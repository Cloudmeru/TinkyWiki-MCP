"""Tests for the httpx + BeautifulSoup parser module."""

from __future__ import annotations

from bs4 import BeautifulSoup

from tinkywiki_mcp.parser import (
    WikiPage,
    _extract_diagrams,
    _extract_text,
    _extract_toc,
    _parse_sections,
    fetch_wiki_page,
    get_section_by_title,
    page_to_markdown,
)
from tests.conftest import SAMPLE_HTML, make_wiki_page


# ---------------------------------------------------------------------------
# _extract_text
# ---------------------------------------------------------------------------
class TestExtractText:
    def test_plain_text(self):
        soup = BeautifulSoup("<p>Hello world</p>", "lxml")
        tag = soup.find("p")
        assert _extract_text(tag) == "Hello world"

    def test_bold(self):
        soup = BeautifulSoup("<p>This is <strong>bold</strong> text</p>", "lxml")
        tag = soup.find("p")
        result = _extract_text(tag)
        assert "**bold**" in result

    def test_italic(self):
        soup = BeautifulSoup("<p>This is <em>italic</em> text</p>", "lxml")
        tag = soup.find("p")
        result = _extract_text(tag)
        assert "*italic*" in result

    def test_link(self):
        soup = BeautifulSoup(
            '<p>See <a href="https://example.com">link</a></p>', "lxml"
        )
        tag = soup.find("p")
        result = _extract_text(tag)
        assert "[link](https://example.com)" in result

    def test_code_inline(self):
        soup = BeautifulSoup("<p>Use <code>npm install</code> to install</p>", "lxml")
        tag = soup.find("p")
        result = _extract_text(tag)
        assert "`npm install`" in result

    def test_code_block(self):
        soup = BeautifulSoup("<div><pre><code>const x = 1;</code></pre></div>", "lxml")
        tag = soup.find("div")
        result = _extract_text(tag)
        assert "```" in result
        assert "const x = 1;" in result

    def test_list(self):
        soup = BeautifulSoup(
            "<div><ul><li>Item A</li><li>Item B</li></ul></div>", "lxml"
        )
        tag = soup.find("div")
        result = _extract_text(tag)
        assert "- Item A" in result
        assert "- Item B" in result


# ---------------------------------------------------------------------------
# _parse_sections
# ---------------------------------------------------------------------------
class TestParseSections:
    def test_extracts_sections(self):
        soup = BeautifulSoup(SAMPLE_HTML, "lxml")
        sections = _parse_sections(soup)
        # h1 + h2 + h2 + h3 + h2 = 5 headings
        assert len(sections) >= 3
        titles = [s.title for s in sections]
        assert "Architecture" in titles
        assert "Extensions" in titles
        assert "Testing" in titles

    def test_section_levels(self):
        soup = BeautifulSoup(SAMPLE_HTML, "lxml")
        sections = _parse_sections(soup)
        arch = next(s for s in sections if s.title == "Architecture")
        assert arch.level == 2

    def test_section_content_not_empty(self):
        soup = BeautifulSoup(SAMPLE_HTML, "lxml")
        sections = _parse_sections(soup)
        arch = next(s for s in sections if s.title == "Architecture")
        assert len(arch.content) > 0

    def test_empty_page(self):
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        sections = _parse_sections(soup)
        assert not sections


# ---------------------------------------------------------------------------
# _extract_toc
# ---------------------------------------------------------------------------
class TestExtractToc:
    def test_extracts_toc_from_nav(self):
        soup = BeautifulSoup(SAMPLE_HTML, "lxml")
        toc = _extract_toc(soup)
        assert len(toc) >= 3
        titles = [item["title"] for item in toc]
        assert "Architecture" in titles

    def test_fallback_to_headings(self):
        html = """
        <html><body><main>
          <h2>Section A</h2><p>text</p>
          <h2>Section B</h2><p>text</p>
        </main></body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        toc = _extract_toc(soup)
        assert len(toc) == 2


# ---------------------------------------------------------------------------
# _extract_diagrams
# ---------------------------------------------------------------------------
class TestExtractDiagrams:
    def test_mermaid_code_block(self):
        html = '<html><body><pre><code class="language-mermaid">graph LR; A-->B;</code></pre></body></html>'
        soup = BeautifulSoup(html, "lxml")
        diagrams = _extract_diagrams(soup)
        assert len(diagrams) == 1
        assert diagrams[0]["type"] == "mermaid"
        assert "graph LR" in diagrams[0]["content"]

    def test_mermaid_div(self):
        html = (
            '<html><body><div class="mermaid">flowchart TD; A-->B;</div></body></html>'
        )
        soup = BeautifulSoup(html, "lxml")
        diagrams = _extract_diagrams(soup)
        assert len(diagrams) == 1
        assert diagrams[0]["type"] == "mermaid"

    def test_diagram_image(self):
        html = '<html><body><img alt="architecture diagram" src="/img/arch.png"></body></html>'
        soup = BeautifulSoup(html, "lxml")
        diagrams = _extract_diagrams(soup)
        assert len(diagrams) == 1
        assert diagrams[0]["type"] == "image"

    def test_tinkywiki_spa_diagram(self):
        """TinkyWiki SPA renders diagrams as <code-documentation-diagram-inline>
        with base64-encoded SVG data URIs — flat text fallback."""
        import base64

        inner_svg = '<svg xmlns="http://www.w3.org/2000/svg"><text>Component A</text><text>Component B</text></svg>'
        b64 = base64.b64encode(inner_svg.encode()).decode()
        data_uri = f"data:image/svg+xml;base64,{b64}"
        html = (
            "<html><body>"
            "<body-content-section><h2>Architecture</h2>"
            "<code-documentation-diagram-inline>"
            '<code-documentation-diagram-contents class="height-constrained">'
            '<div class="zoomable-image-container">'
            f'<svg class="svg-diagram"><image class="image-diagram" href="{data_uri}"></image></svg>'
            "</div></code-documentation-diagram-contents>"
            "</code-documentation-diagram-inline>"
            "</body-content-section>"
            "</body></html>"
        )
        soup = BeautifulSoup(html, "lxml")
        diagrams = _extract_diagrams(soup)
        assert len(diagrams) == 1
        assert diagrams[0]["type"] == "svg-diagram"
        assert diagrams[0]["section"] == "Architecture"
        assert "Component A" in diagrams[0]["content"]
        assert "Component B" in diagrams[0]["content"]

    def test_tinkywiki_graphviz_diagram(self):
        """TinkyWiki Graphviz SVGs have <g class='node'> and <g class='edge'>
        groups that yield structured entities and relationships."""
        import base64

        inner_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            "<title>G</title>"
            '<g class="node" id="node1"><title>Trainer</title>'
            "<text>Trainer</text><text>(Orchestrator)</text></g>"
            '<g class="node" id="node2"><title>Algorithm</title>'
            "<text>Algorithm</text></g>"
            '<g class="edge" id="edge1"><title>Trainer-&gt;Algorithm</title>'
            "<text>manages</text></g>"
            "</svg>"
        )
        b64 = base64.b64encode(inner_svg.encode()).decode()
        data_uri = f"data:image/svg+xml;base64,{b64}"
        html = (
            "<html><body>"
            "<body-content-section><h2>Core Architecture</h2>"
            "<code-documentation-diagram-inline>"
            f'<svg class="svg-diagram"><image class="image-diagram" href="{data_uri}"></image></svg>'
            "</code-documentation-diagram-inline>"
            "</body-content-section>"
            "</body></html>"
        )
        soup = BeautifulSoup(html, "lxml")
        diagrams = _extract_diagrams(soup)
        assert len(diagrams) == 1
        d = diagrams[0]
        assert d["type"] == "svg-diagram"
        assert d["section"] == "Core Architecture"
        # Structured nodes
        assert len(d["nodes"]) == 2
        assert d["nodes"][0]["id"] == "Trainer"
        assert "Orchestrator" in d["nodes"][0]["label"]
        assert d["nodes"][1]["id"] == "Algorithm"
        # Structured edges with relationship labels
        assert len(d["edges"]) == 1
        assert d["edges"][0]["from"] == "Trainer"
        assert d["edges"][0]["to"] == "Algorithm"
        assert d["edges"][0]["label"] == "manages"
        # Backward-compat content string
        assert "Trainer" in d["content"]

    def test_no_diagrams(self):
        html = "<html><body><p>No diagrams here</p></body></html>"
        soup = BeautifulSoup(html, "lxml")
        diagrams = _extract_diagrams(soup)
        assert not diagrams


# ---------------------------------------------------------------------------
# get_section_by_title
# ---------------------------------------------------------------------------
class TestGetSectionByTitle:
    def test_exact_match(self):
        page = make_wiki_page()
        section = get_section_by_title(page, "Architecture")
        assert section is not None
        assert section.title == "Architecture"

    def test_case_insensitive(self):
        page = make_wiki_page()
        section = get_section_by_title(page, "architecture")
        assert section is not None
        assert section.title == "Architecture"

    def test_partial_match(self):
        page = make_wiki_page()
        section = get_section_by_title(page, "Ext")
        assert section is not None
        assert "Ext" in section.title

    def test_no_match(self):
        page = make_wiki_page()
        section = get_section_by_title(page, "Nonexistent")
        assert section is None


# ---------------------------------------------------------------------------
# page_to_markdown
# ---------------------------------------------------------------------------
class TestPageToMarkdown:
    def test_includes_title(self):
        page = make_wiki_page()
        md = page_to_markdown(page)
        assert "# Microsoft VS Code" in md

    def test_includes_sections(self):
        page = make_wiki_page()
        md = page_to_markdown(page)
        assert "Architecture" in md
        assert "Extensions" in md
        assert "Testing" in md

    def test_truncation(self):
        page = make_wiki_page()
        md = page_to_markdown(page, max_chars=50)
        assert len(md) < 200  # truncated + "... [truncated]"
        assert "truncated" in md

    def test_no_truncation_when_short(self):
        page = make_wiki_page()
        md = page_to_markdown(page, max_chars=100000)
        assert "truncated" not in md


# ---------------------------------------------------------------------------
# fetch_wiki_page (mocked HTTP)
# ---------------------------------------------------------------------------
class TestFetchWikiPage:
    def test_calls_playwright(self, mocker):
        """Verify fetch_wiki_page uses Playwright rendering and returns a WikiPage."""
        mocker.patch(
            "tinkywiki_mcp.parser._fetch_html",
            return_value=SAMPLE_HTML,
        )
        page = fetch_wiki_page("https://github.com/microsoft/vscode")
        assert isinstance(page, WikiPage)
        assert page.repo_name == "github.com/microsoft/vscode"
        assert len(page.sections) >= 3

    def test_builds_correct_url(self, mocker):
        mock_fetch = mocker.patch(
            "tinkywiki_mcp.parser._fetch_html",
            return_value=SAMPLE_HTML,
        )
        fetch_wiki_page("https://github.com/owner/repo")
        mock_fetch.assert_called_once_with(
            "https://codewiki.google/github.com/owner/repo"
        )
