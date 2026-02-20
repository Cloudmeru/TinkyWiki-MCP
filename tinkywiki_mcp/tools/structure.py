"""tinkywiki_read_structure tool — Lightweight JSON table of contents.

The most token-efficient tool — returns structured metadata only.
Always call this first to discover section titles before reading content.
"""

from __future__ import annotations

import json
import logging
import time

from mcp.server.fastmcp import Context, FastMCP

from ..fallback import build_source_banner
from ..types import ResponseMeta, ToolResponse
from ..rate_limit import rate_limit_remaining
from ._helpers import build_resolution_note, fetch_page_or_error, pre_resolve_keyword

logger = logging.getLogger("TinkyWiki")


def register(mcp: FastMCP) -> None:
    """Register the tinkywiki_read_structure tool on the MCP server."""

    @mcp.tool()
    def tinkywiki_read_structure(repo_url: str, ctx: Context) -> str:
        """
        Get a list of documentation topics for a repository from Google TinkyWiki.

        Returns the table of contents / section structure as a JSON list so you
        can choose which sections to read with ``tinkywiki_read_contents``.

        **Recommended first step** — call this before ``tinkywiki_read_contents``
        or ``tinkywiki_list_topics`` to discover available sections without
        consuming many tokens.

        **Response size**: typically 1–3 KB (lightweight JSON).
        Cached for 5 minutes — repeated calls are instant.

        **Rate limit**: max 10 calls per 60 s per repo URL. Duplicate
        concurrent calls are automatically deduplicated.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/facebook/react)
                      or shorthand owner/repo (e.g. facebook/react).
                      Bare keywords (e.g. 'react') are auto-resolved with
                      interactive disambiguation.
        """
        start = time.monotonic()
        logger.info("tinkywiki_read_structure — repo: %s", repo_url)

        original_input = repo_url  # save before resolution
        repo_url = pre_resolve_keyword(repo_url, ctx)  # elicitation for bare keywords

        result = fetch_page_or_error(repo_url)
        if isinstance(result, ToolResponse):
            return result.to_text()

        page = result
        source_banner = build_source_banner(page.source) if page.source != "tinkywiki" else ""

        # Build structured TOC
        structure = {
            "repo": page.repo_name,
            "title": page.title,
            "source": page.source,
            "sections": [{"title": s.title, "level": s.level} for s in page.sections],
            "section_count": len(page.sections),
        }

        data = json.dumps(structure, indent=2)
        note = build_resolution_note(original_input, page.url)
        elapsed = int((time.monotonic() - start) * 1000)

        return ToolResponse.success(
            source_banner + note + data,
            repo_url=page.url,
            meta=ResponseMeta(
                elapsed_ms=elapsed,
                char_count=len(data),
                calls_remaining=rate_limit_remaining(page.url),
                source=page.source,
            ),
        ).to_text()
