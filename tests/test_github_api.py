"""Tests for tinkywiki_mcp.github_api — GitHub API fallback (v1.4.0).

Covers: HTTP helpers, owner/repo extraction, repo metadata, README fetching,
file tree, code search, WikiPage builder, and search answer.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

import pytest

from tinkywiki_mcp.github_api import (
    RepoMeta,
    _extract_owner_repo,
    _github_get,
    _github_headers,
    fetch_file_tree,
    fetch_github_wiki_page,
    fetch_readme,
    fetch_repo_meta,
    github_search_answer,
    search_code,
)
from tinkywiki_mcp.parser import WikiPage


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
class TestGithubHeaders:
    def test_default_headers(self, mocker):
        mocker.patch("tinkywiki_mcp.github_api.config.GITHUB_TOKEN", "")
        headers = _github_headers()
        assert "Accept" in headers
        assert "User-Agent" in headers
        assert "Authorization" not in headers

    def test_with_token(self, mocker):
        mocker.patch("tinkywiki_mcp.github_api.config.GITHUB_TOKEN", "ghp_test123")
        headers = _github_headers()
        assert headers["Authorization"] == "Bearer ghp_test123"


class TestGithubGet:
    def test_success(self, mocker):
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps({"name": "react"}).encode()

        mocker.patch("urllib.request.urlopen", return_value=_Resp())
        result = _github_get("/repos/facebook/react")
        assert result == {"name": "react"}

    def test_timeout_returns_none(self, mocker):
        mocker.patch("urllib.request.urlopen", side_effect=TimeoutError("timeout"))
        result = _github_get("/repos/facebook/react")
        assert result is None

    def test_blocks_non_github_host(self):
        # This should be blocked because the URL isn't api.github.com
        result = _github_get("https://evil.com/repos/o/r")
        assert result is None


# ---------------------------------------------------------------------------
# Owner/repo extraction
# ---------------------------------------------------------------------------
class TestExtractOwnerRepo:
    def test_https_url(self):
        assert _extract_owner_repo("https://github.com/microsoft/vscode") == (
            "microsoft",
            "vscode",
        )

    def test_http_url(self):
        assert _extract_owner_repo("http://github.com/owner/repo") == (
            "owner",
            "repo",
        )

    def test_with_extra_path(self):
        assert _extract_owner_repo("https://github.com/a/b/tree/main") == ("a", "b")

    def test_invalid(self):
        assert _extract_owner_repo("not-a-url") is None

    def test_single_segment(self):
        assert _extract_owner_repo("https://github.com/only-owner") is None


# ---------------------------------------------------------------------------
# Repo metadata
# ---------------------------------------------------------------------------
class TestFetchRepoMeta:
    def test_success(self, mocker):
        data = {
            "description": "A JS library",
            "stargazers_count": 200000,
            "language": "JavaScript",
            "topics": ["react", "frontend"],
            "default_branch": "main",
        }
        mocker.patch("tinkywiki_mcp.github_api._github_get", return_value=data)
        meta = fetch_repo_meta("https://github.com/facebook/react")
        assert isinstance(meta, RepoMeta)
        assert meta.owner == "facebook"
        assert meta.repo == "react"
        assert meta.stars == 200000
        assert meta.language == "JavaScript"

    def test_not_found(self, mocker):
        mocker.patch("tinkywiki_mcp.github_api._github_get", return_value=None)
        assert fetch_repo_meta("https://github.com/unknown/repo") is None

    def test_invalid_url(self):
        assert fetch_repo_meta("invalid") is None


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------
class TestFetchReadme:
    def test_base64_readme(self, mocker):
        content = base64.b64encode(b"# Hello World").decode()
        mocker.patch(
            "tinkywiki_mcp.github_api._github_get",
            return_value={"content": content, "encoding": "base64"},
        )
        readme = fetch_readme("https://github.com/owner/repo")
        assert readme == "# Hello World"

    def test_plain_content(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.github_api._github_get",
            return_value={"content": "# Plain readme", "encoding": ""},
        )
        readme = fetch_readme("https://github.com/owner/repo")
        assert readme == "# Plain readme"

    def test_not_found(self, mocker):
        mocker.patch("tinkywiki_mcp.github_api._github_get", return_value=None)
        assert fetch_readme("https://github.com/owner/repo") is None

    def test_invalid_url(self):
        assert fetch_readme("bad-url") is None


# ---------------------------------------------------------------------------
# File tree
# ---------------------------------------------------------------------------
class TestFetchFileTree:
    def test_success(self, mocker):
        meta = RepoMeta(
            owner="o", repo="r", description="", stars=0,
            language="", topics=[], default_branch="main",
        )
        mocker.patch("tinkywiki_mcp.github_api.fetch_repo_meta", return_value=meta)
        tree_data = {
            "tree": [
                {"path": "src/main.py", "type": "blob"},
                {"path": "src/utils.py", "type": "blob"},
                {"path": "src", "type": "tree"},
            ]
        }
        mocker.patch("tinkywiki_mcp.github_api._github_get", return_value=tree_data)
        files = fetch_file_tree("https://github.com/o/r")
        assert files == ["src/main.py", "src/utils.py"]

    def test_limits_entries(self, mocker):
        meta = RepoMeta(
            owner="o", repo="r", description="", stars=0,
            language="", topics=[], default_branch="main",
        )
        mocker.patch("tinkywiki_mcp.github_api.fetch_repo_meta", return_value=meta)
        tree = [{"path": f"file{i}.py", "type": "blob"} for i in range(500)]
        mocker.patch(
            "tinkywiki_mcp.github_api._github_get",
            return_value={"tree": tree},
        )
        files = fetch_file_tree("https://github.com/o/r", max_entries=100)
        assert len(files) == 100

    def test_invalid_url(self):
        assert fetch_file_tree("bad") is None


# ---------------------------------------------------------------------------
# Code search
# ---------------------------------------------------------------------------
class TestSearchCode:
    def test_success(self, mocker):
        data = {
            "items": [
                {
                    "path": "src/index.ts",
                    "name": "index.ts",
                    "html_url": "https://github.com/o/r/blob/main/src/index.ts",
                },
            ]
        }
        mocker.patch("tinkywiki_mcp.github_api._github_get", return_value=data)
        results = search_code("https://github.com/o/r", "useState")
        assert results is not None
        assert len(results) == 1
        assert results[0]["path"] == "src/index.ts"

    def test_no_results(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.github_api._github_get",
            return_value={"items": []},
        )
        results = search_code("https://github.com/o/r", "nonexistent")
        assert results is None

    def test_invalid_url(self):
        assert search_code("bad", "query") is None


# ---------------------------------------------------------------------------
# WikiPage builder
# ---------------------------------------------------------------------------
class TestFetchGithubWikiPage:
    def test_builds_wiki_page(self, mocker):
        meta = RepoMeta(
            owner="facebook", repo="react",
            description="A JS library for building UIs",
            stars=200000, language="JavaScript",
            topics=["react", "frontend"],
            default_branch="main",
        )
        mocker.patch("tinkywiki_mcp.github_api.fetch_repo_meta", return_value=meta)
        mocker.patch("tinkywiki_mcp.github_api.fetch_readme", return_value="# React\nA JS lib")
        mocker.patch(
            "tinkywiki_mcp.github_api.fetch_file_tree",
            return_value=["src/index.js", "package.json"],
        )

        page = fetch_github_wiki_page("https://github.com/facebook/react")
        assert page is not None
        assert isinstance(page, WikiPage)
        assert page.repo_name == "facebook/react"
        assert len(page.sections) >= 2  # metadata + README + tree
        assert any("React" in s.title or "README" in s.title for s in page.sections)

    def test_returns_none_when_repo_not_found(self, mocker):
        mocker.patch("tinkywiki_mcp.github_api.fetch_repo_meta", return_value=None)
        assert fetch_github_wiki_page("https://github.com/none/repo") is None

    def test_disabled_returns_none(self, mocker):
        mocker.patch("tinkywiki_mcp.github_api.config.GITHUB_API_ENABLED", False)
        assert fetch_github_wiki_page("https://github.com/o/r") is None

    def test_invalid_url(self):
        assert fetch_github_wiki_page("bad") is None


# ---------------------------------------------------------------------------
# Search answer
# ---------------------------------------------------------------------------
class TestGithubSearchAnswer:
    def test_with_code_results(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.github_api.search_code",
            return_value=[{"path": "src/hook.ts", "name": "hook.ts", "url": "http://x"}],
        )
        mocker.patch("tinkywiki_mcp.github_api.fetch_readme", return_value="Uses hooks")
        answer = github_search_answer("https://github.com/o/r", "hooks")
        assert answer is not None
        assert "hook" in answer.lower()

    def test_disabled_returns_none(self, mocker):
        mocker.patch("tinkywiki_mcp.github_api.config.GITHUB_API_ENABLED", False)
        assert github_search_answer("https://github.com/o/r", "q") is None

    def test_returns_basic_info_when_no_matches(self, mocker):
        mocker.patch("tinkywiki_mcp.github_api.search_code", return_value=None)
        mocker.patch("tinkywiki_mcp.github_api.fetch_readme", return_value=None)
        meta = RepoMeta(
            owner="o", repo="r", description="A tool",
            stars=100, language="Python", topics=[], default_branch="main",
        )
        mocker.patch("tinkywiki_mcp.github_api.fetch_repo_meta", return_value=meta)
        answer = github_search_answer("https://github.com/o/r", "nonexistent")
        assert answer is not None
        assert "o/r" in answer
