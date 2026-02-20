"""Tests for tinkywiki_mcp.stealth — anti-bot-detection utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tinkywiki_mcp.stealth import (
    STEALTH_JS,
    apply_stealth_scripts,
    human_click,
    human_move_to,
    human_type,
    random_delay,
    stealth_context_options,
)


# ---------------------------------------------------------------------------
# stealth_context_options
# ---------------------------------------------------------------------------
class TestStealthContextOptions:
    """Tests for stealth_context_options()."""

    def test_returns_dict(self):
        opts = stealth_context_options()
        assert isinstance(opts, dict)

    def test_has_viewport(self):
        opts = stealth_context_options()
        vp = opts["viewport"]
        assert 1903 <= vp["width"] <= 1920
        assert 1040 <= vp["height"] <= 1080

    def test_has_locale(self):
        opts = stealth_context_options()
        assert opts["locale"] == "en-US"

    def test_has_timezone(self):
        opts = stealth_context_options()
        assert opts["timezone_id"] == "America/New_York"

    def test_has_extra_http_headers(self):
        opts = stealth_context_options()
        headers = opts["extra_http_headers"]
        assert "Accept-Language" in headers
        assert "Sec-CH-UA" in headers
        assert "Sec-CH-UA-Mobile" in headers
        assert "Sec-CH-UA-Platform" in headers

    def test_device_scale_factor_in_range(self):
        """device_scale_factor should be 1 or 2."""
        for _ in range(20):
            opts = stealth_context_options()
            assert opts["device_scale_factor"] in (1, 2)

    def test_no_user_agent_included(self):
        """user_agent is set externally by callers, not in opts."""
        opts = stealth_context_options()
        assert "user_agent" not in opts

    def test_randomisation_produces_variety(self):
        """Multiple calls should produce at least some different viewports."""
        widths = {stealth_context_options()["viewport"]["width"] for _ in range(50)}
        # With 18 possible widths (1903-1920), 50 samples should hit >1
        assert len(widths) > 1


# ---------------------------------------------------------------------------
# STEALTH_JS
# ---------------------------------------------------------------------------
class TestStealthJs:
    """Validate the stealth JS payload is well-formed."""

    def test_is_nonempty_string(self):
        assert isinstance(STEALTH_JS, str)
        assert len(STEALTH_JS) > 200

    def test_patches_webdriver(self):
        assert "navigator" in STEALTH_JS
        assert "webdriver" in STEALTH_JS

    def test_patches_chrome_runtime(self):
        assert "chrome.runtime" in STEALTH_JS

    def test_patches_plugins(self):
        assert "plugins" in STEALTH_JS

    def test_patches_languages(self):
        assert "languages" in STEALTH_JS

    def test_patches_webgl(self):
        assert "WebGLRenderingContext" in STEALTH_JS


# ---------------------------------------------------------------------------
# apply_stealth_scripts
# ---------------------------------------------------------------------------
class TestApplyStealthScripts:
    """Tests for apply_stealth_scripts()."""

    @pytest.mark.asyncio
    async def test_calls_add_init_script(self):
        page = AsyncMock()
        await apply_stealth_scripts(page)
        page.add_init_script.assert_awaited_once_with(STEALTH_JS)


# ---------------------------------------------------------------------------
# human_type
# ---------------------------------------------------------------------------
class TestHumanType:
    """Tests for human_type()."""

    @pytest.mark.asyncio
    async def test_types_all_characters(self):
        locator = AsyncMock()
        text = "hello"
        await human_type(locator, text, min_delay=1, max_delay=2)
        # Each char should produce one press() call
        assert locator.press.await_count == len(text)

    @pytest.mark.asyncio
    async def test_correct_characters(self):
        locator = AsyncMock()
        text = "abc"
        await human_type(locator, text, min_delay=1, max_delay=2)
        calls = [c.args[0] for c in locator.press.await_args_list]
        assert calls == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_empty_string(self):
        locator = AsyncMock()
        await human_type(locator, "", min_delay=1, max_delay=2)
        locator.press.assert_not_awaited()


# ---------------------------------------------------------------------------
# human_move_to
# ---------------------------------------------------------------------------
class TestHumanMoveTo:
    """Tests for human_move_to()."""

    @pytest.mark.asyncio
    async def test_moves_mouse(self):
        page = MagicMock()
        page.mouse = AsyncMock()
        page.mouse.move = AsyncMock()

        locator = AsyncMock()
        locator.bounding_box.return_value = {
            "x": 100,
            "y": 200,
            "width": 50,
            "height": 30,
        }

        await human_move_to(page, locator, steps=10)
        page.mouse.move.assert_awaited_once()
        args = page.mouse.move.await_args
        assert args is not None
        # Target should be within the bounding box
        assert 100 <= args[0][0] <= 150  # x within box
        assert 200 <= args[0][1] <= 230  # y within box

    @pytest.mark.asyncio
    async def test_no_bounding_box(self):
        """If bounding_box returns None, do nothing."""
        page = MagicMock()
        page.mouse = AsyncMock()
        page.mouse.move = AsyncMock()

        locator = AsyncMock()
        locator.bounding_box.return_value = None

        await human_move_to(page, locator)
        page.mouse.move.assert_not_awaited()


# ---------------------------------------------------------------------------
# human_click
# ---------------------------------------------------------------------------
class TestHumanClick:
    """Tests for human_click()."""

    @pytest.mark.asyncio
    async def test_moves_then_clicks(self):
        page = MagicMock()
        page.mouse = AsyncMock()
        page.mouse.move = AsyncMock()

        locator = AsyncMock()
        locator.bounding_box.return_value = {
            "x": 10,
            "y": 20,
            "width": 100,
            "height": 40,
        }

        await human_click(page, locator)
        # Should have moved the mouse
        page.mouse.move.assert_awaited_once()
        # Should have clicked
        locator.click.assert_awaited_once()


# ---------------------------------------------------------------------------
# random_delay
# ---------------------------------------------------------------------------
class TestRandomDelay:
    """Tests for random_delay()."""

    @pytest.mark.asyncio
    async def test_completes_quickly(self):
        """With tiny bounds, should finish fast."""
        await random_delay(0.001, 0.002)  # just verify no crash
