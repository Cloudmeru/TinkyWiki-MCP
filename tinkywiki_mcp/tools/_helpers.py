"""Shared helpers for TinkyWiki MCP tools.

Eliminates boilerplate duplicated across tool modules: input validation,
page fetching with error handling, response truncation, URL construction,
in-flight deduplication, rate limiting, and keyword resolution notes.

v1.4.0: ``fetch_page_or_error`` now uses the fallback chain
(TinkyWiki → DeepWiki → GitHub API) when the primary source fails.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import config
from ..fallback import (
    FallbackResult,
    fetch_page_with_fallback,
)
from ..parser import WikiPage
from ..rate_limit import time_until_next_slot, wait_for_rate_limit
from ..resolver import is_bare_keyword, resolve_keyword, resolve_keyword_interactive
from ..types import (
    ErrorCode,
    ResponseMeta,
    ToolResponse,
    validate_topics_input,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context


# ---------------------------------------------------------------------------
# Not-indexed detection
# ---------------------------------------------------------------------------
def _is_not_indexed(page: WikiPage) -> bool:
    """Return True if the fetched page is a TinkyWiki 404 / not-indexed page.

    TinkyWiki renders a 404 SPA page containing "This page doesn't exist"
    and a "request a repo" prompt when the repository hasn't been indexed.
    """
    if page.sections:
        return False
    text = (page.raw_text or "").lower()
    return any(ind.lower() in text for ind in config.NOT_INDEXED_INDICATORS)


logger = logging.getLogger("TinkyWiki")


# ---------------------------------------------------------------------------
# Pre-resolution: bare keyword → owner/repo with elicitation
# ---------------------------------------------------------------------------
def pre_resolve_keyword(raw_input: str, ctx: Context | None = None) -> str:
    """Resolve bare keywords interactively before passing to Pydantic validators.

    If *raw_input* is a bare keyword (e.g. "vue"), this uses
    ``resolve_keyword_interactive()`` with MCP elicitation to let the user
    pick from multiple candidates.  If already ``owner/repo`` or a full URL,
    returns unchanged.

    Args:
        raw_input: The user-supplied repo identifier.
        ctx: MCP Context for elicitation (None = skip elicitation).

    Returns:
        Resolved ``owner/repo`` string, or the original input unchanged.
    """
    if not is_bare_keyword(raw_input):
        return raw_input

    resolved, _results = resolve_keyword_interactive(raw_input, ctx)
    if resolved:
        return resolved

    # Could not resolve — return original; the validator will give a helpful error
    return raw_input


# ---------------------------------------------------------------------------
# Keyword resolution note
# ---------------------------------------------------------------------------
def build_resolution_note(original_input: str, resolved_repo_url: str) -> str:
    """Build a note explaining keyword → repo resolution, or empty string.

    Returns a markdown note like:
        > **Resolved:** keyword "vue" → **vuejs/vue** (209.9k★)
        > Other candidates: vuejs/core (52.9k★), panjiachen/vue-element-admin (90.3k★)

    Returns empty string if the input was already owner/repo or a full URL.
    """
    if not is_bare_keyword(original_input):
        return ""

    _, results = resolve_keyword(original_input)  # uses cache, no extra call
    if not results:
        return ""

    # Find which result was selected
    clean = resolved_repo_url.replace("https://github.com/", "").replace(
        "http://github.com/", ""
    )

    selected = None
    others = []
    for r in results:
        if r.full_name == clean:
            selected = r
        else:
            others.append(r)

    if selected is None:
        return ""

    note = f'> **Resolved:** keyword "{original_input}" → **{selected.full_name}**'
    if selected.stars:
        note += f" ({selected.stars:,}★)"
    note += "\n"

    # Show top 3 other candidates
    top_others = sorted(others, key=lambda r: r.stars, reverse=True)[:3]
    if top_others:
        candidates = ", ".join(
            f"{r.full_name} ({r.stars:,}★)" if r.stars else r.full_name
            for r in top_others
        )
        note += f"> Other candidates: {candidates}\n"

    note += "\n"
    return note


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------
def build_tinkywiki_url(repo_url: str) -> str:
    """Convert a normalised repo URL to a full TinkyWiki page URL.

    Example::

        >>> build_tinkywiki_url("https://github.com/microsoft/vscode")
        'https://codewiki.google/github.com/microsoft/vscode'
    """
    clean = repo_url.replace("https://", "").replace("http://", "")
    return f"{config.TINKYWIKI_BASE_URL}/{clean}"


# ---------------------------------------------------------------------------
# Truncation with word-boundary awareness
# ---------------------------------------------------------------------------
def truncate_response(data: str, max_chars: int = 0) -> tuple[str, bool]:
    """Truncate *data* at a word boundary near *max_chars*.

    Returns ``(text, was_truncated)``.  If *max_chars* is 0 or the text
    is shorter, returns the original text unchanged.
    """
    if not max_chars or len(data) <= max_chars:
        return data, False

    # Try to break at the last newline before the limit
    cut = data[:max_chars]
    last_nl = cut.rfind("\n")
    if last_nl > max_chars * 0.8:  # only if we keep ≥80% of the budget
        cut = cut[:last_nl]
    else:
        # Fall back to last space
        last_sp = cut.rfind(" ")
        if last_sp > max_chars * 0.8:
            cut = cut[:last_sp]

    return cut.rstrip() + "\n\n... [truncated]", True


# ---------------------------------------------------------------------------
# Unified page fetcher with error handling + fallback chain (v1.4.0)
# ---------------------------------------------------------------------------
def fetch_page_or_error(repo_url: str) -> WikiPage | ToolResponse:
    """Validate *repo_url*, fetch and return a WikiPage, or a ToolResponse error.

    **v1.4.0:** When TinkyWiki returns NOT_INDEXED or NO_CONTENT and fallback
    is enabled, transparently tries DeepWiki → GitHub API before giving up.
    The returned ``WikiPage.source`` indicates which layer served the data.

    Handles validation, rate limiting, in-flight deduplication, NOT_INDEXED
    detection, fallback chain, TIMEOUT, and generic exceptions.
    """
    validated = validate_topics_input(repo_url)
    if isinstance(validated, ToolResponse):
        return validated

    if not wait_for_rate_limit(validated.repo_url):
        retry_after = time_until_next_slot(validated.repo_url)
        return ToolResponse.error(
            ErrorCode.RATE_LIMITED,
            f"Rate limit exceeded for {validated.repo_url}. "
            f"Max {config.RATE_LIMIT_MAX_CALLS} calls per "
            f"{config.RATE_LIMIT_WINDOW_SECONDS}s window. "
            f"Retry after {retry_after:.0f}s.",
            repo_url=validated.repo_url,
            meta=ResponseMeta(
                retry_after_seconds=round(retry_after, 1),
                calls_remaining=0,
            ),
        )

    # --- Fallback chain: TinkyWiki → DeepWiki → GitHub API ---
    try:
        fb_result: FallbackResult = fetch_page_with_fallback(validated.repo_url)
    except TimeoutError as exc:
        return ToolResponse.error(
            ErrorCode.TIMEOUT,
            f"Timed out fetching wiki page for {validated.repo_url}: {exc}",
            repo_url=validated.repo_url,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return ToolResponse.error(
            ErrorCode.INTERNAL,
            f"Failed to fetch wiki page: {exc}",
            repo_url=validated.repo_url,
        )

    if fb_result.page is not None:
        # Validate the page has actual content (not a 404 / not-indexed page)
        page = fb_result.page
        if not page.sections and not page.raw_text:
            return ToolResponse.error(
                ErrorCode.NO_CONTENT,
                f"No content found for {validated.repo_url}. "
                "The repository may not be indexed by any supported source.",
                repo_url=validated.repo_url,
            )
        if _is_not_indexed(page):
            return _build_all_failed_response(validated.repo_url, fb_result)
        return page

    # All sources failed — return NOT_INDEXED or NO_CONTENT
    return _build_all_failed_response(validated.repo_url, fb_result)


def _build_all_failed_response(repo_url: str, fb: FallbackResult) -> ToolResponse:
    """Build an error ToolResponse when all fallback layers failed."""
    parts = [
        f"The repository {repo_url} is not yet available on any supported source.",
    ]
    if fb.tinkywiki_not_indexed:
        parts.append(
            f"• **TinkyWiki:** not indexed — auto-indexing requested. "
            f"You can also visit: {config.TINKYWIKI_REQUEST_URL}"
        )
    if fb.deepwiki_not_indexed and config.DEEPWIKI_ENABLED:
        parts.append(
            f"• **DeepWiki:** not available. Try visiting "
            f"{config.DEEPWIKI_BASE_URL}/{repo_url.replace('https://github.com/', '')} "
            f"to trigger indexing."
        )
    if config.GITHUB_API_ENABLED:
        parts.append("• **GitHub API:** could not retrieve sufficient content.")

    parts.append("\nPlease try again later once indexing is complete.")

    return ToolResponse.error(
        ErrorCode.NOT_INDEXED,
        "\n".join(parts),
        repo_url=repo_url,
    )


def _validate_fetched_page(repo_url: str, page: WikiPage) -> WikiPage | ToolResponse:
    """Validate fetched page content and convert not-indexed states to errors.

    NOTE: This is retained for backward compatibility but the main flow
    now uses ``fetch_page_with_fallback`` which handles not-indexed detection
    internally.
    """
    if not page.sections and not page.raw_text:
        return ToolResponse.error(
            ErrorCode.NO_CONTENT,
            f"No content found for {repo_url}. "
            "The repository may not be indexed by TinkyWiki.",
            repo_url=repo_url,
        )

    if _is_not_indexed(page):
        tinkywiki_url = build_tinkywiki_url(repo_url)
        return ToolResponse.error(
            ErrorCode.NOT_INDEXED,
            f"The repository {repo_url} is not yet indexed by "
            f"Google TinkyWiki. You can request indexing by visiting: "
            f"{config.TINKYWIKI_REQUEST_URL} and searching for the "
            f"repository, or navigate directly to {tinkywiki_url} — "
            f"TinkyWiki may begin indexing automatically. "
            f"Please try again later once indexing is complete.",
            repo_url=repo_url,
        )

    return page
