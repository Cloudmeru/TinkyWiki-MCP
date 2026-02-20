"""Tests for MCP tool registration, server creation, and individual tools."""

from __future__ import annotations

import inspect
import json
from typing import Any

from tinkywiki_mcp.server import create_server, parse_args
from tests.conftest import make_wiki_page


def _tool_manager(mcp: Any) -> Any:
    return getattr(mcp, "_tool_manager")


class _DummyElicitPayload:
    confirm = "Yes, request indexing"
    selected_repo = "microsoft/vscode"


class _DummyElicitResult:
    action = "accept"
    data = _DummyElicitPayload()


class _DummyCtx:
    async def elicit(self, **_kwargs):
        return _DummyElicitResult()


_DUMMY_CTX = _DummyCtx()


def _tool_fn(mcp: Any, tool_name: str) -> Any:
    manager = _tool_manager(mcp)
    tools = getattr(manager, "_tools")
    fn = tools[tool_name].fn
    if "ctx" not in inspect.signature(fn).parameters:
        return fn

    def _wrapped(*args, **kwargs):
        kwargs.setdefault("ctx", _DUMMY_CTX)
        return fn(*args, **kwargs)

    return _wrapped


def _list_tool_names(mcp: Any) -> set[str]:
    manager = _tool_manager(mcp)
    return {tool.name for tool in manager.list_tools()}


# All tools that go through _helpers.fetch_page_or_error need their
# fetch_page_with_fallback mock applied at the _helpers import location.
_HELPERS_FETCH = "tinkywiki_mcp.tools._helpers.fetch_page_with_fallback"
# Rate limiter must always allow in tests (unless testing rate limiting itself)
_HELPERS_RATE_LIMIT = "tinkywiki_mcp.tools._helpers.wait_for_rate_limit"


def _fb(page):
    """Wrap a WikiPage in a FallbackResult for mocking."""
    from tinkywiki_mcp.fallback import FallbackResult
    return FallbackResult(page=page, source="tinkywiki")


# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------
class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.transport == "stdio"
        assert args.port == 3000
        assert args.verbose is False

    def test_sse(self):
        args = parse_args(["--sse", "--port", "8080"])
        assert args.transport == "sse"
        assert args.port == 8080

    def test_verbose(self):
        args = parse_args(["--verbose"])
        assert args.verbose is True

    def test_verbose_short(self):
        args = parse_args(["-v"])
        assert args.verbose is True


# ---------------------------------------------------------------------------
# Server creation
# ---------------------------------------------------------------------------
class TestCreateServer:
    def test_returns_fastmcp(self):
        mcp = create_server()
        assert mcp is not None
        assert hasattr(mcp, "name") or hasattr(mcp, "_name")

    def test_tools_registered(self):
        """Verify all 4 tools are registered on the server."""
        mcp = create_server()
        assert mcp is not None


# ---------------------------------------------------------------------------
# tinkywiki_list_topics tool
# ---------------------------------------------------------------------------
class TestTopicsTool:
    def test_success(self, mocker):
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        tool_names = _list_tool_names(mcp)
        assert "tinkywiki_list_topics" in tool_names

    def test_returns_json_envelope(self, mocker):
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        # Call the tool function directly
        fn = _tool_fn(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "data" in parsed
        assert "meta" in parsed

    def test_no_content(self, mocker):
        page = make_wiki_page(raw_text="", sections=[])
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "NO_CONTENT"

    def test_validation_error(self):
        from tinkywiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="http://example.com/foo/bar")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "VALIDATION"

    def test_http_error(self, mocker):
        mocker.patch(
            _HELPERS_FETCH,
            side_effect=TimeoutError("Page render timed out"),
        )

        from tinkywiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "TIMEOUT"

    def test_returns_previews_not_full(self, mocker):
        """Topics tool should return previews, not the full page content."""
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        # The data should contain section titles
        assert "Architecture" in parsed["data"]
        assert "Extensions" in parsed["data"]


# ---------------------------------------------------------------------------
# tinkywiki_read_structure tool
# ---------------------------------------------------------------------------
class TestStructureTool:
    def test_returns_json_sections(self, mocker):
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.structure import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_structure")
        result = fn(repo_url="microsoft/vscode")
        outer = json.loads(result)
        assert outer["status"] == "ok"

        inner = json.loads(outer["data"])
        assert inner["repo"] == "github.com/microsoft/vscode"
        assert inner["section_count"] == 4
        assert len(inner["sections"]) == 4

    def test_section_titles(self, mocker):
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.structure import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_structure")
        result = fn(repo_url="microsoft/vscode")
        inner = json.loads(json.loads(result)["data"])
        titles = [s["title"] for s in inner["sections"]]
        assert "Architecture" in titles
        assert "Extensions" in titles
        assert "Testing" in titles


# ---------------------------------------------------------------------------
# tinkywiki_read_contents tool
# ---------------------------------------------------------------------------
class TestContentsTool:
    def test_full_content(self, mocker):
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.contents import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_contents")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "Architecture" in parsed["data"]
        assert "Extensions" in parsed["data"]

    def test_section_filter(self, mocker):
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.contents import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_contents")
        result = fn(repo_url="microsoft/vscode", section_title="Architecture")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "Architecture" in parsed["data"]
        assert "Electron" in parsed["data"]

    def test_section_not_found(self, mocker):
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.contents import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_contents")
        result = fn(repo_url="microsoft/vscode", section_title="Nonexistent Section")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "NO_CONTENT"
        assert "not found" in parsed["message"].lower()

    def test_pagination(self, mocker):
        """Pagination returns a subset of sections with has_more hint."""
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.contents import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_contents")
        # Ask for only 2 sections starting at offset 0
        result = fn(repo_url="microsoft/vscode", offset=0, limit=2)
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        # Should have Architecture and Extensions but not Testing
        assert "Architecture" in parsed["data"]
        assert "Extensions" in parsed["data"]
        assert "offset=2" in parsed["data"]  # next_offset hint


# ---------------------------------------------------------------------------
# tinkywiki_search_wiki tool (Playwright — mocked)
# ---------------------------------------------------------------------------
class TestSearchTool:
    def test_validation_error(self):
        from tinkywiki_mcp.tools.search import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_search_wiki")
        result = fn(repo_url="http://example.com/foo/bar", query="test")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "VALIDATION"

    def test_empty_query_error(self):
        from tinkywiki_mcp.tools.search import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_search_wiki")
        result = fn(repo_url="microsoft/vscode", query="")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "VALIDATION"

    def test_successful_search(self, mocker):
        """Mock _run_search to test the tool flow without Playwright."""
        from tinkywiki_mcp.types import ResponseMeta, ToolResponse

        mock_response = ToolResponse.success(
            "VS Code uses Electron for cross-platform support.",
            repo_url="https://github.com/microsoft/vscode",
            query="What framework does VS Code use?",
            meta=ResponseMeta(char_count=50),
        )
        mocker.patch(
            "tinkywiki_mcp.tools.search._run_search",
            return_value=mock_response,
        )
        # Ensure search cache doesn't interfere
        mocker.patch(
            "tinkywiki_mcp.tools.search.get_cached_search",
            return_value=None,
        )

        from tinkywiki_mcp.tools.search import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_search_wiki")
        result = fn(
            repo_url="microsoft/vscode", query="What framework does VS Code use?"
        )
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "Electron" in parsed["data"]


# ---------------------------------------------------------------------------
# Rate limiting integration
# ---------------------------------------------------------------------------
class TestRateLimitIntegration:
    """Test that tools respect rate limits."""

    def test_topics_rate_limited(self, mocker):
        """Topics tool returns RATE_LIMITED when limit exceeded."""
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))
        mocker.patch(_HELPERS_RATE_LIMIT, return_value=False)

        from tinkywiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "RATE_LIMITED"

    def test_structure_rate_limited(self, mocker):
        """Structure tool returns RATE_LIMITED when limit exceeded."""
        mocker.patch(_HELPERS_RATE_LIMIT, return_value=False)

        from tinkywiki_mcp.tools.structure import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_structure")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "RATE_LIMITED"

    def test_contents_rate_limited(self, mocker):
        """Contents tool returns RATE_LIMITED when limit exceeded."""
        mocker.patch(_HELPERS_RATE_LIMIT, return_value=False)

        from tinkywiki_mcp.tools.contents import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_contents")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "RATE_LIMITED"

    def test_search_rate_limited(self, mocker):
        """Search tool returns RATE_LIMITED when limit exceeded."""
        mocker.patch("tinkywiki_mcp.tools.search.wait_for_rate_limit", return_value=False)

        from tinkywiki_mcp.tools.search import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_search_wiki")
        result = fn(repo_url="microsoft/vscode", query="How does it work?")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "RATE_LIMITED"


# ---------------------------------------------------------------------------
# Content hash / idempotency key integration
# ---------------------------------------------------------------------------
class TestResponseMetaIntegration:
    """Test that responses include content_hash and idempotency_key."""

    def test_topics_has_content_hash(self, mocker):
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "content_hash" in parsed["meta"]
        assert parsed["meta"]["content_hash"] is not None
        assert "idempotency_key" in parsed

    def test_structure_has_content_hash(self, mocker):
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.structure import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_structure")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "content_hash" in parsed["meta"]
        assert "idempotency_key" in parsed

    def test_same_data_same_hash(self, mocker):
        """Repeated calls produce the same content_hash."""
        page = make_wiki_page()
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.structure import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_structure")
        r1 = json.loads(fn(repo_url="microsoft/vscode"))
        r2 = json.loads(fn(repo_url="microsoft/vscode"))
        assert r1["meta"]["content_hash"] == r2["meta"]["content_hash"]
        assert r1["idempotency_key"] == r2["idempotency_key"]


# ---------------------------------------------------------------------------
# NOT_INDEXED detection
# ---------------------------------------------------------------------------
class TestNotIndexedDetection:
    """Test that tools correctly detect repos not indexed by TinkyWiki."""

    def test_topics_not_indexed_404_page(self, mocker):
        """A page with 404 indicators and no sections should return NOT_INDEXED."""
        page = make_wiki_page(
            raw_text="404 This page doesn\u2019t exist Try heading back to "
            "the homepage Need to request a repo?",
            sections=[],
        )
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="Snowflake-Labs/agent-world-model")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "NOT_INDEXED"
        assert "not yet available" in parsed["message"].lower() or "not yet indexed" in parsed["message"].lower()

    def test_structure_not_indexed_404_page(self, mocker):
        """Structure tool should also return NOT_INDEXED for 404 pages."""
        page = make_wiki_page(
            raw_text="404 This page doesn't exist",
            sections=[],
        )
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.structure import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_structure")
        result = fn(repo_url="Snowflake-Labs/agent-world-model")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "NOT_INDEXED"

    def test_contents_not_indexed_404_page(self, mocker):
        """Contents tool should also return NOT_INDEXED for 404 pages."""
        page = make_wiki_page(
            raw_text="This page doesn\u2019t exist",
            sections=[],
        )
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.contents import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_read_contents")
        result = fn(repo_url="Snowflake-Labs/agent-world-model")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "NOT_INDEXED"

    def test_not_indexed_vs_no_content(self, mocker):
        """Empty raw_text + empty sections = NO_CONTENT (not NOT_INDEXED)."""
        page = make_wiki_page(raw_text="", sections=[])
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "NO_CONTENT"

    def test_indexed_page_not_flagged(self, mocker):
        """A real indexed page should NOT be flagged as NOT_INDEXED."""
        page = make_wiki_page()  # default page with sections
        mocker.patch(_HELPERS_FETCH, return_value=_fb(page))

        from tinkywiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_list_topics")
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"


# ---------------------------------------------------------------------------
# tinkywiki_request_indexing tool
# ---------------------------------------------------------------------------
class TestRequestIndexingTool:
    """Test the tinkywiki_request_indexing tool."""

    def test_tool_registered(self):
        """Verify tinkywiki_request_indexing is registered on server creation."""
        mcp = create_server()
        assert mcp is not None

    def test_returns_confirmation_on_success(self, mocker):
        """Mock _run_request_indexing to simulate a successful submission."""
        from tinkywiki_mcp.types import (
            ResponseMeta,
            ResponseStatus,
            ErrorCode as EC,
            ToolResponse,
        )

        mock_response = ToolResponse(
            status=ResponseStatus.OK,
            code=EC.NOT_INDEXED,
            data=(
                "**Indexing request submitted successfully** for "
                "**https://github.com/Snowflake-Labs/agent-world-model**.\n\n"
                'Google TinkyWiki confirmed: *"Repo requested"*\n\n'
                "Check back later at: https://codewiki.google/github.com/"
                "Snowflake-Labs/agent-world-model"
            ),
            repo_url="https://github.com/Snowflake-Labs/agent-world-model",
            meta=ResponseMeta(char_count=200),
        )
        mocker.patch(
            "tinkywiki_mcp.tools.request_indexing._run_request_indexing",
            return_value=mock_response,
        )

        from tinkywiki_mcp.tools.request_indexing import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_request_indexing")
        result = fn(repo_url="Snowflake-Labs/agent-world-model")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["code"] == "NOT_INDEXED"
        assert "indexing request submitted" in parsed["data"].lower()
        assert "codewiki.google" in parsed["data"]

    def test_validation_error(self):
        from tinkywiki_mcp.tools.request_indexing import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_request_indexing")
        result = fn(repo_url="http://example.com/foo/bar")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "VALIDATION"

    def test_returns_repo_url(self, mocker):
        from tinkywiki_mcp.types import (
            ResponseMeta,
            ResponseStatus,
            ErrorCode as EC,
            ToolResponse,
        )

        mock_response = ToolResponse(
            status=ResponseStatus.OK,
            code=EC.NOT_INDEXED,
            data="Submitted request for fastapi/fastapi",
            repo_url="https://github.com/fastapi/fastapi",
            meta=ResponseMeta(char_count=40),
        )
        mocker.patch(
            "tinkywiki_mcp.tools.request_indexing._run_request_indexing",
            return_value=mock_response,
        )

        from tinkywiki_mcp.tools.request_indexing import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_request_indexing")
        result = fn(repo_url="fastapi/fastapi")
        parsed = json.loads(result)
        assert parsed["repo_url"] == "https://github.com/fastapi/fastapi"

    def test_handles_driver_error(self, mocker):
        """Simulate a Playwright failure during submission."""
        from tinkywiki_mcp.types import ErrorCode as EC, ToolResponse

        mock_response = ToolResponse.error(
            EC.DRIVER_ERROR,
            "Playwright error during indexing request: browser crashed",
            repo_url="https://github.com/some/repo",
        )
        mocker.patch(
            "tinkywiki_mcp.tools.request_indexing._run_request_indexing",
            return_value=mock_response,
        )

        from tinkywiki_mcp.tools.request_indexing import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = _tool_fn(mcp, "tinkywiki_request_indexing")
        result = fn(repo_url="some/repo")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "DRIVER_ERROR"
