"""tinkywiki_list_topics tool — Lightweight topic discovery.

Returns section titles with short content previews — dramatically more
token-efficient than dumping the full page.  For full content, use
``tinkywiki_read_contents`` with pagination.
"""

from __future__ import annotations

import logging
import time

from mcp.server.fastmcp import Context, FastMCP

from .. import config
from ..cache import get_cached_topics, set_cached_topics
from ..fallback import build_source_banner
from ..parser import page_to_topic_list
from ..types import ResponseMeta, ToolResponse, validate_topics_input
from ..rate_limit import rate_limit_remaining
from ._helpers import (
    build_resolution_note,
    fetch_page_or_error,
    pre_resolve_keyword,
    truncate_response,
)

logger = logging.getLogger("TinkyWiki")


# ---------------------------------------------------------------------------
# Public: tool registration
# ---------------------------------------------------------------------------
def register(mcp: FastMCP) -> None:
    """Register the tinkywiki_list_topics tool on the MCP server."""

    @mcp.tool()
    def tinkywiki_list_topics(repo_url: str, ctx: Context) -> str:
        """
        Retrieve the overview / available topics for a repository from Google TinkyWiki.

        Use this to discover what TinkyWiki knows about a repo before asking
        specific questions with ``tinkywiki_search_wiki``.

        Returns section titles with short content previews (not the full page).
        For detailed content, call ``tinkywiki_read_contents`` with a section title.

        **Response size**: typically 5–30 KB depending on the repository.
        Cached for 30 minutes — repeated calls for the same repo are instant.

        **Rate limit**: max 10 calls per 60 s per repo URL. Duplicate
        concurrent calls are automatically deduplicated.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/microsoft/vscode-copilot-chat)
                      or shorthand owner/repo (e.g. microsoft/vscode-copilot-chat).
                      Bare keywords (e.g. 'vue') are auto-resolved with
                      interactive disambiguation.
        """
        start = time.monotonic()
        logger.info("tinkywiki_list_topics — repo: %s", repo_url)

        original_input = repo_url  # save before resolution
        repo_url = pre_resolve_keyword(repo_url, ctx)  # elicitation for bare keywords

        # Check topic-specific cache first (30-min TTL)
        validated = validate_topics_input(repo_url)
        if isinstance(validated, ToolResponse):
            return validated.to_text()

        note = build_resolution_note(original_input, validated.repo_url)

        cached = get_cached_topics(validated.repo_url)
        if cached is not None:
            elapsed = int((time.monotonic() - start) * 1000)
            return ToolResponse.success(
                note + cached,
                repo_url=validated.repo_url,
                meta=ResponseMeta(
                    elapsed_ms=elapsed,
                    char_count=len(cached),
                    calls_remaining=rate_limit_remaining(validated.repo_url),
                ),
            ).to_text()

        result = fetch_page_or_error(repo_url)
        if isinstance(result, ToolResponse):
            return result.to_text()

        page = result
        source_banner = build_source_banner(page.source) if page.source != "tinkywiki" else ""
        data = page_to_topic_list(
            page,
            preview_chars=config.TOPIC_PREVIEW_CHARS,
        )
        data, truncated = truncate_response(data, config.RESPONSE_MAX_CHARS)

        # Store in topic cache (long TTL)
        set_cached_topics(validated.repo_url, data)

        elapsed = int((time.monotonic() - start) * 1000)

        return ToolResponse.success(
            source_banner + note + data,
            repo_url=page.url,
            meta=ResponseMeta(
                elapsed_ms=elapsed,
                char_count=len(data),
                truncated=truncated,
                calls_remaining=rate_limit_remaining(validated.repo_url),
                source=page.source,
            ),
        ).to_text()
