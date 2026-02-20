"""In-memory caching layer for TinkyWiki page fetches.

Uses cachetools TTLCache to avoid hitting TinkyWiki for every request.
Wiki pages are updated infrequently (on PR merges), making caching very effective.

Four caches:
- **HTML cache** — raw rendered HTML keyed by URL
- **Parsed cache** — ``WikiPage`` objects keyed by repo URL (avoids re-parsing)
- **Search cache** — search responses keyed by ``repo_url::query``
- **Topic cache** — pre-built topic-list strings keyed by repo URL (30-min TTL)
"""

from __future__ import annotations

import logging
from typing import Any

from cachetools import TTLCache

from . import config

logger = logging.getLogger("TinkyWiki")

# ---------------------------------------------------------------------------
# HTML page cache — keyed by rendered URL, TTL from config
# ---------------------------------------------------------------------------
_page_cache: TTLCache[str, str] = TTLCache(
    maxsize=config.CACHE_MAX_SIZE,
    ttl=config.CACHE_TTL_SECONDS,
)


def get_cached_page(url: str) -> str | None:
    """Return cached HTML for *url*, or None if not cached / expired."""
    result = _page_cache.get(url)
    if result is not None:
        logger.debug("Cache HIT for %s (%d chars)", url, len(result))
    else:
        logger.debug("Cache MISS for %s", url)
    return result


def set_cached_page(url: str, html: str) -> None:
    """Store *html* in the page cache keyed by *url*."""
    _page_cache[url] = html
    logger.debug("Cached %s (%d chars)", url, len(html))


# ---------------------------------------------------------------------------
# Parsed WikiPage cache — avoids re-parsing the same HTML
# ---------------------------------------------------------------------------
_parsed_cache: TTLCache = TTLCache(
    maxsize=config.PARSED_CACHE_MAX_SIZE,
    ttl=config.CACHE_TTL_SECONDS,
)


def get_cached_wiki_page(repo_url: str) -> Any:
    """Return a cached ``WikiPage`` for *repo_url*, or ``None``."""
    result = _parsed_cache.get(repo_url)
    if result is not None:
        logger.debug("Parsed-cache HIT for %s", repo_url)
    return result


def set_cached_wiki_page(repo_url: str, page: Any) -> None:
    """Cache a parsed ``WikiPage`` keyed by *repo_url*."""
    _parsed_cache[repo_url] = page
    logger.debug("Parsed-cache stored %s", repo_url)


# ---------------------------------------------------------------------------
# Search response cache — avoids re-querying the same question
# ---------------------------------------------------------------------------
_search_cache: TTLCache[str, str] = TTLCache(
    maxsize=config.SEARCH_CACHE_MAX_SIZE,
    ttl=config.SEARCH_CACHE_TTL_SECONDS,
)


def get_cached_search(repo_url: str, query: str) -> str | None:
    """Return a cached search response, or ``None``."""
    key = f"{repo_url}::{query.strip().lower()}"
    result = _search_cache.get(key)
    if result is not None:
        logger.debug("Search-cache HIT for %s :: %s", repo_url, query[:60])
    return result


def set_cached_search(repo_url: str, query: str, response: str) -> None:
    """Cache a search response keyed by *repo_url* + *query*."""
    key = f"{repo_url}::{query.strip().lower()}"
    _search_cache[key] = response
    logger.debug("Search-cache stored %s :: %s", repo_url, query[:60])


# ---------------------------------------------------------------------------
# Topic-list cache — longer TTL for stable structural data (30 min default)
# ---------------------------------------------------------------------------
_topic_cache: TTLCache[str, str] = TTLCache(
    maxsize=config.TOPIC_CACHE_MAX_SIZE,
    ttl=config.TOPIC_CACHE_TTL_SECONDS,
)


def get_cached_topics(repo_url: str) -> str | None:
    """Return a cached topic-list string for *repo_url*, or ``None``."""
    result = _topic_cache.get(repo_url)
    if result is not None:
        logger.debug("Topic-cache HIT for %s", repo_url)
    return result


def set_cached_topics(repo_url: str, data: str) -> None:
    """Cache a topic-list string keyed by *repo_url*."""
    _topic_cache[repo_url] = data
    logger.debug("Topic-cache stored %s (%d chars)", repo_url, len(data))


# ---------------------------------------------------------------------------
# General-purpose helpers
# ---------------------------------------------------------------------------
def invalidate(url: str) -> None:
    """Remove *url* from the HTML cache."""
    _page_cache.pop(url, None)


def clear_cache() -> None:
    """Flush all caches (HTML + parsed + search + topic)."""
    _page_cache.clear()
    _parsed_cache.clear()
    _search_cache.clear()
    _topic_cache.clear()
    logger.debug("All caches cleared")


def cache_stats() -> dict[str, Any]:
    """Return statistics for all caches."""
    return {
        "html": {
            "current_size": len(_page_cache),
            "max_size": _page_cache.maxsize,
            "ttl_seconds": int(_page_cache.ttl),
        },
        "parsed": {
            "current_size": len(_parsed_cache),
            "max_size": _parsed_cache.maxsize,
            "ttl_seconds": int(_parsed_cache.ttl),
        },
        "search": {
            "current_size": len(_search_cache),
            "max_size": _search_cache.maxsize,
            "ttl_seconds": int(_search_cache.ttl),
        },
        "topic": {
            "current_size": len(_topic_cache),
            "max_size": _topic_cache.maxsize,
            "ttl_seconds": int(_topic_cache.ttl),
        },
    }
