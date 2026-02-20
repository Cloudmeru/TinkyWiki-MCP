"""Tests for Pydantic input schemas and structured response types."""

from __future__ import annotations

import json

import pytest

from tinkywiki_mcp.types import (
    ErrorCode,
    RepoInput,
    ResponseMeta,
    ResponseStatus,
    SearchInput,
    SectionInput,
    ToolResponse,
    TopicsInput,
    validate_search_input,
    validate_section_input,
    validate_topics_input,
)


# ---------------------------------------------------------------------------
# RepoInput
# ---------------------------------------------------------------------------
class TestRepoInput:
    def test_full_github_url(self):
        inp = RepoInput(repo_url="https://github.com/microsoft/vscode")
        assert inp.repo_url == "https://github.com/microsoft/vscode"

    def test_full_gitlab_url(self):
        inp = RepoInput(repo_url="https://gitlab.com/org/project")
        assert inp.repo_url == "https://gitlab.com/org/project"

    def test_owner_repo_shorthand(self):
        inp = RepoInput(repo_url="microsoft/vscode")
        assert inp.repo_url == "https://github.com/microsoft/vscode"

    def test_owner_repo_with_dots(self):
        inp = RepoInput(repo_url="user/repo.js")
        assert inp.repo_url == "https://github.com/user/repo.js"

    def test_empty_raises(self):
        with pytest.raises(Exception):
            RepoInput(repo_url="")

    def test_whitespace_only_raises(self):
        with pytest.raises(Exception):
            RepoInput(repo_url="   ")

    def test_invalid_url_raises(self):
        with pytest.raises(Exception):
            RepoInput(repo_url="https://random-site.com/foo/bar")

    def test_single_word_raises(self):
        with pytest.raises(Exception):
            RepoInput(repo_url="justarepo")

    def test_strips_whitespace(self):
        inp = RepoInput(repo_url="  microsoft/vscode  ")
        assert inp.repo_url == "https://github.com/microsoft/vscode"


# ---------------------------------------------------------------------------
# SearchInput
# ---------------------------------------------------------------------------
class TestSearchInput:
    def test_valid(self):
        inp = SearchInput(repo_url="owner/repo", query="How does routing work?")
        assert inp.repo_url == "https://github.com/owner/repo"
        assert inp.query == "How does routing work?"

    def test_empty_query_raises(self):
        with pytest.raises(Exception):
            SearchInput(repo_url="owner/repo", query="")

    def test_whitespace_query_raises(self):
        with pytest.raises(Exception):
            SearchInput(repo_url="owner/repo", query=" ")


# ---------------------------------------------------------------------------
# SectionInput (new in v0.3.0)
# ---------------------------------------------------------------------------
class TestSectionInput:
    def test_valid(self):
        inp = SectionInput(repo_url="owner/repo", section_title="Architecture")
        assert inp.repo_url == "https://github.com/owner/repo"
        assert inp.section_title == "Architecture"

    def test_empty_section_title_raises(self):
        with pytest.raises(Exception):
            SectionInput(repo_url="owner/repo", section_title="")

    def test_whitespace_section_title_raises(self):
        with pytest.raises(Exception):
            SectionInput(repo_url="owner/repo", section_title="  ")

    def test_inherits_repo_validation(self):
        with pytest.raises(Exception):
            SectionInput(
                repo_url="http://example.com/foo/bar", section_title="Architecture"
            )

    def test_shorthand_normalizes(self):
        inp = SectionInput(repo_url="microsoft/vscode", section_title="Ext")
        assert inp.repo_url == "https://github.com/microsoft/vscode"


# ---------------------------------------------------------------------------
# ToolResponse
# ---------------------------------------------------------------------------
class TestToolResponse:
    def test_success_factory(self):
        resp = ToolResponse.success(
            "hello world", repo_url="https://github.com/a/b", query="q"
        )
        assert resp.status == ResponseStatus.OK
        assert resp.data == "hello world"
        assert resp.meta.char_count == 11
        assert resp.code is None
        # content_hash and idempotency_key populated on success
        assert resp.meta.content_hash is not None
        assert len(resp.meta.content_hash) == 16
        assert resp.idempotency_key is not None
        assert "https://github.com/a/b" in resp.idempotency_key

    def test_error_factory(self):
        resp = ToolResponse.error(
            ErrorCode.TIMEOUT, "timed out", repo_url="https://github.com/a/b"
        )
        assert resp.status == ResponseStatus.ERROR
        assert resp.code == ErrorCode.TIMEOUT
        assert resp.message == "timed out"
        assert resp.data is None

    def test_to_text_is_valid_json(self):
        resp = ToolResponse.success("data here")
        text = resp.to_text()
        parsed = json.loads(text)
        assert parsed["status"] == "ok"
        assert parsed["data"] == "data here"
        assert "content_hash" in parsed["meta"]

    def test_error_to_text_excludes_none(self):
        resp = ToolResponse.error(ErrorCode.VALIDATION, "bad input")
        text = resp.to_text()
        parsed = json.loads(text)
        assert "data" not in parsed
        assert "query" not in parsed
        assert "idempotency_key" not in parsed

    def test_meta_defaults(self):
        meta = ResponseMeta()
        assert meta.elapsed_ms == 0
        assert meta.char_count == 0
        assert meta.attempt == 1
        assert meta.truncated is False
        assert meta.content_hash is None

    def test_content_hash_deterministic(self):
        """Same data produces same hash."""
        r1 = ToolResponse.success("identical content")
        r2 = ToolResponse.success("identical content")
        assert r1.meta.content_hash == r2.meta.content_hash

    def test_content_hash_different_data(self):
        """Different data produces different hashes."""
        r1 = ToolResponse.success("data one")
        r2 = ToolResponse.success("data two")
        assert r1.meta.content_hash != r2.meta.content_hash

    def test_idempotency_key_with_repo(self):
        """Idempotency key includes repo_url and content_hash."""
        r = ToolResponse.success("x", repo_url="https://github.com/a/b")
        assert r.idempotency_key is not None
        parts = r.idempotency_key.split("::")
        assert len(parts) == 2
        assert parts[0] == "https://github.com/a/b"

    def test_idempotency_key_no_repo(self):
        """Without repo_url, idempotency_key is just the hash."""
        r = ToolResponse.success("x")
        assert r.idempotency_key == r.meta.content_hash

    def test_rate_limited_error_code(self):
        """RATE_LIMITED error code exists."""
        resp = ToolResponse.error(ErrorCode.RATE_LIMITED, "too many requests")
        assert resp.code == ErrorCode.RATE_LIMITED


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
class TestValidationHelpers:
    def test_validate_search_input_ok(self):
        result = validate_search_input("owner/repo", "What is X?")
        assert isinstance(result, SearchInput)

    def test_validate_search_input_bad_url(self):
        result = validate_search_input("not-a-url", "query")
        assert isinstance(result, ToolResponse)
        assert result.status == ResponseStatus.ERROR
        assert result.code == ErrorCode.VALIDATION

    def test_validate_search_input_empty_query(self):
        result = validate_search_input("owner/repo", "")
        assert isinstance(result, ToolResponse)
        assert result.code == ErrorCode.VALIDATION

    def test_validate_topics_input_ok(self):
        result = validate_topics_input("microsoft/vscode")
        assert isinstance(result, TopicsInput)

    def test_validate_topics_input_bad(self):
        result = validate_topics_input("http://example.com/foo/bar")
        assert isinstance(result, ToolResponse)
        assert result.code == ErrorCode.VALIDATION

    def test_validate_section_input_ok(self):
        result = validate_section_input("owner/repo", "Architecture")
        assert isinstance(result, SectionInput)

    def test_validate_section_input_bad_url(self):
        result = validate_section_input("http://example.com/foo/bar", "Architecture")
        assert isinstance(result, ToolResponse)
        assert result.code == ErrorCode.VALIDATION

    def test_validate_section_input_empty_section(self):
        result = validate_section_input("owner/repo", "")
        assert isinstance(result, ToolResponse)
        assert result.code == ErrorCode.VALIDATION


# ---------------------------------------------------------------------------
# Bare keyword resolution in RepoInput (v1.2.0+)
# ---------------------------------------------------------------------------
class TestRepoInputBareKeyword:
    """Tests for bare keyword → owner/repo resolution inside the validator."""

    def test_resolved_keyword_produces_github_url(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.resolver.resolve_keyword",
            return_value=("vuejs/vue", []),
        )
        mocker.patch("tinkywiki_mcp.resolver.is_bare_keyword", return_value=True)
        inp = RepoInput(repo_url="vue")
        assert inp.repo_url == "https://github.com/vuejs/vue"

    def test_unresolved_keyword_raises_helpful_error(self, mocker):
        mocker.patch(
            "tinkywiki_mcp.resolver.resolve_keyword",
            return_value=(None, []),
        )
        mocker.patch("tinkywiki_mcp.resolver.is_bare_keyword", return_value=True)
        with pytest.raises(Exception, match="Could not resolve keyword"):
            RepoInput(repo_url="xyznonexistent")

    def test_non_keyword_non_url_raises(self):
        """Gibberish that isn't a keyword, URL, or owner/repo should fail."""
        with pytest.raises(Exception, match="Invalid repository URL"):
            RepoInput(repo_url="https://random-site.com/foo/bar")


# ---------------------------------------------------------------------------
# SHA-256 content hash (changed from MD5 in v1.2.0)
# ---------------------------------------------------------------------------
class TestSha256ContentHash:
    def test_hash_is_16_chars(self):
        resp = ToolResponse.success("test data")
        assert resp.meta.content_hash is not None
        assert len(resp.meta.content_hash) == 16

    def test_hash_is_hex(self):
        import re

        resp = ToolResponse.success("test data")
        assert re.fullmatch(r"[0-9a-f]{16}", resp.meta.content_hash)

