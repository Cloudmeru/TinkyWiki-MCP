"""Tests for tinkywiki_mcp.deepwiki — DeepWiki integration (v1.4.0).

Covers: URL helpers, not-indexed detection, sidebar topic parsing,
content parsing, page fetching, section fetching, and chat/ask feature.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from tinkywiki_mcp.deepwiki import (
    DeepWikiTopic,
    build_deepwiki_url,
    _extract_owner_repo,
    _parse_sidebar_topics,
    _parse_deepwiki_content,
    is_deepwiki_not_indexed,
    fetch_deepwiki_page,
    fetch_deepwiki_section,
    deepwiki_ask,
    deepwiki_request_indexing,
)
from tinkywiki_mcp.parser import WikiPage, WikiSection


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------
class TestBuildDeepwikiUrl:
    def test_github_https(self):
        url = build_deepwiki_url("https://github.com/facebook/react")
        assert url == "https://deepwiki.com/facebook/react"

    def test_github_http(self):
        url = build_deepwiki_url("http://github.com/facebook/react")
        assert url == "https://deepwiki.com/facebook/react"

    def test_trailing_slash(self):
        url = build_deepwiki_url("https://github.com/facebook/react/")
        assert url == "https://deepwiki.com/facebook/react"

    def test_with_hash_and_query(self):
        url = build_deepwiki_url("https://github.com/facebook/react#readme?tab=1")
        assert url == "https://deepwiki.com/facebook/react"


class TestExtractOwnerRepo:
    def test_https_url(self):
        assert _extract_owner_repo("https://github.com/microsoft/vscode") == "microsoft/vscode"

    def test_http_url(self):
        assert _extract_owner_repo("http://github.com/owner/repo") == "owner/repo"

    def test_with_extra_path(self):
        assert _extract_owner_repo("https://github.com/owner/repo/tree/main") == "owner/repo"


# ---------------------------------------------------------------------------
# Not-indexed detection
# ---------------------------------------------------------------------------
class TestIsDeepwikiNotIndexed:
    def test_not_found_page(self):
        html = "<html><body><h1>Profile Not Found</h1></body></html>"
        assert is_deepwiki_not_indexed(html) is True

    def test_repo_not_found(self):
        html = "<html><body><p>Repository not found</p></body></html>"
        assert is_deepwiki_not_indexed(html) is True

    def test_normal_page(self):
        html = "<html><body><h1>React</h1><p>A JavaScript library</p></body></html>"
        assert is_deepwiki_not_indexed(html) is False


# ---------------------------------------------------------------------------
# Sidebar topic parsing
# ---------------------------------------------------------------------------
class TestParseSidebarTopics:
    def test_extracts_topics(self):
        html = """
        <html><body>
        <a href="/facebook/react/1-overview">Overview</a>
        <a href="/facebook/react/2-components">Component System</a>
        <a href="/facebook/react/2.1-hooks">Hooks</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        topics = _parse_sidebar_topics(soup, "facebook/react")
        assert len(topics) == 3
        assert topics[0].title == "Overview"
        assert topics[0].slug == "1-overview"
        assert topics[0].level == 1
        assert topics[2].slug == "2.1-hooks"
        assert topics[2].level == 2

    def test_deduplication(self):
        html = """
        <html><body>
        <a href="/owner/repo/1-intro">Intro</a>
        <a href="/owner/repo/1-intro">Intro Again</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        topics = _parse_sidebar_topics(soup, "owner/repo")
        assert len(topics) == 1

    def test_ignores_non_topic_links(self):
        html = """
        <html><body>
        <a href="/facebook/react/1-overview">Overview</a>
        <a href="https://github.com/facebook/react">GitHub Link</a>
        <a href="/other/repo/1-thing">Other Repo</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        topics = _parse_sidebar_topics(soup, "facebook/react")
        assert len(topics) == 1

    def test_empty_page(self):
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        topics = _parse_sidebar_topics(soup, "owner/repo")
        assert topics == []


# ---------------------------------------------------------------------------
# Content parsing
# ---------------------------------------------------------------------------
class TestParseDeepwikiContent:
    def test_extracts_sections_from_headings(self):
        html = """
        <html><body>
        <article>
          <h1>React Overview</h1>
          <p>React is a JavaScript library.</p>
          <h2>Components</h2>
          <p>Components are the building blocks.</p>
          <h2>State</h2>
          <p>State management in React.</p>
        </article>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        sections = _parse_deepwiki_content(soup)
        assert len(sections) >= 2
        titles = [s.title for s in sections]
        assert "React Overview" in titles or "Components" in titles

    def test_no_headings_single_section(self):
        html = """
        <html><body>
        <article>
          <p>This is a long introductory paragraph about the project that explains everything in detail.</p>
        </article>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        sections = _parse_deepwiki_content(soup)
        assert len(sections) == 1
        assert sections[0].title == "Overview"

    def test_empty_article(self):
        html = "<html><body><article></article></body></html>"
        soup = BeautifulSoup(html, "lxml")
        sections = _parse_deepwiki_content(soup)
        assert sections == []

    def test_fallback_to_body(self):
        html = """
        <html><body>
          <h2>Heading</h2>
          <p>Some content here for the section.</p>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        sections = _parse_deepwiki_content(soup)
        assert len(sections) >= 1


# ---------------------------------------------------------------------------
# Page fetching (mocked)
# ---------------------------------------------------------------------------
class TestFetchDeepwikiPage:
    def test_returns_wiki_page_on_success(self, mocker):
        html = """
        <html><body>
        <h1>React</h1>
        <a href="/facebook/react/1-overview">Overview</a>
        <article>
          <h2>Getting Started</h2>
          <p>Install React via npm install react to begin building UIs with components.</p>
        </article>
        </body></html>
        """
        mocker.patch("tinkywiki_mcp.deepwiki._fetch_deepwiki_html", return_value=html)
        mocker.patch("tinkywiki_mcp.deepwiki.get_cached_wiki_page", return_value=None)
        mocker.patch("tinkywiki_mcp.deepwiki.set_cached_wiki_page")

        page = fetch_deepwiki_page("https://github.com/facebook/react")
        assert page is not None
        assert isinstance(page, WikiPage)
        assert page.repo_name == "facebook/react"

    def test_returns_none_when_not_indexed(self, mocker):
        html = "<html><body><h1>Profile Not Found</h1></body></html>"
        mocker.patch("tinkywiki_mcp.deepwiki._fetch_deepwiki_html", return_value=html)
        mocker.patch("tinkywiki_mcp.deepwiki.get_cached_wiki_page", return_value=None)

        page = fetch_deepwiki_page("https://github.com/unknown/repo")
        assert page is None

    def test_returns_none_when_html_empty(self, mocker):
        mocker.patch("tinkywiki_mcp.deepwiki._fetch_deepwiki_html", return_value="")
        mocker.patch("tinkywiki_mcp.deepwiki.get_cached_wiki_page", return_value=None)

        page = fetch_deepwiki_page("https://github.com/owner/repo")
        assert page is None

    def test_uses_cache(self, mocker):
        cached = WikiPage(
            repo_name="o/r", url="u", title="t",
            sections=[], toc=[], diagrams=[], raw_text="cached",
        )
        mocker.patch("tinkywiki_mcp.deepwiki.get_cached_wiki_page", return_value=cached)
        mock_html = mocker.patch("tinkywiki_mcp.deepwiki._fetch_deepwiki_html")

        page = fetch_deepwiki_page("https://github.com/o/r")
        assert page is cached
        mock_html.assert_not_called()


class TestFetchDeepwikiSection:
    def test_returns_section_page(self, mocker):
        html = """
        <html><body>
        <h1>Component System</h1>
        <article>
          <h2>Function Components</h2>
          <p>Function components are the modern way to write React components with hooks support.</p>
        </article>
        </body></html>
        """
        mocker.patch("tinkywiki_mcp.deepwiki._fetch_deepwiki_html", return_value=html)
        mocker.patch("tinkywiki_mcp.deepwiki.get_cached_wiki_page", return_value=None)
        mocker.patch("tinkywiki_mcp.deepwiki.set_cached_wiki_page")

        page = fetch_deepwiki_section(
            "https://github.com/facebook/react", "2-component-system"
        )
        assert page is not None
        assert isinstance(page, WikiPage)

    def test_returns_none_on_failure(self, mocker):
        mocker.patch("tinkywiki_mcp.deepwiki._fetch_deepwiki_html", return_value="")
        mocker.patch("tinkywiki_mcp.deepwiki.get_cached_wiki_page", return_value=None)

        page = fetch_deepwiki_section(
            "https://github.com/facebook/react", "1-overview"
        )
        assert page is None


# ---------------------------------------------------------------------------
# DeepWiki Ask / Chat (mocked)
# ---------------------------------------------------------------------------
class TestDeepwikiAsk:
    def test_returns_none_when_disabled(self, mocker):
        mocker.patch("tinkywiki_mcp.deepwiki.config.DEEPWIKI_ENABLED", False)
        result = deepwiki_ask("https://github.com/o/r", "What is this?")
        assert result is None

    def test_returns_none_on_error(self, mocker):
        mocker.patch("tinkywiki_mcp.deepwiki.config.DEEPWIKI_ENABLED", True)
        mocker.patch(
            "tinkywiki_mcp.deepwiki.run_in_browser_loop",
            side_effect=RuntimeError("browser error"),
        )
        result = deepwiki_ask("https://github.com/o/r", "What is this?")
        assert result is None


# ---------------------------------------------------------------------------
# DeepWiki indexing request (mocked)
# ---------------------------------------------------------------------------
class TestDeepwikiRequestIndexing:
    def test_returns_false_when_disabled(self, mocker):
        mocker.patch("tinkywiki_mcp.deepwiki.config.DEEPWIKI_ENABLED", False)
        result = deepwiki_request_indexing("https://github.com/o/r")
        assert result is False

    def test_returns_false_on_error(self, mocker):
        mocker.patch("tinkywiki_mcp.deepwiki.config.DEEPWIKI_ENABLED", True)
        mocker.patch(
            "tinkywiki_mcp.deepwiki.run_in_browser_loop",
            side_effect=RuntimeError("error"),
        )
        result = deepwiki_request_indexing("https://github.com/o/r")
        assert result is False
