"""Fallback orchestrator — chains TinkyWiki → DeepWiki → GitHub API (v1.4.0).

This module provides a unified interface that transparently tries multiple
data sources in order, so individual tool modules don't need to know about
the fallback chain.

**Fallback chain for page fetching** (list_topics, read_structure, read_contents):
1. Google TinkyWiki (primary) — richest, most structured docs
2. DeepWiki (secondary) — broader coverage, AI-generated
3. GitHub API (last resort) — README + file tree + metadata

**Fallback chain for search/chat** (search_wiki):
1. TinkyWiki Gemini chat
2. DeepWiki Ask chat
3. GitHub code search + README scanning

**Fallback chain for indexing** (request_indexing):
1. TinkyWiki request_indexing
2. DeepWiki indexing request
3. Return guidance to try later

Each layer returns a result tagged with its ``source`` so the agent
knows the provenance and quality level of the data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from . import config
from .parser import WikiPage

logger = logging.getLogger("TinkyWiki")

# Source identifiers
SOURCE_CODEWIKI: str = "tinkywiki"
SOURCE_DEEPWIKI: str = "deepwiki"
SOURCE_GITHUB_API: str = "github_api"


@dataclass
class FallbackResult:
    """Result from the fallback chain, tagged with data source."""
    page: WikiPage | None
    source: str  # "tinkywiki", "deepwiki", or "github_api"
    tinkywiki_not_indexed: bool = False  # True if TinkyWiki returned NOT_INDEXED
    deepwiki_not_indexed: bool = False   # True if DeepWiki returned not-indexed


@dataclass
class SearchFallbackResult:
    """Result from the search fallback chain."""
    response: str | None
    source: str
    tinkywiki_not_indexed: bool = False
    deepwiki_not_indexed: bool = False


def _is_not_indexed_error(page: WikiPage | None) -> bool:
    """Check if a WikiPage represents a not-indexed state."""
    if page is None:
        return True
    if not page.sections and not page.raw_text:
        return True
    # Check for known not-indexed indicators
    text = (page.raw_text or "").lower()
    from . import config as _cfg  # avoid circular import issues
    return any(ind.lower() in text for ind in _cfg.NOT_INDEXED_INDICATORS)


# ---------------------------------------------------------------------------
# Page fetch fallback chain
# ---------------------------------------------------------------------------
def fetch_page_with_fallback(repo_url: str) -> FallbackResult:
    """Fetch a wiki page trying TinkyWiki → DeepWiki → GitHub API.

    This is the main entry point for tools that need page content
    (list_topics, read_structure, read_contents).

    Args:
        repo_url: Normalised full GitHub URL (https://github.com/owner/repo).

    Returns:
        FallbackResult with the page and source tag.
    """
    if not config.FALLBACK_ENABLED:
        # Fallback disabled — only try TinkyWiki
        return _try_tinkywiki(repo_url)

    # --- Layer 1: TinkyWiki ---
    result = _try_tinkywiki(repo_url)
    if result.page is not None and not _is_not_indexed_error(result.page):
        return result

    tinkywiki_not_indexed = result.page is None or _is_not_indexed_error(result.page)
    logger.info(
        "fallback: TinkyWiki %s for %s, trying DeepWiki…",
        "not indexed" if tinkywiki_not_indexed else "failed",
        repo_url,
    )

    # --- Fire-and-forget: request TinkyWiki indexing ---
    if tinkywiki_not_indexed:
        _request_tinkywiki_indexing_async(repo_url)

    # --- Layer 2: DeepWiki ---
    if config.DEEPWIKI_ENABLED:
        result = _try_deepwiki(repo_url)
        result.tinkywiki_not_indexed = tinkywiki_not_indexed
        if result.page is not None:
            return result

        logger.info("fallback: DeepWiki failed for %s, trying GitHub API…", repo_url)

    # --- Layer 3: GitHub API ---
    if config.GITHUB_API_ENABLED:
        result = _try_github_api(repo_url)
        result.tinkywiki_not_indexed = tinkywiki_not_indexed
        result.deepwiki_not_indexed = True
        if result.page is not None:
            return result

    # All layers failed
    return FallbackResult(
        page=None,
        source=SOURCE_CODEWIKI,
        tinkywiki_not_indexed=tinkywiki_not_indexed,
        deepwiki_not_indexed=True,
    )


def _try_tinkywiki(repo_url: str) -> FallbackResult:
    """Try fetching from TinkyWiki (primary source)."""
    try:
        from .parser import fetch_wiki_page  # noqa: E402
        from .dedup import dedup_fetch  # noqa: E402
        page = dedup_fetch(repo_url, lambda: fetch_wiki_page(repo_url))
        return FallbackResult(page=page, source=SOURCE_CODEWIKI)
    except TimeoutError:
        logger.warning("fallback: TinkyWiki timed out for %s", repo_url)
        return FallbackResult(page=None, source=SOURCE_CODEWIKI)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("fallback: TinkyWiki failed for %s: %s", repo_url, exc)
        return FallbackResult(page=None, source=SOURCE_CODEWIKI)


def _try_deepwiki(repo_url: str) -> FallbackResult:
    """Try fetching from DeepWiki (secondary source)."""
    try:
        from .deepwiki import fetch_deepwiki_page  # noqa: E402
        page = fetch_deepwiki_page(repo_url)
        if page is not None:
            return FallbackResult(page=page, source=SOURCE_DEEPWIKI)
        return FallbackResult(page=None, source=SOURCE_DEEPWIKI, deepwiki_not_indexed=True)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("fallback: DeepWiki failed for %s: %s", repo_url, exc)
        return FallbackResult(page=None, source=SOURCE_DEEPWIKI)


def _try_github_api(repo_url: str) -> FallbackResult:
    """Try fetching from GitHub API (last resort)."""
    try:
        from .github_api import fetch_github_wiki_page  # noqa: E402
        page = fetch_github_wiki_page(repo_url)
        if page is not None:
            return FallbackResult(page=page, source=SOURCE_GITHUB_API)
        return FallbackResult(page=None, source=SOURCE_GITHUB_API)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("fallback: GitHub API failed for %s: %s", repo_url, exc)
        return FallbackResult(page=None, source=SOURCE_GITHUB_API)


def _request_tinkywiki_indexing_async(repo_url: str) -> None:
    """Fire-and-forget TinkyWiki indexing request (best-effort).

    When TinkyWiki hasn't indexed a repo, we silently submit an indexing
    request so that it might be available next time.
    """
    try:
        import threading

        def _do_request():
            try:
                from .tools.request_indexing import _run_request_indexing  # noqa: E402
                _run_request_indexing(repo_url)
                logger.info("fallback: auto-requested TinkyWiki indexing for %s", repo_url)
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("fallback: auto-indexing request failed: %s", exc)

        thread = threading.Thread(target=_do_request, daemon=True, name="auto-index")
        thread.start()
    except Exception:  # pylint: disable=broad-except
        pass  # fire-and-forget, never block the main flow


# ---------------------------------------------------------------------------
# Search/chat fallback chain
# ---------------------------------------------------------------------------
def search_with_fallback(
    repo_url: str,
    query: str,
    tinkywiki_search_fn=None,
) -> SearchFallbackResult:
    """Search/chat fallback: TinkyWiki chat → DeepWiki Ask → GitHub search.

    Args:
        repo_url: Normalised full GitHub URL.
        query: The user's question.
        tinkywiki_search_fn: Callable that runs the TinkyWiki chat search.
            Should return a ToolResponse. If None, skips TinkyWiki.

    Returns:
        SearchFallbackResult with response text and source.
    """
    from .types import ToolResponse, ErrorCode  # noqa: E402

    tinkywiki_not_indexed = False

    # --- Layer 1: TinkyWiki chat ---
    if tinkywiki_search_fn is not None:
        result = tinkywiki_search_fn()
        if isinstance(result, ToolResponse):
            if result.status.value == "ok" and result.data:
                return SearchFallbackResult(
                    response=result.data,
                    source=SOURCE_CODEWIKI,
                )
            # Check if it's a NOT_INDEXED error
            if result.code in (ErrorCode.NOT_INDEXED, ErrorCode.NO_CONTENT):
                tinkywiki_not_indexed = True
                logger.info("fallback: TinkyWiki chat not available for %s, trying DeepWiki…", repo_url)
            elif result.code in (ErrorCode.INPUT_NOT_FOUND, ErrorCode.DRIVER_ERROR):
                # Chat UI issues — try DeepWiki
                logger.info("fallback: TinkyWiki chat failed for %s, trying DeepWiki…", repo_url)

    # --- Layer 2: DeepWiki Ask ---
    if config.DEEPWIKI_ENABLED and config.FALLBACK_ENABLED:
        try:
            from .deepwiki import deepwiki_ask  # noqa: E402
            response = deepwiki_ask(repo_url, query)
            if response:
                return SearchFallbackResult(
                    response=response,
                    source=SOURCE_DEEPWIKI,
                    tinkywiki_not_indexed=tinkywiki_not_indexed,
                )
            logger.info("fallback: DeepWiki Ask failed for %s, trying GitHub…", repo_url)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("fallback: DeepWiki Ask error: %s", exc)

    # --- Layer 3: GitHub API search ---
    if config.GITHUB_API_ENABLED and config.FALLBACK_ENABLED:
        try:
            from .github_api import github_search_answer  # noqa: E402
            response = github_search_answer(repo_url, query)
            if response:
                return SearchFallbackResult(
                    response=response,
                    source=SOURCE_GITHUB_API,
                    tinkywiki_not_indexed=tinkywiki_not_indexed,
                    deepwiki_not_indexed=True,
                )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("fallback: GitHub search error: %s", exc)

    return SearchFallbackResult(
        response=None,
        source=SOURCE_CODEWIKI,
        tinkywiki_not_indexed=tinkywiki_not_indexed,
        deepwiki_not_indexed=True,
    )


# ---------------------------------------------------------------------------
# Source banner — prepended to responses to show provenance
# ---------------------------------------------------------------------------
def build_source_banner(source: str, tinkywiki_not_indexed: bool = False, deepwiki_not_indexed: bool = False) -> str:
    """Build a markdown banner indicating the data source.

    Examples::
        > **Source:** Google TinkyWiki
        > **Source:** DeepWiki (TinkyWiki not indexed — auto-requested)
        > **Source:** GitHub API (TinkyWiki & DeepWiki not indexed)
    """
    labels = {
        SOURCE_CODEWIKI: "Google TinkyWiki",
        SOURCE_DEEPWIKI: "DeepWiki",
        SOURCE_GITHUB_API: "GitHub API",
    }
    label = labels.get(source, source)

    notes: list[str] = []
    if source == SOURCE_DEEPWIKI and tinkywiki_not_indexed:
        notes.append("TinkyWiki not indexed — auto-requested")
    elif source == SOURCE_GITHUB_API:
        parts = []
        if tinkywiki_not_indexed:
            parts.append("TinkyWiki")
        if deepwiki_not_indexed:
            parts.append("DeepWiki")
        if parts:
            notes.append(f"{' & '.join(parts)} not indexed")

    note_str = f" ({'; '.join(notes)})" if notes else ""
    return f"> **Source:** {label}{note_str}\n\n"
