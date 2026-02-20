"""Tests for the in-memory TTL cache layer."""

from __future__ import annotations

from tinkywiki_mcp.cache import (
    cache_stats,
    clear_cache,
    get_cached_page,
    get_cached_search,
    get_cached_topics,
    get_cached_wiki_page,
    invalidate,
    set_cached_page,
    set_cached_search,
    set_cached_topics,
    set_cached_wiki_page,
)


class TestPageCache:
    def test_miss_returns_none(self):
        assert get_cached_page("https://example.com/page") is None

    def test_set_and_get(self):
        url = "https://codewiki.google/github.com/owner/repo"
        html = "<html><body>Hello</body></html>"
        set_cached_page(url, html)
        assert get_cached_page(url) == html

    def test_invalidate(self):
        url = "https://codewiki.google/github.com/owner/repo"
        set_cached_page(url, "<html>test</html>")
        assert get_cached_page(url) is not None
        invalidate(url)
        assert get_cached_page(url) is None

    def test_invalidate_nonexistent_is_noop(self):
        invalidate("https://no-such-url.com")  # should not raise

    def test_clear_cache(self):
        set_cached_page("https://a.com", "aaa")
        set_cached_page("https://b.com", "bbb")
        clear_cache()
        assert get_cached_page("https://a.com") is None
        assert get_cached_page("https://b.com") is None

    def test_cache_stats_html(self):
        clear_cache()
        stats = cache_stats()
        assert stats["html"]["current_size"] == 0
        assert stats["html"]["max_size"] > 0
        assert stats["html"]["ttl_seconds"] > 0

        set_cached_page("https://x.com", "x")
        stats = cache_stats()
        assert stats["html"]["current_size"] == 1

    def test_overwrite_value(self):
        url = "https://test.com/page"
        set_cached_page(url, "v1")
        assert get_cached_page(url) == "v1"
        set_cached_page(url, "v2")
        assert get_cached_page(url) == "v2"


class TestParsedCache:
    def test_miss_returns_none(self):
        assert get_cached_wiki_page("https://github.com/owner/repo") is None

    def test_set_and_get(self):
        repo = "https://github.com/owner/repo"
        sentinel = {"fake": "page"}
        set_cached_wiki_page(repo, sentinel)
        assert get_cached_wiki_page(repo) is sentinel


class TestSearchCache:
    def test_miss_returns_none(self):
        assert get_cached_search("repo", "query") is None

    def test_set_and_get(self):
        set_cached_search("repo", "What is X?", "X is great.")
        assert get_cached_search("repo", "What is X?") == "X is great."

    def test_case_insensitive_key(self):
        set_cached_search("repo", "Hello World", "answer")
        assert get_cached_search("repo", "hello world") == "answer"

    def test_clear_clears_all(self):
        set_cached_page("https://a.com", "html")
        set_cached_wiki_page("repo", {"fake": True})
        set_cached_search("repo", "q", "a")
        set_cached_topics("repo", "topics")
        clear_cache()
        assert get_cached_page("https://a.com") is None
        assert get_cached_wiki_page("repo") is None
        assert get_cached_search("repo", "q") is None
        assert get_cached_topics("repo") is None


class TestTopicCache:
    def setup_method(self):
        clear_cache()

    def test_miss_returns_none(self):
        assert get_cached_topics("https://github.com/owner/repo") is None

    def test_set_and_get(self):
        repo = "https://github.com/owner/repo"
        data = "## Topics\n- Architecture\n- Extensions"
        set_cached_topics(repo, data)
        assert get_cached_topics(repo) == data

    def test_different_repos_independent(self):
        set_cached_topics("repo-a", "topics-a")
        set_cached_topics("repo-b", "topics-b")
        assert get_cached_topics("repo-a") == "topics-a"
        assert get_cached_topics("repo-b") == "topics-b"

    def test_cache_stats_includes_topic(self):
        stats = cache_stats()
        assert "topic" in stats
        assert stats["topic"]["current_size"] == 0
        set_cached_topics("repo", "data")
        stats = cache_stats()
        assert stats["topic"]["current_size"] == 1
