"""GitHub API fallback — last-resort data source (v1.4.0).

When both TinkyWiki and DeepWiki fail to provide documentation for a
repository, this module falls back to the GitHub REST API public endpoints
to retrieve at least the README, file tree, and basic repo metadata.

**Public endpoints** (no auth required, 60 req/hr rate limit):
- ``GET /repos/{owner}/{repo}`` — repo metadata (description, stars, etc.)
- ``GET /repos/{owner}/{repo}/readme`` — decoded README markdown
- ``GET /repos/{owner}/{repo}/git/trees/HEAD?recursive=1`` — full file tree
- ``GET /search/code?q={query}+repo:{owner}/{repo}`` — code search

When ``GITHUB_TOKEN`` is set, the rate limit increases to 5000 req/hr.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from . import config
from .parser import WikiPage, WikiSection

logger = logging.getLogger("TinkyWiki")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _github_headers() -> dict[str, str]:
    """Build HTTP headers for GitHub API requests."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "TinkyWiki-MCP/1.4.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return headers


def _github_get(endpoint: str) -> dict | list | None:
    """Make a GET request to the GitHub API.

    Args:
        endpoint: Path part (e.g. ``/repos/facebook/react/readme``).

    Returns:
        Parsed JSON response, or None on error.
    """
    url = f"{config.GITHUB_API_BASE_URL}{endpoint}"

    # Security: enforce HTTPS + allowed host
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com":
        logger.warning("github_api: blocked request to %s", url)
        return None

    try:
        req = urllib.request.Request(url, headers=_github_headers())
        with urllib.request.urlopen(req, timeout=config.GITHUB_API_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("github_api: request failed for %s: %s", endpoint, exc)
        return None


def _extract_owner_repo(repo_url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub URL."""
    clean = repo_url.replace("https://github.com/", "").replace("http://github.com/", "")
    parts = clean.strip("/").split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


# ---------------------------------------------------------------------------
# Repo metadata
# ---------------------------------------------------------------------------
@dataclass
class RepoMeta:
    """Basic GitHub repository metadata."""
    owner: str
    repo: str
    description: str
    stars: int
    language: str
    topics: list[str]
    default_branch: str


def fetch_repo_meta(repo_url: str) -> RepoMeta | None:
    """Fetch basic repository metadata from GitHub API."""
    parts = _extract_owner_repo(repo_url)
    if not parts:
        return None

    owner, repo = parts
    data = _github_get(f"/repos/{owner}/{repo}")
    if not data or isinstance(data, list):
        return None

    return RepoMeta(
        owner=owner,
        repo=repo,
        description=data.get("description") or "",
        stars=data.get("stargazers_count", 0),
        language=data.get("language") or "",
        topics=data.get("topics") or [],
        default_branch=data.get("default_branch", "main"),
    )


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------
def fetch_readme(repo_url: str) -> str | None:
    """Fetch and decode the repository README from GitHub API.

    Returns the markdown content, or None if unavailable.
    """
    parts = _extract_owner_repo(repo_url)
    if not parts:
        return None

    owner, repo = parts
    data = _github_get(f"/repos/{owner}/{repo}/readme")
    if not data or isinstance(data, list):
        return None

    content = data.get("content", "")
    encoding = data.get("encoding", "")

    if encoding == "base64" and content:
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError):
            return None

    return content if content else None


# ---------------------------------------------------------------------------
# File tree
# ---------------------------------------------------------------------------
def fetch_file_tree(repo_url: str, max_entries: int = 200) -> list[str] | None:
    """Fetch the repository file tree from GitHub API.

    Returns a list of file paths, or None on error.
    Truncated to *max_entries* to avoid massive trees.
    """
    parts = _extract_owner_repo(repo_url)
    if not parts:
        return None

    owner, repo = parts

    # First get the default branch
    meta = fetch_repo_meta(repo_url)
    branch = meta.default_branch if meta else "main"

    data = _github_get(f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
    if not data or isinstance(data, list):
        return None

    tree = data.get("tree", [])
    paths = [item.get("path", "") for item in tree if item.get("type") == "blob"]
    return paths[:max_entries]


# ---------------------------------------------------------------------------
# Code search
# ---------------------------------------------------------------------------
def search_code(repo_url: str, query: str, max_results: int = 10) -> list[dict] | None:
    """Search for code in a repository using GitHub's code search API.

    Returns a list of ``{"path": ..., "fragment": ...}`` dicts, or None.

    **Note**: Code search requires authentication. With no token, this
    endpoint returns 401. Falls back gracefully.
    """
    parts = _extract_owner_repo(repo_url)
    if not parts:
        return None

    owner, repo = parts
    q = urllib.parse.quote(f"{query} repo:{owner}/{repo}", safe="")
    data = _github_get(f"/search/code?q={q}&per_page={max_results}")
    if not data or isinstance(data, list):
        return None

    results = []
    for item in data.get("items", [])[:max_results]:
        path = item.get("path", "")
        # The search API doesn't return file content fragments inline,
        # but it does give us the matching file paths
        results.append({
            "path": path,
            "name": item.get("name", ""),
            "url": item.get("html_url", ""),
        })

    return results if results else None


# ---------------------------------------------------------------------------
# Unified WikiPage builder from GitHub API data
# ---------------------------------------------------------------------------
def fetch_github_wiki_page(repo_url: str) -> WikiPage | None:
    """Build a WikiPage from GitHub API data (README + tree + metadata).

    This is the last-resort fallback — it won't have the rich AI-generated
    documentation that TinkyWiki/DeepWiki provide, but it gives the agent
    *something* to work with.

    Returns a WikiPage or None if the repo doesn't exist on GitHub.
    """
    if not config.GITHUB_API_ENABLED:
        return None

    parts = _extract_owner_repo(repo_url)
    if not parts:
        return None

    owner, repo = parts
    logger.info("github_api: building WikiPage for %s/%s", owner, repo)

    sections: list[WikiSection] = []

    # 1. Repo metadata section
    meta = fetch_repo_meta(repo_url)
    if meta is None:
        logger.info("github_api: repo %s/%s not found", owner, repo)
        return None

    meta_content = f"**{meta.owner}/{meta.repo}**"
    if meta.description:
        meta_content += f"\n\n{meta.description}"
    if meta.language:
        meta_content += f"\n\n**Language:** {meta.language}"
    if meta.stars:
        meta_content += f" | **Stars:** {meta.stars:,}"
    if meta.topics:
        meta_content += f"\n\n**Topics:** {', '.join(meta.topics)}"

    sections.append(WikiSection(
        title="Repository Overview",
        level=1,
        content=meta_content,
    ))

    # 2. README section
    readme = fetch_readme(repo_url)
    if readme:
        # Truncate very long READMEs
        if len(readme) > config.RESPONSE_MAX_CHARS // 2:
            readme = readme[:config.RESPONSE_MAX_CHARS // 2] + "\n\n... [README truncated]"
        sections.append(WikiSection(
            title="README",
            level=1,
            content=readme,
        ))

    # 3. File structure section
    tree = fetch_file_tree(repo_url)
    if tree:
        tree_content = "```\n" + "\n".join(tree[:100]) + "\n```"
        if len(tree) > 100:
            tree_content += f"\n\n*... and {len(tree) - 100} more files*"
        sections.append(WikiSection(
            title="File Structure",
            level=1,
            content=tree_content,
        ))

    if not sections:
        return None

    # Build raw text
    raw_parts = [s.content for s in sections if s.content]
    raw_text = "\n\n".join(raw_parts)

    page = WikiPage(
        repo_name=f"{owner}/{repo}",
        url=f"https://github.com/{owner}/{repo}",
        title=f"{owner}/{repo}" + (f" — {meta.description[:100]}" if meta.description else ""),
        sections=sections,
        toc=[{"title": s.title, "level": str(s.level)} for s in sections],
        diagrams=[],
        raw_text=raw_text,
    )

    logger.info(
        "github_api: built WikiPage for %s/%s — %d sections, %d chars",
        owner, repo, len(sections), len(raw_text),
    )
    return page


def github_search_answer(repo_url: str, query: str) -> str | None:
    """Search for code matching a query and return a formatted answer.

    This is the last-resort fallback for the search_wiki tool (chat).
    Returns a formatted string with matching file paths, or None.
    """
    if not config.GITHUB_API_ENABLED:
        return None

    parts = _extract_owner_repo(repo_url)
    if not parts:
        return None

    owner, repo = parts

    # Try code search
    results: list[dict] = search_code(repo_url, query) or []

    # Also get README for context
    readme = fetch_readme(repo_url)

    answer_parts: list[str] = []

    if results:
        answer_parts.append(f"**Code search results for \"{query}\" in {owner}/{repo}:**\n")
        for r in results:
            answer_parts.append(f"- [{r['path']}]({r.get('url', '')})")
        answer_parts.append("")

    if readme:
        # Search README for relevant sections
        query_lower = query.lower()
        readme_lines = readme.split("\n")
        relevant_lines: list[str] = []
        for i, line in enumerate(readme_lines):
            if query_lower in line.lower():
                # Include context: 2 lines before + 5 lines after
                start = max(0, i - 2)
                end = min(len(readme_lines), i + 6)
                relevant_lines.extend(readme_lines[start:end])
                relevant_lines.append("---")

        if relevant_lines:
            answer_parts.append("**Relevant README sections:**\n")
            answer_parts.append("\n".join(relevant_lines[:50]))

    if not answer_parts:
        # Just return basic repo info
        meta = fetch_repo_meta(repo_url)
        if meta:
            answer_parts.append(
                f"**{owner}/{repo}**: {meta.description}\n\n"
                f"Language: {meta.language} | Stars: {meta.stars:,}\n\n"
                f"*No specific documentation found for \"{query}\". "
                f"Consider browsing the repository directly at "
                f"https://github.com/{owner}/{repo}*"
            )

    return "\n".join(answer_parts).strip() if answer_parts else None
