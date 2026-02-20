"""Tool registration helpers for TinkyWiki MCP.

6 tools available:
  - tinkywiki_list_topics       — Legacy text overview (httpx)
  - tinkywiki_read_structure    — JSON TOC/sections list (httpx)
  - tinkywiki_read_contents     — Full or section-specific markdown (httpx)
  - tinkywiki_search_wiki       — Interactive chat Q&A (Playwright)
  - tinkywiki_request_indexing  — Submit repo for indexing (Playwright)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> None:
    """Register every TinkyWiki tool on the given MCP server."""
    # pylint: disable=import-outside-toplevel
    # Lazy imports avoid circular dependencies at module load time.
    from .contents import register as register_contents
    from .request_indexing import register as register_request_indexing
    from .search import register as register_search
    from .structure import register as register_structure
    from .topics import register as register_topics

    register_topics(mcp)
    register_structure(mcp)
    register_contents(mcp)
    register_search(mcp)
    register_request_indexing(mcp)
