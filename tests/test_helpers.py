"""Tests for tinkywiki_mcp.tools._helpers — post-v1.1.0 additions.

Covers: pre_resolve_keyword, build_resolution_note, build_tinkywiki_url,
truncate_response, _is_not_indexed, fetch_page_or_error, _validate_fetched_page.
"""

from __future__ import annotations

import pytest

from tinkywiki_mcp.parser import WikiPage, WikiSection
from tinkywiki_mcp.tools._helpers import (
    _is_not_indexed,
    _validate_fetched_page,
    build_tinkywiki_url,
    build_resolution_note,
    fetch_page_or_error,
    pre_resolve_keyword,
    truncate_response,
)
from tinkywiki_mcp.types import ErrorCode, ToolResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_page(*, sections=None, raw_text="some content") -> WikiPage:
    return WikiPage(
        repo_name="github.com/owner/repo",
        url="https://codewiki.google/github.com/owner/repo",
        title="Repo",
        sections=sections or [],
        toc=[],
        diagrams=[],
        raw_text=raw_text,
    )


def _sr(owner: str, repo: str, stars: int = 0):
    from tinkywiki_mcp.resolver import SearchResult

    return SearchResult(
        owner=owner,
        repo=repo,
        description=f"{owner}/{repo}",
        stars=stars,
        tinkywiki_url=f"https://codewiki.google/github.com/{owner}/{repo}",
    )


# ---------------------------------------------------------------------------
# build_tinkywiki_url
# ---------------------------------------------------------------------------
class TestBuildTinkyWikiUrl:
    def test_https_url(self):
        assert build_tinkywiki_url("https://github.com/microsoft/vscode") == (
            "https://codewiki.google/github.com/microsoft/vscode"
        )

    def test_http_url(self):
        assert build_tinkywiki_url("http://github.com/owner/repo") == (
            "https://codewiki.google/github.com/owner/repo"
        )

    def test_already_plain(self):
        assert build_tinkywiki_url("github.com/owner/repo") == (
            "https://codewiki.google/github.com/owner/repo"
        )


# ---------------------------------------------------------------------------
# truncate_response
# ---------------------------------------------------------------------------
class TestTruncateResponse:
    def test_no_truncation_when_short(self):
        text, trunc = truncate_response("short", max_chars=100)
        assert text == "short"
        assert trunc is False

    def test_no_truncation_when_zero_limit(self):
        text, trunc = truncate_response("any text", max_chars=0)
        assert text == "any text"
        assert trunc is False

    def test_truncates_at_newline(self):
        data = "line1\nline2\nline3\nline4\nline5"
        text, trunc = truncate_response(data, max_chars=20)
        assert trunc is True
        assert "... [truncated]" in text
        # Should cut at a newline boundary
        assert len(text) < len(data) + 20

    def test_truncates_at_space_fallback(self):
        data = "word " * 50  # 250 chars, no natural newlines
        text, trunc = truncate_response(data, max_chars=30)
        assert trunc is True
        assert "... [truncated]" in text


# ---------------------------------------------------------------------------
# _is_not_indexed
# ---------------------------------------------------------------------------
class TestIsNotIndexed:
    def test_page_with_sections_is_indexed(self):
        page = _make_page(
            sections=[WikiSection(title="Topic", level=2, content="stuff")],
            raw_text="This page doesn't exist",
        )
        assert _is_not_indexed(page) is False

    def test_empty_page_with_not_found_text(self):
        page = _make_page(
            sections=[], raw_text="This page doesn't exist. Request a repo."
        )
        assert _is_not_indexed(page) is True

    def test_empty_page_with_normal_text(self):
        page = _make_page(sections=[], raw_text="Some unrelated text")
        assert _is_not_indexed(page) is False


# ---------------------------------------------------------------------------
# pre_resolve_keyword
# ---------------------------------------------------------------------------
class TestPreResolveKeyword:
    def test_url_passthrough(self):
        url = "https://github.com/microsoft/vscode"
        assert pre_resolve_keyword(url) == url

    def test_owner_repo_passthrough(self):
        assert pre_resolve_keyword("microsoft/vscode") == "microsoft/vscode"

    def test_bare_keyword_resolved(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.resolve_keyword_interactive",
            return_value=("vuejs/vue", [_sr("vuejs", "vue", 200_000)]),
        )
        assert pre_resolve_keyword("vue") == "vuejs/vue"

    def test_bare_keyword_not_resolved_returns_original(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.resolve_keyword_interactive",
            return_value=(None, []),
        )
        assert pre_resolve_keyword("xyznonexistent") == "xyznonexistent"

    def test_ctx_forwarded(self, mocker):
        mock = mocker.patch(
            "tinkywiki_mcp.tools._helpers.resolve_keyword_interactive",
            return_value=("a/b", []),
        )
        sentinel = object()
        pre_resolve_keyword("vue", ctx=sentinel)
        mock.assert_called_once_with("vue", sentinel)


# ---------------------------------------------------------------------------
# build_resolution_note
# ---------------------------------------------------------------------------
class TestBuildResolutionNote:
    def test_non_keyword_returns_empty(self, mocker):
        assert build_resolution_note("microsoft/vscode", "https://github.com/microsoft/vscode") == ""

    def test_keyword_with_results(self, mocker):
        results = [_sr("vuejs", "vue", 209_900), _sr("vuejs", "core", 52_000)]
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.resolve_keyword",
            return_value=("vuejs/vue", results),
        )
        note = build_resolution_note("vue", "https://github.com/vuejs/vue")
        assert "vuejs/vue" in note
        assert "Resolved" in note
        assert "209,900" in note

    def test_keyword_with_other_candidates(self, mocker):
        results = [
            _sr("vuejs", "vue", 200_000),
            _sr("vuejs", "core", 50_000),
            _sr("other", "vue-admin", 10_000),
        ]
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.resolve_keyword",
            return_value=("vuejs/vue", results),
        )
        note = build_resolution_note("vue", "https://github.com/vuejs/vue")
        assert "Other candidates" in note
        assert "vuejs/core" in note

    def test_keyword_no_results(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.resolve_keyword",
            return_value=(None, []),
        )
        assert build_resolution_note("nope", "https://github.com/a/b") == ""

    def test_keyword_selected_not_in_results(self, mocker):
        results = [_sr("other", "thing", 1)]
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.resolve_keyword",
            return_value=("other/thing", results),
        )
        # selected repo not matching any result
        assert build_resolution_note("vue", "https://github.com/vuejs/vue") == ""


# ---------------------------------------------------------------------------
# _validate_fetched_page
# ---------------------------------------------------------------------------
class TestValidateFetchedPage:
    def test_valid_page_returned(self):
        page = _make_page(
            sections=[WikiSection(title="Intro", level=2, content="hello")]
        )
        result = _validate_fetched_page("https://github.com/o/r", page)
        assert isinstance(result, WikiPage)

    def test_no_content_returns_error(self):
        page = _make_page(sections=[], raw_text="")
        result = _validate_fetched_page("https://github.com/o/r", page)
        assert isinstance(result, ToolResponse)
        assert result.code == ErrorCode.NO_CONTENT

    def test_not_indexed_page_returns_error(self):
        page = _make_page(
            sections=[], raw_text="This page doesn't exist. Request a repo."
        )
        result = _validate_fetched_page("https://github.com/o/r", page)
        assert isinstance(result, ToolResponse)
        assert result.code == ErrorCode.NOT_INDEXED


# ---------------------------------------------------------------------------
# fetch_page_or_error
# ---------------------------------------------------------------------------
class TestFetchPageOrError:
    def test_validation_error(self, mocker):
        result = fetch_page_or_error("not-a-valid-url")
        assert isinstance(result, ToolResponse)
        assert result.code == ErrorCode.VALIDATION

    def test_rate_limited(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.validate_topics_input",
            return_value=type("V", (), {"repo_url": "https://github.com/o/r"})(),
        )
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.wait_for_rate_limit", return_value=False
        )
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.time_until_next_slot", return_value=15.0
        )
        result = fetch_page_or_error("https://github.com/o/r")
        assert isinstance(result, ToolResponse)
        assert result.code == ErrorCode.RATE_LIMITED
        assert result.meta.retry_after_seconds == 15.0
        assert result.meta.calls_remaining == 0

    def test_timeout_error(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.validate_topics_input",
            return_value=type("V", (), {"repo_url": "https://github.com/o/r"})(),
        )
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.wait_for_rate_limit", return_value=True
        )
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.fetch_page_with_fallback",
            side_effect=TimeoutError("timed out"),
        )
        result = fetch_page_or_error("https://github.com/o/r")
        assert isinstance(result, ToolResponse)
        assert result.code == ErrorCode.TIMEOUT

    def test_success(self, mocker):
        from tinkywiki_mcp.fallback import FallbackResult
        page = _make_page(
            sections=[WikiSection(title="X", level=2, content="y")]
        )
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.validate_topics_input",
            return_value=type("V", (), {"repo_url": "https://github.com/o/r"})(),
        )
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.wait_for_rate_limit", return_value=True
        )
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.fetch_page_with_fallback",
            return_value=FallbackResult(page=page, source="tinkywiki"),
        )
        result = fetch_page_or_error("https://github.com/o/r")
        assert isinstance(result, WikiPage)

    def test_all_sources_failed(self, mocker):
        """When all fallback sources fail, returns NOT_INDEXED error."""
        from tinkywiki_mcp.fallback import FallbackResult
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.validate_topics_input",
            return_value=type("V", (), {"repo_url": "https://github.com/o/r"})(),
        )
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.wait_for_rate_limit", return_value=True
        )
        mocker.patch(
            "tinkywiki_mcp.tools._helpers.fetch_page_with_fallback",
            return_value=FallbackResult(
                page=None, source="tinkywiki",
                tinkywiki_not_indexed=True, deepwiki_not_indexed=True,
            ),
        )
        result = fetch_page_or_error("https://github.com/o/r")
        assert isinstance(result, ToolResponse)
        assert result.code == ErrorCode.NOT_INDEXED
