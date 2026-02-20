"""Persistent browser context pool for TinkyWiki search sessions.

Instead of creating and destroying a fresh Playwright browser context for
every ``tinkywiki_search_wiki`` call, this module maintains a pool of warm
contexts keyed by repository URL.  Reusing a context means the TinkyWiki
page is already loaded and the chat panel can be re-used, dramatically
reducing latency for follow-up questions on the same repo.

Pool behaviour:
- Contexts are created on demand and kept alive until evicted.
- The pool size is bounded by ``config.SESSION_POOL_SIZE`` — when full,
  the least-recently-used context is closed and replaced.
- ``cleanup_pool()`` should be called at server shutdown to close all
  browser contexts (registered via server.py signal handler).
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from . import config
from .browser import _get_browser, run_in_browser_loop
from .stealth import apply_stealth_scripts, stealth_context_options

logger = logging.getLogger("TinkyWiki")


@dataclass
class _PoolEntry:
    """A warm browser context + page for a specific TinkyWiki repo URL."""

    url: str
    context: object  # playwright BrowserContext
    page: object  # playwright Page
    uses: int = 0


# LRU-ordered pool: most-recently-used entries at the end
_pool: OrderedDict[str, _PoolEntry] = OrderedDict()
_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Internal async helpers
# ---------------------------------------------------------------------------
async def _close_entry(entry: _PoolEntry) -> None:
    """Gracefully close a pool entry's page and context."""
    try:
        await entry.page.close()
    except Exception:
        logger.debug("Suppressed exception during cleanup", exc_info=True)
    try:
        await entry.context.close()
    except Exception:
        logger.debug("Suppressed exception during cleanup", exc_info=True)
    logger.debug("Closed session for %s (used %d times)", entry.url, entry.uses)


async def _evict_oldest() -> None:
    """Evict the LRU entry to make room for a new one."""
    if _pool:
        _, entry = _pool.popitem(last=False)
        await _close_entry(entry)


async def _create_entry(url: str) -> _PoolEntry:
    """Create a new browser context + page for *url*."""
    browser = await _get_browser()
    ctx_opts = stealth_context_options()
    ctx_opts["user_agent"] = config.USER_AGENT
    context = await browser.new_context(**ctx_opts)
    page = await context.new_page()
    await apply_stealth_scripts(page)

    await page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=config.PAGE_LOAD_TIMEOUT_SECONDS * 1000,
    )

    # Wait for SPA to render
    try:
        await page.wait_for_selector(
            "body-content-section, documentation-markdown, h1",
            timeout=config.ELEMENT_WAIT_TIMEOUT_SECONDS * 1000,
        )
    except PlaywrightTimeoutError:
        logger.debug("Suppressed exception during cleanup", exc_info=True)
    await asyncio.sleep(config.JS_LOAD_DELAY_SECONDS)

    entry = _PoolEntry(url=url, context=context, page=page)
    logger.info("Created new session for %s", url)
    return entry


async def _get_or_create(url: str) -> _PoolEntry:
    """Return a warm entry for *url*, creating one if needed."""
    async with _lock:
        if url in _pool:
            entry = _pool[url]
            _pool.move_to_end(url)  # mark as recently used
            entry.uses += 1
            logger.debug("Reusing session for %s (use #%d)", url, entry.uses)
            return entry

        # Evict LRU if at capacity
        while len(_pool) >= config.SESSION_POOL_SIZE:
            await _evict_oldest()

        entry = await _create_entry(url)
        entry.uses = 1
        _pool[url] = entry
        return entry


async def _release(url: str, *, broken: bool = False) -> None:
    """Release a session back to the pool.

    If *broken* is True the entry is evicted (connection died,
    navigation error, etc.).
    """
    async with _lock:
        if broken and url in _pool:
            entry = _pool.pop(url)
            await _close_entry(entry)
            logger.warning("Evicted broken session for %s", url)


async def _cleanup_all() -> None:
    """Close every entry in the pool."""
    async with _lock:
        for entry in _pool.values():
            await _close_entry(entry)
        _pool.clear()
    logger.info("Session pool cleaned up")


# ---------------------------------------------------------------------------
# Public synchronous API (runs in the Playwright event loop)
# ---------------------------------------------------------------------------
def get_or_create_session(url: str) -> _PoolEntry:
    """Get a warm session or create a new one (sync wrapper)."""
    return run_in_browser_loop(_get_or_create(url))


def release_session(url: str, *, broken: bool = False) -> None:
    """Release a session back to the pool (sync wrapper)."""
    run_in_browser_loop(_release(url, broken=broken))


def cleanup_pool() -> None:
    """Close all sessions — call at server shutdown."""
    try:
        run_in_browser_loop(_cleanup_all())
    except Exception:  # pylint: disable=broad-except
        logger.debug("Pool cleanup skipped (event loop already closed)")


def pool_stats() -> dict:
    """Return pool diagnostic information."""
    return {
        "size": len(_pool),
        "max_size": config.SESSION_POOL_SIZE,
        "urls": list(_pool.keys()),
    }
