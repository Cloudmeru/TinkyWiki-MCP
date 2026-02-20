"""Per-repo sliding-window rate limiter for TinkyWiki MCP tools.

Prevents runaway agent loops from hammering TinkyWiki with the same
request hundreds of times.  Each repo URL gets its own counter that
tracks calls within a configurable window (default: 10 calls / 60 s).

When the limit is exceeded the tool can either auto-wait for the next
available slot (up to ``RATE_LIMIT_MAX_WAIT_SECONDS``) or return a
clear ``RATE_LIMITED`` error so the agent knows to stop retrying.

Thread-safe: uses a ``threading.Lock`` to guard the counter state.
"""

from __future__ import annotations

import logging
import threading
import time

from . import config

logger = logging.getLogger("TinkyWiki")

# ---------------------------------------------------------------------------
# Per-key sliding window
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_windows: dict[str, list[float]] = {}


def check_rate_limit(key: str) -> bool:
    """Return ``True`` if the request is allowed, ``False`` if rate-limited.

    Each call records a timestamp for *key*.  Timestamps older than
    ``RATE_LIMIT_WINDOW_SECONDS`` are pruned.  If the remaining count
    exceeds ``RATE_LIMIT_MAX_CALLS``, the request is rejected.
    """
    now = time.monotonic()
    window = config.RATE_LIMIT_WINDOW_SECONDS
    max_calls = config.RATE_LIMIT_MAX_CALLS

    with _lock:
        timestamps = _windows.setdefault(key, [])
        # Prune expired entries
        cutoff = now - window
        _windows[key] = [t for t in timestamps if t > cutoff]
        timestamps = _windows[key]

        if len(timestamps) >= max_calls:
            logger.warning(
                "Rate limit exceeded for %s (%d calls in %ds window)",
                key,
                len(timestamps),
                window,
            )
            return False

        timestamps.append(now)
        return True


def time_until_next_slot(key: str) -> float:
    """Return seconds until the next rate-limit slot opens for *key*.

    Returns 0.0 if a slot is already available.
    """
    now = time.monotonic()
    window = config.RATE_LIMIT_WINDOW_SECONDS
    max_calls = config.RATE_LIMIT_MAX_CALLS

    with _lock:
        timestamps = _windows.get(key, [])
        cutoff = now - window
        active = sorted(t for t in timestamps if t > cutoff)

        if len(active) < max_calls:
            return 0.0

        # Oldest active timestamp — when it expires, a slot opens
        oldest = active[0]
        wait = (oldest + window) - now
        return max(0.0, wait)


def wait_for_rate_limit(key: str) -> bool:
    """Wait until a rate-limit slot opens, then record the call.

    If ``RATE_LIMIT_AUTO_WAIT`` is disabled or the wait would exceed
    ``RATE_LIMIT_MAX_WAIT_SECONDS``, returns ``False`` immediately
    (caller should return a RATE_LIMITED error).

    Returns ``True`` if the call is now allowed (may have waited).
    """
    if not config.RATE_LIMIT_AUTO_WAIT:
        return check_rate_limit(key)

    # Fast path: slot available right now
    if check_rate_limit(key):
        return True

    wait = time_until_next_slot(key)
    max_wait = config.RATE_LIMIT_MAX_WAIT_SECONDS

    if wait <= 0:
        # Shouldn't happen, but re-check
        return check_rate_limit(key)

    if wait > max_wait:
        logger.warning(
            "Rate limit wait %.1fs exceeds max %ds for %s — rejecting",
            wait,
            max_wait,
            key,
        )
        return False

    logger.info(
        "Rate limited for %s — auto-waiting %.1fs for next slot", key, wait
    )
    time.sleep(wait + 0.05)  # small buffer to ensure the slot is open
    return check_rate_limit(key)


def rate_limit_remaining(key: str) -> int:
    """Return how many calls remain in the current window for *key*."""
    now = time.monotonic()
    window = config.RATE_LIMIT_WINDOW_SECONDS
    max_calls = config.RATE_LIMIT_MAX_CALLS

    with _lock:
        timestamps = _windows.get(key, [])
        cutoff = now - window
        active = [t for t in timestamps if t > cutoff]
        return max(0, max_calls - len(active))


def reset_rate_limits() -> None:
    """Clear all rate-limit state (mainly for testing)."""
    with _lock:
        _windows.clear()
