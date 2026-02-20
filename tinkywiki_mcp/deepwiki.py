"""DeepWiki integration — second-layer fallback behind Google TinkyWiki (v1.4.0).

DeepWiki (https://deepwiki.com) provides AI-generated documentation for GitHub
repositories, powered by DeepSeek.  It has broader coverage than Google TinkyWiki,
making it an excellent fallback when TinkyWiki hasn't indexed a repo.

**Architecture**:
- DeepWiki is a Next.js app with a sidebar navigation listing topics.
- Each topic lives at ``https://deepwiki.com/{owner}/{repo}/{slug}``
  (e.g. ``/facebook/react/1-overview``).
- The main repo page at ``https://deepwiki.com/{owner}/{repo}`` shows the
  overview + sidebar with all topic links.
- DeepWiki has an "Ask" chat feature similar to TinkyWiki's Gemini chat.

**Page fetching**: Uses the shared Playwright browser (same as TinkyWiki) to
render the Next.js SPA, then BeautifulSoup to extract structured content.

**Chat interaction**: Types into the DeepWiki Ask input and reads the streamed
response, following the same pattern as TinkyWiki's chat.
"""

from __future__ import annotations

import asyncio
import logging
import re

from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from . import config
from .browser import _get_browser, fetch_rendered_html, run_in_browser_loop
from .cache import get_cached_page, get_cached_wiki_page, set_cached_page, set_cached_wiki_page
from .parser import WikiPage, WikiSection, _extract_text, _tag_to_markdown
from .stealth import apply_stealth_scripts, human_click, human_type, random_delay, stealth_context_options

logger = logging.getLogger("TinkyWiki")


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------
def build_deepwiki_url(repo_url: str) -> str:
    """Convert a normalised GitHub repo URL to a DeepWiki page URL.

    Example::
        >>> build_deepwiki_url("https://github.com/facebook/react")
        'https://deepwiki.com/facebook/react'
    """
    clean = repo_url.replace("https://github.com/", "").replace("http://github.com/", "")
    # Remove trailing slashes and path fragments
    clean = clean.split("#")[0].split("?")[0].rstrip("/")
    return f"{config.DEEPWIKI_BASE_URL}/{clean}"


def _extract_owner_repo(repo_url: str) -> str:
    """Extract owner/repo from a full GitHub URL."""
    clean = repo_url.replace("https://github.com/", "").replace("http://github.com/", "")
    parts = clean.strip("/").split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return clean


# ---------------------------------------------------------------------------
# Not-indexed detection
# ---------------------------------------------------------------------------
def is_deepwiki_not_indexed(html: str) -> bool:
    """Return True if the HTML indicates DeepWiki hasn't indexed this repo."""
    text = html.lower()
    return any(ind.lower() in text for ind in config.DEEPWIKI_NOT_INDEXED_INDICATORS)


# ---------------------------------------------------------------------------
# Sidebar / topic parsing
# ---------------------------------------------------------------------------
@dataclass
class DeepWikiTopic:
    """A topic entry from DeepWiki's sidebar navigation."""
    title: str
    slug: str
    url: str
    level: int = 1  # 1=top-level, 2=sub-topic


def _parse_sidebar_topics(soup: BeautifulSoup, owner_repo: str) -> list[DeepWikiTopic]:
    """Extract topic links from DeepWiki's sidebar navigation.

    DeepWiki sidebar contains ``<a>`` elements with hrefs like:
      ``/facebook/react/1-overview``
      ``/facebook/react/2.1-component-system``

    We parse these into structured ``DeepWikiTopic`` entries.
    """
    topics: list[DeepWikiTopic] = []
    seen_slugs: set[str] = set()

    # Pattern to match topic links: /{owner}/{repo}/{slug}
    topic_pattern = re.compile(
        rf"/{re.escape(owner_repo)}/(\d[\w.\-()]+)",
        re.IGNORECASE,
    )

    # Look for all links in the page
    for link in soup.find_all("a", href=True):
        href = str(link.get("href", ""))
        match = topic_pattern.search(href)
        if not match:
            continue

        slug = match.group(1)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        title = link.get_text(strip=True)
        if not title or len(title) < 2:
            continue

        # Determine level from slug pattern (e.g. "1-overview" = 1, "1.1-foo" = 2)
        level = 1 if "." not in slug.split("-")[0] else 2

        full_url = f"{config.DEEPWIKI_BASE_URL}/{owner_repo}/{slug}"
        topics.append(DeepWikiTopic(title=title, slug=slug, url=full_url, level=level))

    return topics


# ---------------------------------------------------------------------------
# Content parsing (single page)
# ---------------------------------------------------------------------------
def _parse_deepwiki_content(soup: BeautifulSoup) -> list[WikiSection]:
    """Parse content sections from a DeepWiki page.

    DeepWiki renders content with standard HTML headings (h1-h6) inside
    the main content area. We parse these the same way as TinkyWiki's
    heading-based fallback strategy.
    """
    sections: list[WikiSection] = []

    # Find main content area
    main = None
    for sel in config.DEEPWIKI_CONTENT_SELECTORS:
        if sel.startswith("."):
            main = soup.find(class_=re.compile(sel[1:], re.I))
        elif sel.startswith("["):
            # attribute selector like [class*='content']
            attr_match = re.match(r"\[(\w+)\*='([^']+)'\]", sel)
            if attr_match:
                attr_name, attr_val = attr_match.group(1), attr_match.group(2)
                _an, _av = attr_name, attr_val  # bind for closure
                main = soup.find(lambda tag, an=_an, av=_av: tag and av.lower() in (str(tag.get(an, "")) or "").lower() if hasattr(tag, 'get') else False)  # type: ignore[call-overload]
        else:
            main = soup.find(sel)
        if main:
            break

    if not main:
        main = soup.find("body")
    if not main:
        return sections

    # Parse headings as section delimiters
    current_section: WikiSection | None = None
    content_parts: list[str] = []

    all_headings = main.find_all(re.compile(r"h[1-6]"))
    if not all_headings:
        # No headings — treat entire content as one section
        text = _extract_text(main) if isinstance(main, Tag) else main.get_text(strip=True)
        if text and len(text) > 50:
            sections.append(WikiSection(title="Overview", level=1, content=text))
        return sections

    for heading in all_headings:
        if current_section is not None:
            current_section.content = "\n".join(content_parts).strip()
            sections.append(current_section)
            content_parts = []

        level = int(heading.name[1])
        title = heading.get_text(strip=True)
        # Strip trailing image/icon artifacts
        title = re.sub(r"\s*\[Image:.*?\]\s*$", "", title).strip()
        current_section = WikiSection(title=title, level=level)

        for sibling in heading.find_next_siblings():
            if isinstance(sibling, Tag):
                if re.match(r"h[1-6]", sibling.name or ""):
                    break
                text = _tag_to_markdown(sibling)
                if text:
                    content_parts.append(text)

    if current_section is not None:
        current_section.content = "\n".join(content_parts).strip()
        sections.append(current_section)

    return sections


# ---------------------------------------------------------------------------
# Page fetcher (Playwright-rendered with caching)
# ---------------------------------------------------------------------------
def _fetch_deepwiki_html(url: str) -> str:
    """Fetch rendered HTML from DeepWiki with caching."""
    cache_key = f"deepwiki::{url}"
    cached = get_cached_page(cache_key)
    if cached is not None:
        return cached

    html = fetch_rendered_html(url)
    if html:
        set_cached_page(cache_key, html)
    return html


def fetch_deepwiki_page(repo_url: str) -> WikiPage | None:
    """Fetch and parse a DeepWiki page for *repo_url*.

    Returns a ``WikiPage`` normalised to the same format as TinkyWiki pages,
    or ``None`` if the repo is not indexed on DeepWiki.
    """
    # Check parsed cache first
    cache_key = f"deepwiki::{repo_url}"
    cached_page = get_cached_wiki_page(cache_key)
    if cached_page is not None:
        return cached_page

    owner_repo = _extract_owner_repo(repo_url)
    deepwiki_url = build_deepwiki_url(repo_url)

    html = _fetch_deepwiki_html(deepwiki_url)
    if not html:
        return None

    if is_deepwiki_not_indexed(html):
        logger.info("DeepWiki: repo %s not indexed", owner_repo)
        return None

    soup = BeautifulSoup(html, "lxml")

    # Extract title
    title_tag = soup.find("h1") or soup.find("h2")
    title = title_tag.get_text(strip=True) if title_tag else owner_repo
    title = re.sub(r"\s*\[Image:.*?\]\s*", "", title).strip()

    # Parse sidebar topics into sections (lightweight TOC)
    topics = _parse_sidebar_topics(soup, owner_repo)

    # Parse main content sections from the overview page
    sections = _parse_deepwiki_content(soup)

    # If we have sidebar topics but few sections from the overview,
    # convert topics into section stubs so structure tools work
    if topics and len(sections) < 3:
        for topic in topics:
            # Check if this topic is already in sections
            already_exists = any(
                topic.title.lower() in s.title.lower() or s.title.lower() in topic.title.lower()
                for s in sections
            )
            if not already_exists:
                sections.append(WikiSection(
                    title=topic.title,
                    level=topic.level,
                    content=f"[Full content at: {topic.url}]",
                ))

    # Build TOC from topics
    toc = [{"title": t.title, "level": str(t.level)} for t in topics]

    # Build raw text
    body = soup.find("body")
    raw_text = body.get_text(separator="\n", strip=True) if body else ""
    for artifact in config.DEEPWIKI_UI_ARTIFACTS:
        raw_text = raw_text.replace(artifact, "")

    page = WikiPage(
        repo_name=owner_repo,
        url=deepwiki_url,
        title=title,
        sections=sections,
        toc=toc,
        diagrams=[],  # DeepWiki diagrams are Mermaid-based, parsed from content
        raw_text=raw_text,
    )

    logger.info(
        "DeepWiki parsed %s: %d sections, %d topics, %d chars",
        owner_repo,
        len(sections),
        len(topics),
        len(raw_text),
    )

    set_cached_wiki_page(cache_key, page)
    return page


def fetch_deepwiki_section(repo_url: str, topic_slug: str) -> WikiPage | None:
    """Fetch a specific DeepWiki topic/section page.

    Args:
        repo_url: Full GitHub URL.
        topic_slug: Topic slug (e.g. '1-overview', '2.1-component-system').

    Returns:
        WikiPage with sections from that specific topic page.
    """
    owner_repo = _extract_owner_repo(repo_url)
    topic_url = f"{config.DEEPWIKI_BASE_URL}/{owner_repo}/{topic_slug}"

    cache_key = f"deepwiki::{topic_url}"
    cached_page = get_cached_wiki_page(cache_key)
    if cached_page is not None:
        return cached_page

    html = _fetch_deepwiki_html(topic_url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    sections = _parse_deepwiki_content(soup)

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else topic_slug
    title = re.sub(r"\s*\[Image:.*?\]\s*", "", title).strip()

    body = soup.find("body")
    raw_text = body.get_text(separator="\n", strip=True) if body else ""

    page = WikiPage(
        repo_name=owner_repo,
        url=topic_url,
        title=title,
        sections=sections,
        toc=[],
        diagrams=[],
        raw_text=raw_text,
    )

    set_cached_wiki_page(cache_key, page)
    return page


# ---------------------------------------------------------------------------
# DeepWiki Chat / Ask feature (Playwright-based)
# ---------------------------------------------------------------------------
async def _deepwiki_ask_impl(repo_url: str, query: str) -> str | None:
    """Navigate to DeepWiki repo page and use the Ask feature.

    Returns the response text, or None if the chat feature is unavailable
    or the repo is not indexed.
    """
    owner_repo = _extract_owner_repo(repo_url)
    deepwiki_url = build_deepwiki_url(repo_url)

    browser = await _get_browser()
    ctx_opts = stealth_context_options()
    ctx_opts["user_agent"] = config.USER_AGENT
    context = await browser.new_context(**ctx_opts)
    page = await context.new_page()
    await apply_stealth_scripts(page)

    try:
        logger.info("DeepWiki Ask: navigating to %s", deepwiki_url)
        await page.goto(
            deepwiki_url,
            wait_until="domcontentloaded",
            timeout=config.PAGE_LOAD_TIMEOUT_SECONDS * 1000,
        )

        # Wait for content to render
        try:
            await page.wait_for_selector(
                "h1, h2, article, main, [class*='content']",
                timeout=config.ELEMENT_WAIT_TIMEOUT_SECONDS * 1000,
            )
        except PlaywrightTimeoutError:
            await asyncio.sleep(config.JS_LOAD_DELAY_SECONDS)

        await asyncio.sleep(2)

        # Check if repo is indexed
        body_text = await page.inner_text("body")
        if any(ind.lower() in body_text.lower() for ind in config.DEEPWIKI_NOT_INDEXED_INDICATORS):
            logger.info("DeepWiki Ask: repo %s not indexed", owner_repo)
            return None

        # Find the Ask input
        ask_input = None
        for selector in config.DEEPWIKI_ASK_INPUT_SELECTORS:
            try:
                elem = page.locator(selector).first
                if await elem.is_visible(timeout=2000):
                    ask_input = elem
                    logger.debug("DeepWiki Ask: found input: %s", selector)
                    break
            except (PlaywrightTimeoutError, RuntimeError, ValueError, TypeError, AttributeError):
                continue

        if not ask_input:
            logger.info("DeepWiki Ask: no Ask input found on %s", deepwiki_url)
            return None

        # Type the query
        await human_click(page, ask_input)
        await random_delay(0.2, 0.5)
        await ask_input.fill("")
        await random_delay(0.2, 0.4)
        await human_type(ask_input, query)
        await random_delay(0.3, 0.8)

        # Submit — try Enter first, then button click
        await ask_input.press("Enter")
        await random_delay(0.3, 0.6)

        # Try button click as fallback
        for selector in config.DEEPWIKI_ASK_SUBMIT_SELECTORS:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=1000):
                    if not await btn.is_disabled():
                        await btn.click()
                        logger.debug("DeepWiki Ask: clicked submit: %s", selector)
                        break
            except (PlaywrightTimeoutError, RuntimeError, ValueError, TypeError, AttributeError):
                continue

        # Wait for response
        await asyncio.sleep(config.RESPONSE_INITIAL_DELAY_SECONDS)

        # Wait for response content to appear and stabilize
        deadline = asyncio.get_event_loop().time() + config.RESPONSE_WAIT_TIMEOUT_SECONDS
        content = ""

        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(config.RESPONSE_POLL_INTERVAL_SECONDS)
            # Look for response content — DeepWiki renders in markdown-style divs
            for sel in ["[class*='answer']", "[class*='response']", "[class*='message']",
                        "[class*='markdown']", ".prose", "article"]:
                try:
                    elem = page.locator(sel).last
                    if await elem.is_visible(timeout=500):
                        text = await elem.inner_text()
                        if len(text) > config.NEW_CONTENT_THRESHOLD_CHARS:
                            content = text
                            break
                except (PlaywrightTimeoutError, RuntimeError, ValueError, TypeError, AttributeError):
                    continue
            if content:
                break

        if not content:
            logger.info("DeepWiki Ask: no response received for %s", owner_repo)
            return None

        # Wait for streaming to stabilize
        last_len = len(content)
        for _ in range(10):
            await asyncio.sleep(config.RESPONSE_STABLE_INTERVAL_SECONDS)
            for sel in ["[class*='answer']", "[class*='response']", "[class*='message']",
                        "[class*='markdown']", ".prose", "article"]:
                try:
                    elem = page.locator(sel).last
                    if await elem.is_visible(timeout=500):
                        content = await elem.inner_text()
                        break
                except (PlaywrightTimeoutError, RuntimeError, ValueError, TypeError, AttributeError):
                    continue
            if len(content) == last_len:
                break
            last_len = len(content)

        # Clean up artifacts
        for artifact in config.DEEPWIKI_UI_ARTIFACTS:
            content = content.replace(artifact, "")

        return content.strip() if content.strip() else None

    except (
        PlaywrightTimeoutError,
        asyncio.TimeoutError,
        RuntimeError,
        ValueError,
        TypeError,
    ) as exc:
        logger.warning("DeepWiki Ask failed for %s: %s", owner_repo, exc)
        return None
    finally:
        await page.close()
        await context.close()


def deepwiki_ask(repo_url: str, query: str) -> str | None:
    """Synchronous wrapper: ask DeepWiki a question about a repository.

    Returns the response text, or None if unavailable.
    """
    if not config.DEEPWIKI_ENABLED:
        return None
    try:
        return run_in_browser_loop(_deepwiki_ask_impl(repo_url, query))
    except (asyncio.TimeoutError, RuntimeError, ValueError, TypeError) as exc:
        logger.warning("DeepWiki Ask sync wrapper failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# DeepWiki indexing request
# ---------------------------------------------------------------------------
async def _deepwiki_request_indexing_impl(repo_url: str) -> bool:
    """Navigate to DeepWiki and look for an 'Index' or 'Add repo' button.

    DeepWiki has an "Index your code with Devin" button on the homepage,
    and potentially an "Add repo" flow. This is best-effort.

    Returns True if we believe the request was submitted.
    """
    deepwiki_url = build_deepwiki_url(repo_url)

    browser = await _get_browser()
    ctx_opts = stealth_context_options()
    ctx_opts["user_agent"] = config.USER_AGENT
    context = await browser.new_context(**ctx_opts)
    page = await context.new_page()
    await apply_stealth_scripts(page)

    try:
        await page.goto(
            deepwiki_url,
            wait_until="domcontentloaded",
            timeout=config.PAGE_LOAD_TIMEOUT_SECONDS * 1000,
        )
        await asyncio.sleep(config.JS_LOAD_DELAY_SECONDS)

        # Look for "Add repo" or "Index" button
        for selector in [
            "button:has-text('Add repo')",
            "button:has-text('Index')",
            "a:has-text('Add repo')",
            "a:has-text('Index')",
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    logger.info("DeepWiki: clicked indexing button: %s", selector)
                    await asyncio.sleep(2)
                    return True
            except (PlaywrightTimeoutError, RuntimeError, ValueError, TypeError):
                continue

        logger.info("DeepWiki: no indexing button found for %s", repo_url)
        return False

    except (PlaywrightTimeoutError, asyncio.TimeoutError, RuntimeError, ValueError, TypeError) as exc:
        logger.warning("DeepWiki indexing request failed: %s", exc)
        return False
    finally:
        await page.close()
        await context.close()


def deepwiki_request_indexing(repo_url: str) -> bool:
    """Synchronous wrapper: request DeepWiki to index a repo."""
    if not config.DEEPWIKI_ENABLED:
        return False
    try:
        return run_in_browser_loop(_deepwiki_request_indexing_impl(repo_url))
    except (asyncio.TimeoutError, RuntimeError, ValueError, TypeError) as exc:
        logger.warning("DeepWiki indexing sync wrapper failed: %s", exc)
        return False
