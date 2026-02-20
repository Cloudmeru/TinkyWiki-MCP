"""Shared fixtures for TinkyWiki MCP tests."""

from __future__ import annotations

from typing import Any

import pytest

from tinkywiki_mcp.cache import clear_cache
from tinkywiki_mcp.parser import WikiPage, WikiSection
from tinkywiki_mcp.rate_limit import reset_rate_limits

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------
SAMPLE_REPO_URL = "https://github.com/microsoft/vscode"
SAMPLE_REPO_NAME = "github.com/microsoft/vscode"
SAMPLE_HTML = """
<html>
<body>
<main>
  <h1>Microsoft VS Code</h1>
  <h2>Architecture</h2>
  <p>VS Code is built on <strong>Electron</strong> for cross-platform support.</p>
  <pre><code class="language-typescript">const app = new App();</code></pre>
  <h2>Extensions</h2>
  <p>Extensions are installed from the <a href="https://marketplace.visualstudio.com">marketplace</a>.</p>
  <h3>Extension API</h3>
  <p>The API provides access to the editor, commands, and more.</p>
  <h2>Testing</h2>
  <p>Tests are written using <em>Mocha</em> and run via the CLI.</p>
</main>
<nav class="toc">
  <a href="#architecture">Architecture</a>
  <a href="#extensions">Extensions</a>
  <a href="#testing">Testing</a>
</nav>
</body>
</html>
"""


def make_wiki_page(**overrides: Any) -> WikiPage:
    """Create a WikiPage with sensible defaults for testing."""
    defaults: dict[str, Any] = {
        "repo_name": SAMPLE_REPO_NAME,
        "url": f"https://codewiki.google/{SAMPLE_REPO_NAME}",
        "title": "Microsoft VS Code",
        "sections": [
            WikiSection(
                title="Architecture", level=2, content="VS Code is built on Electron."
            ),
            WikiSection(
                title="Extensions", level=2, content="Extensions from the marketplace."
            ),
            WikiSection(
                title="Extension API", level=3, content="API for editor access."
            ),
            WikiSection(title="Testing", level=2, content="Tests written in Mocha."),
        ],
        "toc": [
            {"title": "Architecture", "href": "#architecture"},
            {"title": "Extensions", "href": "#extensions"},
            {"title": "Testing", "href": "#testing"},
        ],
        "diagrams": [],
        "raw_text": "Microsoft VS Code\nArchitecture\nExtensions\nTesting",
    }
    defaults.update(overrides)
    return WikiPage(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_state():
    """Reset caches and rate limits before each test."""
    clear_cache()
    reset_rate_limits()
    yield
    clear_cache()
    reset_rate_limits()


@pytest.fixture
def sample_wiki_page() -> WikiPage:
    """A pre-built WikiPage for testing tools."""
    return make_wiki_page()


@pytest.fixture
def sample_html() -> str:
    """Sample SSR HTML resembling a TinkyWiki page."""
    return SAMPLE_HTML


@pytest.fixture
def mock_fetch_wiki_page(mocker, sample_wiki_page):
    """Patch parser.fetch_wiki_page to return sample data without HTTP."""
    return mocker.patch(
        "tinkywiki_mcp.parser.fetch_wiki_page",
        return_value=sample_wiki_page,
    )
