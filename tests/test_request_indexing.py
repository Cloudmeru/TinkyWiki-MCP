"""Tests for tinkywiki_request_indexing — post-v1.1.0 elicitation & keyword changes.

Covers: _IndexingConfirmation model, _elicit_indexing_confirmation,
_build_search_url, helper response builders, _is_confirmed,
_build_outcome_message, and the register wrapper (keyword resolution +
confirmation elicitation flow).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tinkywiki_mcp.tools.request_indexing import (
    _IndexingConfirmation,
    _build_outcome_message,
    _build_search_url,
    _dialog_input_missing_response,
    _elicit_indexing_confirmation,
    _request_button_missing_response,
    _submit_failed_response,
)
from tinkywiki_mcp.types import ErrorCode


# ---------------------------------------------------------------------------
# _IndexingConfirmation Pydantic model
# ---------------------------------------------------------------------------
class TestIndexingConfirmation:
    def test_accept_literal(self):
        m = _IndexingConfirmation(confirm="Yes, request indexing")
        assert m.confirm == "Yes, request indexing"

    def test_reject_literal(self):
        m = _IndexingConfirmation(confirm="No, skip indexing")
        assert m.confirm == "No, skip indexing"

    def test_invalid_choice_raises(self):
        with pytest.raises(Exception):
            _IndexingConfirmation(confirm="Maybe later")


# ---------------------------------------------------------------------------
# _build_search_url
# ---------------------------------------------------------------------------
class TestBuildSearchUrl:
    def test_github_url(self):
        url = _build_search_url("https://github.com/microsoft/vscode")
        assert "codewiki.google" in url
        assert "microsoft%2Fvscode" in url

    def test_shorthand_url(self):
        url = _build_search_url("microsoft/vscode")
        assert "microsoft%2Fvscode" in url


# ---------------------------------------------------------------------------
# _elicit_indexing_confirmation (async)
# ---------------------------------------------------------------------------
class TestElicitIndexingConfirmation:
    @pytest.mark.asyncio
    async def test_accept_yes(self):
        class _Ctx:
            async def elicit(self, **_kw):
                return SimpleNamespace(
                    action="accept",
                    data=SimpleNamespace(confirm="Yes, request indexing"),
                )

        confirmed = await _elicit_indexing_confirmation("https://github.com/o/r", _Ctx())
        assert confirmed is True

    @pytest.mark.asyncio
    async def test_accept_no(self):
        class _Ctx:
            async def elicit(self, **_kw):
                return SimpleNamespace(
                    action="accept",
                    data=SimpleNamespace(confirm="No, skip indexing"),
                )

        confirmed = await _elicit_indexing_confirmation("https://github.com/o/r", _Ctx())
        assert confirmed is False

    @pytest.mark.asyncio
    async def test_cancel(self):
        class _Ctx:
            async def elicit(self, **_kw):
                return SimpleNamespace(action="cancel", data=None)

        confirmed = await _elicit_indexing_confirmation("https://github.com/o/r", _Ctx())
        assert confirmed is False

    @pytest.mark.asyncio
    async def test_accept_with_dict_data(self):
        """Handle data returned as dict (some MCP client implementations)."""

        class _Ctx:
            async def elicit(self, **_kw):
                return SimpleNamespace(
                    action="accept",
                    data={"confirm": "Yes, request indexing"},
                )

        confirmed = await _elicit_indexing_confirmation("https://github.com/o/r", _Ctx())
        assert confirmed is True


# ---------------------------------------------------------------------------
# Response builder helpers
# ---------------------------------------------------------------------------
class TestResponseBuilders:
    def test_request_button_missing(self):
        resp = _request_button_missing_response(
            "https://github.com/o/r", "https://search-url"
        )
        assert resp.code == ErrorCode.NOT_INDEXED
        assert "Request repository" in resp.data

    def test_dialog_input_missing(self):
        resp = _dialog_input_missing_response(
            "https://github.com/o/r", "https://search-url"
        )
        assert resp.code == ErrorCode.NOT_INDEXED
        assert "input field" in resp.data

    def test_submit_failed(self):
        resp = _submit_failed_response(
            "https://github.com/o/r", "https://search-url", RuntimeError("fail")
        )
        assert "Submit" in resp.data
        assert "fail" in resp.data


# ---------------------------------------------------------------------------
# _build_outcome_message
# ---------------------------------------------------------------------------
class TestBuildOutcomeMessage:
    def test_confirmed_message(self):
        msg = _build_outcome_message(
            "https://github.com/o/r", "https://search", confirmed=True
        )
        assert "submitted successfully" in msg
        assert "codewiki.google" in msg

    def test_unconfirmed_message(self):
        msg = _build_outcome_message(
            "https://github.com/o/r", "https://search", confirmed=False
        )
        assert "could not confirm" in msg
        assert "submit manually" in msg


# ---------------------------------------------------------------------------
# Tool registration: keyword resolution & elicitation flow
# ---------------------------------------------------------------------------
class TestRequestIndexingTool:
    def test_validation_error_returns_json(self, mocker):
        """Invalid URL returns a proper ToolResponse JSON."""
        from tinkywiki_mcp.server import create_server

        mocker.patch(
            "tinkywiki_mcp.tools._helpers.resolve_keyword_interactive",
            return_value=(None, []),
        )

        mcp = create_server()
        manager = getattr(mcp, "_tool_manager")
        tools = getattr(manager, "_tools")
        fn = tools["tinkywiki_request_indexing"].fn

        class _DummyCtx:
            async def elicit(self, **_kw):
                return SimpleNamespace(action="accept", data=SimpleNamespace(confirm="Yes, request indexing"))

        result = fn(repo_url="http://example.com/foo/bar", ctx=_DummyCtx())
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "VALIDATION"

    def test_keyword_resolution_called(self, mocker):
        """Bare keyword triggers pre_resolve_keyword before validation."""
        from tinkywiki_mcp.server import create_server

        resolve_mock = mocker.patch(
            "tinkywiki_mcp.tools.request_indexing.pre_resolve_keyword",
            return_value="microsoft/vscode",
        )
        # Mock out everything after validation so we don't hit Playwright
        mocker.patch(
            "tinkywiki_mcp.tools.request_indexing.from_thread.run",
            return_value=True,  # confirm=True
        )
        mocker.patch(
            "tinkywiki_mcp.tools.request_indexing._run_request_indexing",
            return_value=__import__("tinkywiki_mcp.types", fromlist=["ToolResponse"]).ToolResponse.success(
                "Indexing submitted", repo_url="https://github.com/microsoft/vscode"
            ),
        )

        mcp = create_server()
        manager = getattr(mcp, "_tool_manager")
        tools = getattr(manager, "_tools")
        fn = tools["tinkywiki_request_indexing"].fn

        class _DummyCtx:
            async def elicit(self, **_kw):
                return SimpleNamespace(action="accept", data=SimpleNamespace(confirm="Yes, request indexing"))

        fn(repo_url="vscode", ctx=_DummyCtx())
        resolve_mock.assert_called_once_with("vscode", mocker.ANY)

    def test_confirmation_declined_skips_indexing(self, mocker):
        """User declining confirmation returns skip message without hitting Playwright."""
        from tinkywiki_mcp.server import create_server

        mocker.patch(
            "tinkywiki_mcp.tools.request_indexing.pre_resolve_keyword",
            side_effect=lambda raw, ctx=None: raw,
        )
        mocker.patch(
            "tinkywiki_mcp.tools.request_indexing.from_thread.run",
            return_value=False,  # user declined
        )
        run_mock = mocker.patch(
            "tinkywiki_mcp.tools.request_indexing._run_request_indexing"
        )

        mcp = create_server()
        manager = getattr(mcp, "_tool_manager")
        tools = getattr(manager, "_tools")
        fn = tools["tinkywiki_request_indexing"].fn

        class _DummyCtx:
            async def elicit(self, **_kw):
                return SimpleNamespace(action="cancel", data=None)

        result = fn(repo_url="microsoft/vscode", ctx=_DummyCtx())
        parsed = json.loads(result)
        assert "skipped" in parsed["data"].lower()
        # Should NOT call _run_request_indexing
        run_mock.assert_not_called()
