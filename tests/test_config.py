"""Tests for environment-variable-driven configuration."""

from __future__ import annotations

import importlib


class TestConfig:
    def test_default_values(self):
        from tinkywiki_mcp import config

        assert config.HARD_TIMEOUT_SECONDS == 60
        assert config.MAX_RETRIES == 2
        assert config.RESPONSE_MAX_CHARS == 30000
        assert config.TINKYWIKI_BASE_URL == "https://codewiki.google"

    def test_httpx_defaults(self):
        from tinkywiki_mcp import config

        assert config.HTTPX_TIMEOUT_SECONDS == 30

    def test_cache_defaults(self):
        from tinkywiki_mcp import config

        assert config.CACHE_TTL_SECONDS == 300
        assert config.CACHE_MAX_SIZE == 50

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("TINKYWIKI_HARD_TIMEOUT", "120")
        monkeypatch.setenv("TINKYWIKI_MAX_RETRIES", "5")
        monkeypatch.setenv("TINKYWIKI_VERBOSE", "true")
        monkeypatch.setenv("TINKYWIKI_BASE_URL", "https://custom.url")

        # Force reimport to pick up new env vars
        from tinkywiki_mcp import config

        importlib.reload(config)

        assert config.HARD_TIMEOUT_SECONDS == 120
        assert config.MAX_RETRIES == 5
        assert config.VERBOSE is True
        assert config.TINKYWIKI_BASE_URL == "https://custom.url"

        # Reset
        importlib.reload(config)

    def test_httpx_env_override(self, monkeypatch):
        monkeypatch.setenv("TINKYWIKI_HTTPX_TIMEOUT", "60")

        from tinkywiki_mcp import config

        importlib.reload(config)

        assert config.HTTPX_TIMEOUT_SECONDS == 60

        importlib.reload(config)

    def test_cache_env_override(self, monkeypatch):
        monkeypatch.setenv("TINKYWIKI_CACHE_TTL", "600")
        monkeypatch.setenv("TINKYWIKI_CACHE_MAX_SIZE", "100")

        from tinkywiki_mcp import config

        importlib.reload(config)

        assert config.CACHE_TTL_SECONDS == 600
        assert config.CACHE_MAX_SIZE == 100

        importlib.reload(config)

    def test_invalid_env_uses_default(self, monkeypatch):
        monkeypatch.setenv("TINKYWIKI_HARD_TIMEOUT", "not_a_number")

        from tinkywiki_mcp import config

        importlib.reload(config)
        assert config.HARD_TIMEOUT_SECONDS == 60
        importlib.reload(config)

    def test_selectors_populated(self):
        from tinkywiki_mcp import config

        assert len(config.CHAT_INPUT_SELECTORS) > 0
        assert len(config.SUBMIT_BUTTON_SELECTORS) > 0
        assert len(config.RESPONSE_ELEMENT_SELECTORS) > 0

    # --- v1.4.0: DeepWiki, GitHub API, Fallback config ---

    def test_deepwiki_defaults(self):
        from tinkywiki_mcp import config

        assert config.DEEPWIKI_BASE_URL == "https://deepwiki.com"
        assert config.DEEPWIKI_ENABLED is True
        assert len(config.DEEPWIKI_CONTENT_SELECTORS) > 0
        assert len(config.DEEPWIKI_NOT_INDEXED_INDICATORS) > 0
        assert len(config.DEEPWIKI_ASK_INPUT_SELECTORS) > 0
        assert len(config.DEEPWIKI_ASK_SUBMIT_SELECTORS) > 0

    def test_github_api_defaults(self):
        from tinkywiki_mcp import config

        assert config.GITHUB_API_BASE_URL == "https://api.github.com"
        assert config.GITHUB_API_ENABLED is True
        assert config.GITHUB_API_TIMEOUT == 15

    def test_fallback_defaults(self):
        from tinkywiki_mcp import config

        assert config.FALLBACK_ENABLED is True

    def test_deepwiki_env_override(self, monkeypatch):
        monkeypatch.setenv("DEEPWIKI_ENABLED", "false")
        monkeypatch.setenv("DEEPWIKI_BASE_URL", "https://custom-deepwiki.com")

        from tinkywiki_mcp import config

        importlib.reload(config)

        assert config.DEEPWIKI_ENABLED is False
        assert config.DEEPWIKI_BASE_URL == "https://custom-deepwiki.com"

        importlib.reload(config)

    def test_github_api_env_override(self, monkeypatch):
        monkeypatch.setenv("GITHUB_API_ENABLED", "false")
        monkeypatch.setenv("GITHUB_API_TIMEOUT", "30")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken")

        from tinkywiki_mcp import config

        importlib.reload(config)

        assert config.GITHUB_API_ENABLED is False
        assert config.GITHUB_API_TIMEOUT == 30
        assert config.GITHUB_TOKEN == "ghp_testtoken"

        importlib.reload(config)

    def test_fallback_env_override(self, monkeypatch):
        monkeypatch.setenv("TINKYWIKI_FALLBACK_ENABLED", "false")

        from tinkywiki_mcp import config

        importlib.reload(config)

        assert config.FALLBACK_ENABLED is False

        importlib.reload(config)
