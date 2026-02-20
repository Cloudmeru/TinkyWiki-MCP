"""Tests for keyword resolution integration across all MCP tools (post-v1.1.0).

All tools gained: ctx parameter, pre_resolve_keyword() call, and
build_resolution_note() in responses.  These tests verify the integration
without hitting Playwright by mocking at the _helpers level.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tinkywiki_mcp.fallback import FallbackResult
from tinkywiki_mcp.server import create_server
from tests.conftest import make_wiki_page


def _fb(page):
    """Wrap a WikiPage in a FallbackResult for mocking."""
    return FallbackResult(page=page, source="tinkywiki")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
_HELPERS_FETCH = "tinkywiki_mcp.tools._helpers.fetch_page_with_fallback"
_HELPERS_RATE = "tinkywiki_mcp.tools._helpers.wait_for_rate_limit"
_HELPERS_PRE_RESOLVE = "tinkywiki_mcp.tools._helpers.pre_resolve_keyword"


class _DummyCtx:
    """Minimal MCP Context stub for elicitation."""

    async def elicit(self, **_kw):
        return SimpleNamespace(
            action="accept",
            data=SimpleNamespace(selected_repo="vuejs/vue"),
        )


def _get_tool(mcp, name):
    """Return the callable for a registered MCP tool."""
    manager = getattr(mcp, "_tool_manager")
    tools = getattr(manager, "_tools")
    return tools[name].fn


# ---------------------------------------------------------------------------
# tinkywiki_list_topics — keyword resolution
# ---------------------------------------------------------------------------
class TestTopicsKeywordResolution:
    def test_bare_keyword_resolved_and_note_prepended(self, mocker):
        """Bare keyword 'vue' → resolved to vuejs/vue, note in output."""
        mocker.patch(
            "tinkywiki_mcp.tools.topics.pre_resolve_keyword",
            return_value="vuejs/vue",
        )
        mocker.patch(
            "tinkywiki_mcp.tools.topics.build_resolution_note",
            return_value='> **Resolved:** keyword "vue" → **vuejs/vue**\n',
        )
        page = make_wiki_page(
            repo_name="github.com/vuejs/vue",
            url="https://codewiki.google/github.com/vuejs/vue",
        )
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))
        mocker.patch(_HELPERS_RATE, return_value=True)

        mcp = create_server()
        fn = _get_tool(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="vue", ctx=_DummyCtx())
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "Resolved" in parsed["data"]

    def test_owner_repo_no_resolution_note(self, mocker):
        """Owner/repo input should not produce a resolution note."""
        mocker.patch(
            "tinkywiki_mcp.tools.topics.pre_resolve_keyword",
            side_effect=lambda raw, ctx=None: raw,
        )
        mocker.patch(
            "tinkywiki_mcp.tools.topics.build_resolution_note",
            return_value="",
        )
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))
        mocker.patch(_HELPERS_RATE, return_value=True)

        mcp = create_server()
        fn = _get_tool(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="microsoft/vscode", ctx=_DummyCtx())
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "Resolved" not in parsed["data"]


# ---------------------------------------------------------------------------
# tinkywiki_read_structure — keyword resolution
# ---------------------------------------------------------------------------
class TestStructureKeywordResolution:
    def test_bare_keyword_resolved(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.tools.structure.pre_resolve_keyword",
            return_value="vuejs/vue",
        )
        mocker.patch(
            "tinkywiki_mcp.tools.structure.build_resolution_note",
            return_value='> **Resolved:** "vue" → **vuejs/vue**\n',
        )
        page = make_wiki_page(
            repo_name="github.com/vuejs/vue",
            url="https://codewiki.google/github.com/vuejs/vue",
        )
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))
        mocker.patch(_HELPERS_RATE, return_value=True)

        mcp = create_server()
        fn = _get_tool(mcp, "tinkywiki_read_structure")
        result = fn(repo_url="vue", ctx=_DummyCtx())
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "Resolved" in parsed["data"]


# ---------------------------------------------------------------------------
# tinkywiki_read_contents — keyword resolution
# ---------------------------------------------------------------------------
class TestContentsKeywordResolution:
    def test_bare_keyword_resolved(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.tools.contents.pre_resolve_keyword",
            return_value="vuejs/vue",
        )
        mocker.patch(
            "tinkywiki_mcp.tools.contents.build_resolution_note",
            return_value='> **Resolved:** "vue" → **vuejs/vue**\n',
        )
        page = make_wiki_page(
            repo_name="github.com/vuejs/vue",
            url="https://codewiki.google/github.com/vuejs/vue",
        )
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))
        mocker.patch(_HELPERS_RATE, return_value=True)

        mcp = create_server()
        fn = _get_tool(mcp, "tinkywiki_read_contents")
        result = fn(repo_url="vue", ctx=_DummyCtx())
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "Resolved" in parsed["data"]


# ---------------------------------------------------------------------------
# tinkywiki_search_wiki — keyword resolution
# ---------------------------------------------------------------------------
class TestSearchKeywordResolution:
    def test_bare_keyword_resolved_with_cached_search(self, mocker):
        """Keyword resolution + cached search result → note in output."""
        mocker.patch(
            "tinkywiki_mcp.tools.search.pre_resolve_keyword",
            return_value="vuejs/vue",
        )
        mocker.patch(
            "tinkywiki_mcp.tools.search.build_resolution_note",
            return_value='> **Resolved:** "vue" → **vuejs/vue**\n',
        )
        mocker.patch(
            "tinkywiki_mcp.tools.search.get_cached_search",
            return_value="Vue is a progressive JS framework.",
        )
        mocker.patch(_HELPERS_RATE, return_value=True)

        mcp = create_server()
        fn = _get_tool(mcp, "tinkywiki_search_wiki")
        result = fn(repo_url="vue", query="What is Vue?", ctx=_DummyCtx())
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "Resolved" in parsed["data"]

    def test_ctx_optional_for_search(self, mocker):
        """tinkywiki_search_wiki has ctx as optional (ctx: Context | None)."""
        mocker.patch(
            "tinkywiki_mcp.tools.search.pre_resolve_keyword",
            side_effect=lambda raw, ctx=None: raw,
        )
        mocker.patch(
            "tinkywiki_mcp.tools.search.build_resolution_note",
            return_value="",
        )
        mocker.patch(
            "tinkywiki_mcp.tools.search.get_cached_search",
            return_value="cached answer",
        )
        mocker.patch(_HELPERS_RATE, return_value=True)

        mcp = create_server()
        fn = _get_tool(mcp, "tinkywiki_search_wiki")
        # Call without ctx
        result = fn(repo_url="microsoft/vscode", query="architecture")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"


# ---------------------------------------------------------------------------
# All tools have ctx in their signature
# ---------------------------------------------------------------------------
class TestAllToolsHaveCtx:
    def test_ctx_parameter_present(self):
        """Every tool should accept a ctx parameter."""
        import inspect

        mcp = create_server()
        manager = getattr(mcp, "_tool_manager")
        tools = getattr(manager, "_tools")
        for name, tool in tools.items():
            sig = inspect.signature(tool.fn)
            assert "ctx" in sig.parameters, (
                f"Tool '{name}' is missing 'ctx' parameter"
            )
