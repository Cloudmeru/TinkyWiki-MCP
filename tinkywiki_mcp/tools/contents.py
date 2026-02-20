"""tinkywiki_read_contents tool — View full or section-specific documentation.

Uses Playwright to render the JS SPA, then BeautifulSoup to parse content.
Supports pagination to avoid overwhelming the context window.
"""

from __future__ import annotations

import logging
import time

from mcp.server.fastmcp import Context, FastMCP

from .. import config
from ..fallback import build_source_banner
from ..parser import get_section_by_title
from ..types import (
    ErrorCode,
    ResponseMeta,
    ToolResponse,
    validate_contents_input,
)
from ..rate_limit import rate_limit_remaining
from ._helpers import (
    build_resolution_note,
    fetch_page_or_error,
    pre_resolve_keyword,
    truncate_response,
)

logger = logging.getLogger("TinkyWiki")


def _build_section_content(
    page, section_title: str, repo_url: str
) -> str | ToolResponse:
    """Render one section or return a NO_CONTENT error response."""
    section = get_section_by_title(page, section_title)
    if section is None:
        available = [item.title for item in page.sections[:20]]
        return ToolResponse.error(
            ErrorCode.NO_CONTENT,
            f"Section '{section_title}' not found. "
            f"Available sections: {', '.join(available)}",
            repo_url=repo_url,
        )

    prefix = "#" * min(section.level + 1, 6)
    return f"{prefix} {section.title}\n\n{section.content}"


def _build_paginated_content(page, offset: int, limit: int) -> str:
    """Render paginated full-page content."""
    total = len(page.sections)
    sliced = page.sections[offset : offset + limit]
    has_more = (offset + limit) < total

    parts = [f"# {page.title}\n"]
    for section in sliced:
        prefix = "#" * min(section.level + 1, 6)
        parts.append(f"\n{prefix} {section.title}\n")
        if section.content:
            parts.append(section.content)

    if has_more:
        next_off = offset + limit
        parts.append(
            f"\n\n---\n*Showing sections {offset + 1}–"
            f"{offset + len(sliced)} of {total}. "
            f"Call again with `offset={next_off}` to continue.*"
        )

    return "\n".join(parts).strip()


def register(mcp: FastMCP) -> None:
    """Register the tinkywiki_read_contents tool on the MCP server."""

    @mcp.tool()
    def tinkywiki_read_contents(
        repo_url: str,
        ctx: Context,
        section_title: str = "",
        offset: int = 0,
        limit: int = 5,
    ) -> str:
        """
        View documentation about a GitHub repository from Google TinkyWiki.

        Without ``section_title``, returns the full wiki content (may be truncated).
        With ``section_title``, returns just that section's content.

        Use ``tinkywiki_read_structure`` first to see available sections.

        **Pagination** (when ``section_title`` is empty):
        - ``offset`` — section index to start from (default 0).
        - ``limit`` — max sections per response (default 5).
        The response includes ``has_more`` and ``next_offset`` when more
        sections are available, so you can call again to continue.

        **Response size**: 2–10 KB per section, 5–30 KB for paginated full page.
        Cached for 5 minutes — repeated calls are instant.

        **Rate limit**: max 10 calls per 60 s per repo URL. Duplicate
        concurrent calls are automatically deduplicated.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/facebook/react)
                      or shorthand owner/repo (e.g. facebook/react).
                      Bare keywords (e.g. 'react') are auto-resolved with
                      interactive disambiguation.
            section_title: Optional. Title (or partial title) of a specific section
                          to retrieve. If empty, returns the full wiki.
            offset: Section index to start from (0-based, default 0).
            limit: Maximum sections to return (default 5, max 50).
        """
        start = time.monotonic()
        logger.info(
            "tinkywiki_read_contents — repo: %s, section: %s, offset: %d, limit: %d",
            repo_url,
            section_title,
            offset,
            limit,
        )

        original_input = repo_url  # save before resolution
        repo_url = pre_resolve_keyword(repo_url, ctx)  # elicitation for bare keywords

        validated = validate_contents_input(repo_url, section_title, offset, limit)
        if isinstance(validated, ToolResponse):
            return validated.to_text()

        result = fetch_page_or_error(validated.repo_url)
        if isinstance(result, ToolResponse):
            return result.to_text()

        if validated.section_title.strip():
            content_or_error = _build_section_content(
                result,
                validated.section_title.strip(),
                validated.repo_url,
            )
            if isinstance(content_or_error, ToolResponse):
                return content_or_error.to_text()
            data = content_or_error
        else:
            data = _build_paginated_content(result, validated.offset, validated.limit)

        note = build_resolution_note(original_input, validated.repo_url)
        source_banner = build_source_banner(result.source) if result.source != "tinkywiki" else ""
        data, truncated = truncate_response(data, config.RESPONSE_MAX_CHARS)

        return ToolResponse.success(
            source_banner + note + data,
            repo_url=validated.repo_url,
            meta=ResponseMeta(
                elapsed_ms=int((time.monotonic() - start) * 1000),
                char_count=len(data),
                truncated=truncated,
                calls_remaining=rate_limit_remaining(validated.repo_url),
                source=result.source,
            ),
        ).to_text()
