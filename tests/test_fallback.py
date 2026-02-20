"""Tests for tinkywiki_mcp.fallback — Fallback orchestrator (v1.4.0).

Covers: FallbackResult, SearchFallbackResult, _is_not_indexed_error,
fetch_page_with_fallback, search_with_fallback, build_source_banner.
"""

from __future__ import annotations

import pytest

from tinkywiki_mcp.fallback import (
    SOURCE_CODEWIKI,
    SOURCE_DEEPWIKI,
    SOURCE_GITHUB_API,
    FallbackResult,
    SearchFallbackResult,
    _is_not_indexed_error,
    build_source_banner,
    fetch_page_with_fallback,
    search_with_fallback,
)
from tinkywiki_mcp.parser import WikiPage, WikiSection
from tinkywiki_mcp.types import ErrorCode, ToolResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SENTINEL = object()

def _page(*, sections=_SENTINEL, raw_text="content") -> WikiPage:
    if sections is _SENTINEL:
        sections = [WikiSection(title="Intro", level=1, content="Hi")]
    return WikiPage(
        repo_name="owner/repo",
        url="https://codewiki.google/github.com/owner/repo",
        title="Repo",
        sections=sections,
        toc=[],
        diagrams=[],
        raw_text=raw_text,
    )


def _not_indexed_page() -> WikiPage:
    return WikiPage(
        repo_name="owner/repo",
        url="https://codewiki.google/github.com/owner/repo",
        title="Repo",
        sections=[],
        toc=[],
        diagrams=[],
        raw_text="This page doesn\u2019t exist 404",
    )


# ---------------------------------------------------------------------------
# _is_not_indexed_error
# ---------------------------------------------------------------------------
class TestIsNotIndexedError:
    def test_none_page(self):
        assert _is_not_indexed_error(None) is True

    def test_empty_page(self):
        page = _page(sections=[], raw_text="")
        assert _is_not_indexed_error(page) is True

    def test_not_indexed_indicators(self):
        page = _page(sections=[], raw_text="This page doesn\u2019t exist")
        assert _is_not_indexed_error(page) is True

    def test_indexed_page(self):
        page = _page()
        assert _is_not_indexed_error(page) is False


# ---------------------------------------------------------------------------
# FallbackResult / SearchFallbackResult dataclasses
# ---------------------------------------------------------------------------
class TestDataclasses:
    def test_fallback_result_defaults(self):
        fr = FallbackResult(page=None, source=SOURCE_CODEWIKI)
        assert fr.tinkywiki_not_indexed is False
        assert fr.deepwiki_not_indexed is False

    def test_search_fallback_result_defaults(self):
        sfr = SearchFallbackResult(response=None, source=SOURCE_CODEWIKI)
        assert sfr.tinkywiki_not_indexed is False
        assert sfr.deepwiki_not_indexed is False


# ---------------------------------------------------------------------------
# build_source_banner
# ---------------------------------------------------------------------------
class TestBuildSourceBanner:
    def test_tinkywiki_banner(self):
        banner = build_source_banner(SOURCE_CODEWIKI)
        assert "Google TinkyWiki" in banner

    def test_deepwiki_banner_with_not_indexed(self):
        banner = build_source_banner(SOURCE_DEEPWIKI, tinkywiki_not_indexed=True)
        assert "DeepWiki" in banner
        assert "TinkyWiki not indexed" in banner

    def test_github_api_banner_both_not_indexed(self):
        banner = build_source_banner(
            SOURCE_GITHUB_API,
            tinkywiki_not_indexed=True,
            deepwiki_not_indexed=True,
        )
        assert "GitHub API" in banner
        assert "TinkyWiki" in banner
        assert "DeepWiki" in banner

    def test_github_api_banner_no_notes(self):
        banner = build_source_banner(SOURCE_GITHUB_API)
        assert "GitHub API" in banner


# ---------------------------------------------------------------------------
# fetch_page_with_fallback
# ---------------------------------------------------------------------------
class TestFetchPageWithFallback:
    def test_tinkywiki_success_returns_immediately(self, mocker):
        page = _page()
        mocker.patch(
            "tinkywiki_mcp.fallback._try_tinkywiki",
            return_value=FallbackResult(page=page, source=SOURCE_CODEWIKI),
        )
        mocker.patch("tinkywiki_mcp.fallback.config.FALLBACK_ENABLED", True)

        result = fetch_page_with_fallback("https://github.com/owner/repo")
        assert result.page is page
        assert result.source == SOURCE_CODEWIKI

    def test_fallback_disabled_only_tries_tinkywiki(self, mocker):
        page = _page()
        tw_mock = mocker.patch(
            "tinkywiki_mcp.fallback._try_tinkywiki",
            return_value=FallbackResult(page=page, source=SOURCE_CODEWIKI),
        )
        dw_mock = mocker.patch("tinkywiki_mcp.fallback._try_deepwiki")
        gh_mock = mocker.patch("tinkywiki_mcp.fallback._try_github_api")
        mocker.patch("tinkywiki_mcp.fallback.config.FALLBACK_ENABLED", False)

        result = fetch_page_with_fallback("https://github.com/owner/repo")
        tw_mock.assert_called_once()
        dw_mock.assert_not_called()
        gh_mock.assert_not_called()

    def test_falls_back_to_deepwiki(self, mocker):
        """When TinkyWiki returns not-indexed, falls back to DeepWiki."""
        mocker.patch(
            "tinkywiki_mcp.fallback._try_tinkywiki",
            return_value=FallbackResult(page=None, source=SOURCE_CODEWIKI),
        )
        mocker.patch(
            "tinkywiki_mcp.fallback._request_tinkywiki_indexing_async",
        )
        deepwiki_page = _page()
        mocker.patch(
            "tinkywiki_mcp.fallback._try_deepwiki",
            return_value=FallbackResult(page=deepwiki_page, source=SOURCE_DEEPWIKI),
        )
        mocker.patch("tinkywiki_mcp.fallback.config.FALLBACK_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.DEEPWIKI_ENABLED", True)

        result = fetch_page_with_fallback("https://github.com/owner/repo")
        assert result.page is deepwiki_page
        assert result.source == SOURCE_DEEPWIKI
        assert result.tinkywiki_not_indexed is True

    def test_falls_back_to_github_api(self, mocker):
        """When both TinkyWiki and DeepWiki fail, falls back to GitHub API."""
        mocker.patch(
            "tinkywiki_mcp.fallback._try_tinkywiki",
            return_value=FallbackResult(page=None, source=SOURCE_CODEWIKI),
        )
        mocker.patch("tinkywiki_mcp.fallback._request_tinkywiki_indexing_async")
        mocker.patch(
            "tinkywiki_mcp.fallback._try_deepwiki",
            return_value=FallbackResult(
                page=None, source=SOURCE_DEEPWIKI, deepwiki_not_indexed=True
            ),
        )
        github_page = _page()
        mocker.patch(
            "tinkywiki_mcp.fallback._try_github_api",
            return_value=FallbackResult(page=github_page, source=SOURCE_GITHUB_API),
        )
        mocker.patch("tinkywiki_mcp.fallback.config.FALLBACK_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.DEEPWIKI_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.GITHUB_API_ENABLED", True)

        result = fetch_page_with_fallback("https://github.com/owner/repo")
        assert result.page is github_page
        assert result.source == SOURCE_GITHUB_API
        assert result.tinkywiki_not_indexed is True
        assert result.deepwiki_not_indexed is True

    def test_all_failed(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.fallback._try_tinkywiki",
            return_value=FallbackResult(page=None, source=SOURCE_CODEWIKI),
        )
        mocker.patch("tinkywiki_mcp.fallback._request_tinkywiki_indexing_async")
        mocker.patch(
            "tinkywiki_mcp.fallback._try_deepwiki",
            return_value=FallbackResult(
                page=None, source=SOURCE_DEEPWIKI, deepwiki_not_indexed=True
            ),
        )
        mocker.patch(
            "tinkywiki_mcp.fallback._try_github_api",
            return_value=FallbackResult(page=None, source=SOURCE_GITHUB_API),
        )
        mocker.patch("tinkywiki_mcp.fallback.config.FALLBACK_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.DEEPWIKI_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.GITHUB_API_ENABLED", True)

        result = fetch_page_with_fallback("https://github.com/owner/repo")
        assert result.page is None
        assert result.tinkywiki_not_indexed is True
        assert result.deepwiki_not_indexed is True

    def test_not_indexed_page_triggers_fallback(self, mocker):
        """A TinkyWiki page with not-indexed indicators triggers fallback."""
        not_indexed = _not_indexed_page()
        mocker.patch(
            "tinkywiki_mcp.fallback._try_tinkywiki",
            return_value=FallbackResult(page=not_indexed, source=SOURCE_CODEWIKI),
        )
        mocker.patch("tinkywiki_mcp.fallback._request_tinkywiki_indexing_async")
        dw_page = _page()
        mocker.patch(
            "tinkywiki_mcp.fallback._try_deepwiki",
            return_value=FallbackResult(page=dw_page, source=SOURCE_DEEPWIKI),
        )
        mocker.patch("tinkywiki_mcp.fallback.config.FALLBACK_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.DEEPWIKI_ENABLED", True)

        result = fetch_page_with_fallback("https://github.com/owner/repo")
        assert result.page is dw_page
        assert result.source == SOURCE_DEEPWIKI


# ---------------------------------------------------------------------------
# search_with_fallback
# ---------------------------------------------------------------------------
class TestSearchWithFallback:
    def test_tinkywiki_success(self):
        ok_response = ToolResponse.success("Answer from TinkyWiki")

        def tw_fn():
            return ok_response

        result = search_with_fallback(
            "https://github.com/o/r", "query", tinkywiki_search_fn=tw_fn
        )
        assert result.response == "Answer from TinkyWiki"
        assert result.source == SOURCE_CODEWIKI

    def test_falls_back_to_deepwiki_ask(self, mocker):
        error_response = ToolResponse.error(
            ErrorCode.NOT_INDEXED, "not indexed"
        )

        def tw_fn():
            return error_response

        mocker.patch("tinkywiki_mcp.fallback.config.DEEPWIKI_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.FALLBACK_ENABLED", True)
        mocker.patch(
            "tinkywiki_mcp.deepwiki.deepwiki_ask",
            return_value="DeepWiki answer",
        )

        result = search_with_fallback(
            "https://github.com/o/r", "query", tinkywiki_search_fn=tw_fn
        )
        assert result.response == "DeepWiki answer"
        assert result.source == SOURCE_DEEPWIKI

    def test_falls_back_to_github_search(self, mocker):
        error_response = ToolResponse.error(ErrorCode.NOT_INDEXED, "not indexed")

        def tw_fn():
            return error_response

        mocker.patch("tinkywiki_mcp.fallback.config.DEEPWIKI_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.FALLBACK_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.GITHUB_API_ENABLED", True)
        mocker.patch("tinkywiki_mcp.deepwiki.deepwiki_ask", return_value=None)
        mocker.patch(
            "tinkywiki_mcp.github_api.github_search_answer",
            return_value="GitHub search result",
        )

        result = search_with_fallback(
            "https://github.com/o/r", "query", tinkywiki_search_fn=tw_fn
        )
        assert result.response == "GitHub search result"
        assert result.source == SOURCE_GITHUB_API

    def test_all_failed(self, mocker):
        error_response = ToolResponse.error(ErrorCode.NOT_INDEXED, "not indexed")

        def tw_fn():
            return error_response

        mocker.patch("tinkywiki_mcp.fallback.config.DEEPWIKI_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.FALLBACK_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.GITHUB_API_ENABLED", True)
        mocker.patch("tinkywiki_mcp.deepwiki.deepwiki_ask", return_value=None)
        mocker.patch("tinkywiki_mcp.github_api.github_search_answer", return_value=None)

        result = search_with_fallback(
            "https://github.com/o/r", "query", tinkywiki_search_fn=tw_fn
        )
        assert result.response is None
        assert result.tinkywiki_not_indexed is True
        assert result.deepwiki_not_indexed is True

    def test_no_tinkywiki_fn_skips_to_deepwiki(self, mocker):
        mocker.patch("tinkywiki_mcp.fallback.config.DEEPWIKI_ENABLED", True)
        mocker.patch("tinkywiki_mcp.fallback.config.FALLBACK_ENABLED", True)
        mocker.patch(
            "tinkywiki_mcp.deepwiki.deepwiki_ask",
            return_value="DeepWiki direct",
        )

        result = search_with_fallback(
            "https://github.com/o/r", "query", tinkywiki_search_fn=None
        )
        assert result.response == "DeepWiki direct"
        assert result.source == SOURCE_DEEPWIKI
