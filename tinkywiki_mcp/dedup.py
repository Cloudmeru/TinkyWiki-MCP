"""In-flight request deduplication for TinkyWiki page fetches.

Prevents duplicate Playwright browser launches when the same repo URL
is requested multiple times concurrently (e.g. an eager agent calling
``tinkywiki_list_topics`` 60 times in a row).

**How it works**: The first request for a given URL proceeds normally.
Concurrent requests for the *same* URL block on a ``threading.Event``
until the first request completes, then all waiters receive the same
result — zero extra browser overhead.

Thread-safe: uses a ``threading.Lock`` to guard the in-flight registry
(MCP tool handlers are synchronous and may be called from different threads).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("TinkyWiki")

# ---------------------------------------------------------------------------
# In-flight registry
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_inflight: dict[str, _InflightEntry] = {}


class _InflightEntry:
    """Tracks a single in-flight fetch for a URL."""

    __slots__ = ("event", "result", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: Exception | None = None


def dedup_fetch(key: str, fetch_fn):
    """Execute *fetch_fn()* with deduplication on *key*.

    If another thread is already fetching *key*, this call blocks until
    that fetch completes and returns the same result (or re-raises the
    same exception).

    Args:
        key: Deduplication key (typically the normalised repo URL).
        fetch_fn: Zero-argument callable that performs the actual fetch.

    Returns:
        Whatever *fetch_fn()* returns.

    Raises:
        Whatever *fetch_fn()* raises (propagated to all waiters).
    """
    with _lock:
        if key in _inflight:
            entry = _inflight[key]
            is_owner = False
            logger.debug("Dedup: waiting on in-flight fetch for %s", key)
        else:
            entry = _InflightEntry()
            _inflight[key] = entry
            is_owner = True
            logger.debug("Dedup: starting fetch for %s", key)

    if is_owner:
        try:
            entry.result = fetch_fn()
        except Exception as exc:  # pylint: disable=broad-except
            entry.error = exc
        finally:
            entry.event.set()
            with _lock:
                _inflight.pop(key, None)

    else:
        # Wait for the owner to finish (with generous timeout)
        entry.event.wait(timeout=120)

    if entry.error is not None:
        raise entry.error
    return entry.result


def inflight_count() -> int:
    """Return the number of currently in-flight fetches (for diagnostics)."""
    with _lock:
        return len(_inflight)
