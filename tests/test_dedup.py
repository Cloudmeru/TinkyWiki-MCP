"""Tests for in-flight request deduplication."""

from __future__ import annotations

import threading
import time

import pytest

from tinkywiki_mcp.dedup import dedup_fetch, inflight_count


class TestDedupFetch:
    """Core deduplication behaviour."""

    def test_single_call_returns_result(self):
        """A single call passes through to fetch_fn and returns its result."""
        result = dedup_fetch("key1", lambda: "hello")
        assert result == "hello"

    def test_single_call_propagates_exception(self):
        """If fetch_fn raises, the exception propagates to the caller."""

        def failing_fn():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            dedup_fetch("key2", failing_fn)

    def test_concurrent_calls_deduplicated(self):
        """Multiple concurrent calls for the same key only invoke fetch_fn once."""
        call_count = 0
        barrier = threading.Barrier(3)

        def slow_fetch():
            nonlocal call_count
            call_count += 1
            time.sleep(0.3)  # simulate work
            return "shared-result"

        results = [None, None, None]
        errors: list[Exception | None] = [None, None, None]

        def worker(idx):
            barrier.wait()  # synchronise start
            try:
                results[idx] = dedup_fetch("same-key", slow_fetch)
            except Exception as exc:  # pylint: disable=broad-except
                errors[idx] = exc

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert all(r == "shared-result" for r in results), results
        assert all(e is None for e in errors), errors
        assert call_count == 1, f"fetch_fn called {call_count} times (expected 1)"

    def test_concurrent_calls_propagate_error(self):
        """If the owner's fetch_fn raises, all waiters see the same error."""
        barrier = threading.Barrier(3)

        def failing_fetch():
            time.sleep(0.2)
            raise RuntimeError("shared failure")

        errors: list[RuntimeError | None] = [None, None, None]

        def worker(idx):
            barrier.wait()
            try:
                dedup_fetch("err-key", failing_fetch)
            except RuntimeError as exc:
                errors[idx] = exc

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert all(isinstance(e, RuntimeError) for e in errors)
        assert all("shared failure" in str(e) for e in errors)

    def test_different_keys_run_independently(self):
        """Requests with different keys run in parallel, not deduplicated."""
        call_count = 0
        lock = threading.Lock()

        def counting_fetch():
            nonlocal call_count
            with lock:
                call_count += 1
            time.sleep(0.1)
            return "ok"

        t1 = threading.Thread(target=lambda: dedup_fetch("a", counting_fetch))
        t2 = threading.Thread(target=lambda: dedup_fetch("b", counting_fetch))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert call_count == 2

    def test_inflight_count_zero_when_idle(self):
        """No in-flight fetches when nothing is running."""
        assert not inflight_count()

    def test_key_freed_after_completion(self):
        """After fetch completes, the key is removed from the registry."""
        dedup_fetch("clean-key", lambda: 42)
        assert not inflight_count()
