"""Tests for per-repo sliding-window rate limiter."""

from __future__ import annotations

from unittest.mock import patch

from tinkywiki_mcp.rate_limit import (
    check_rate_limit,
    rate_limit_remaining,
    reset_rate_limits,
    time_until_next_slot,
    wait_for_rate_limit,
)


class TestRateLimit:
    def setup_method(self):
        reset_rate_limits()

    def test_allows_under_limit(self):
        """Calls within the limit are all allowed."""
        for _ in range(10):
            assert check_rate_limit("repo-a") is True

    def test_blocks_over_limit(self):
        """The 11th call in the window is rejected."""
        for _ in range(10):
            check_rate_limit("repo-b")
        assert check_rate_limit("repo-b") is False

    def test_different_keys_independent(self):
        """Rate limits are per-key — different repos don't interfere."""
        for _ in range(10):
            check_rate_limit("repo-c")
        # repo-c is exhausted
        assert check_rate_limit("repo-c") is False
        # repo-d is fresh
        assert check_rate_limit("repo-d") is True

    def test_remaining_decreases(self):
        """rate_limit_remaining counts down correctly."""
        assert rate_limit_remaining("repo-e") == 10
        check_rate_limit("repo-e")
        assert rate_limit_remaining("repo-e") == 9
        for _ in range(9):
            check_rate_limit("repo-e")
        assert rate_limit_remaining("repo-e") == 0

    def test_reset_clears_all(self):
        """reset_rate_limits clears all state."""
        for _ in range(10):
            check_rate_limit("repo-f")
        assert check_rate_limit("repo-f") is False
        reset_rate_limits()
        assert check_rate_limit("repo-f") is True
        assert rate_limit_remaining("repo-f") == 9  # one call just made


class TestTimeUntilNextSlot:
    """Tests for time_until_next_slot."""

    def setup_method(self):
        reset_rate_limits()

    def test_slot_available_when_fresh(self):
        """Fresh key has a slot available immediately."""
        assert time_until_next_slot("fresh-key") == 0.0

    def test_slot_available_under_limit(self):
        """Under the limit, slot is available."""
        for _ in range(5):
            check_rate_limit("partial-key")
        assert time_until_next_slot("partial-key") == 0.0

    def test_nonzero_when_exhausted(self):
        """When exhausted, returns positive wait time."""
        for _ in range(10):
            check_rate_limit("full-key")
        wait = time_until_next_slot("full-key")
        assert wait > 0
        assert wait <= 60  # within the window


class TestWaitForRateLimit:
    """Tests for wait_for_rate_limit with auto-wait."""

    def setup_method(self):
        reset_rate_limits()

    def test_allows_when_under_limit(self):
        """Under the limit, returns True immediately."""
        assert wait_for_rate_limit("wait-ok") is True

    def test_auto_wait_disabled_returns_false(self):
        """With auto-wait disabled, behaves like check_rate_limit."""
        for _ in range(10):
            check_rate_limit("wait-disabled")
        with patch("tinkywiki_mcp.rate_limit.config") as mock_config:
            mock_config.RATE_LIMIT_AUTO_WAIT = False
            mock_config.RATE_LIMIT_WINDOW_SECONDS = 60
            mock_config.RATE_LIMIT_MAX_CALLS = 10
            result = wait_for_rate_limit("wait-disabled")
        assert result is False

    def test_auto_wait_rejects_when_wait_too_long(self):
        """When wait exceeds max, returns False."""
        for _ in range(10):
            check_rate_limit("wait-long")
        with patch("tinkywiki_mcp.rate_limit.config") as mock_config:
            mock_config.RATE_LIMIT_AUTO_WAIT = True
            mock_config.RATE_LIMIT_WINDOW_SECONDS = 60
            mock_config.RATE_LIMIT_MAX_CALLS = 10
            mock_config.RATE_LIMIT_MAX_WAIT_SECONDS = 0  # no wait allowed
            result = wait_for_rate_limit("wait-long")
        assert result is False

    @patch("tinkywiki_mcp.rate_limit.time.sleep")
    def test_auto_wait_sleeps_and_retries(self, mock_sleep):
        """When wait is within max, sleeps and retries."""
        # Fill the limit
        for _ in range(10):
            check_rate_limit("wait-sleep")

        # Mock config to allow auto-wait
        with patch("tinkywiki_mcp.rate_limit.config") as mock_config:
            mock_config.RATE_LIMIT_AUTO_WAIT = True
            mock_config.RATE_LIMIT_WINDOW_SECONDS = 60
            mock_config.RATE_LIMIT_MAX_CALLS = 10
            mock_config.RATE_LIMIT_MAX_WAIT_SECONDS = 120

            # After sleep, reset so the retry succeeds
            def sleep_side_effect(_):
                reset_rate_limits()

            mock_sleep.side_effect = sleep_side_effect
            result = wait_for_rate_limit("wait-sleep")

        assert result is True
        mock_sleep.assert_called_once()
