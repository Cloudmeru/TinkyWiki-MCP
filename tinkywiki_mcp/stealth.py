"""Browser stealth utilities — anti-bot-detection measures for Playwright.

Google TinkyWiki may block or throttle requests from browsers that appear to
be automated.  This module patches Playwright pages and contexts to look
like a real, manually-operated Chrome browser.

Techniques applied:
1. JavaScript property overrides (webdriver, plugins, languages, etc.)
2. Realistic viewport + device-scale-factor
3. Human-like typing with per-character jitter
4. Human-like mouse movement (Bézier curves) before click targets
5. Randomised timing between interactions
"""

from __future__ import annotations

import asyncio
import logging
import random

logger = logging.getLogger("TinkyWiki")

# ---------------------------------------------------------------------------
# 1. JavaScript stealth patches (injected before every navigation)
# ---------------------------------------------------------------------------
STEALTH_JS = """
// ── navigator.webdriver ──────────────────────────────────────────
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true,
});

// ── chrome.runtime (present in real Chrome, missing in headless) ──
if (!window.chrome) { window.chrome = {}; }
if (!window.chrome.runtime) {
    window.chrome.runtime = {
        connect: function() {},
        sendMessage: function() {},
    };
}

// ── navigator.plugins (headless has length 0) ────────────────────
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin',       filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer',        filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client',            filename: 'internal-nacl-plugin' },
        ];
        plugins.length = 3;
        return plugins;
    },
    configurable: true,
});

// ── navigator.languages ──────────────────────────────────────────
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
    configurable: true,
});

// ── navigator.permissions.query override ─────────────────────────
if (navigator.permissions) {
    const origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (params) => {
        if (params.name === 'notifications') {
            return Promise.resolve({ state: Notification.permission });
        }
        return origQuery(params);
    };
}

// ── WebGL vendor/renderer (headless returns "Google Inc." / "ANGLE") ──
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Google Inc. (NVIDIA)';
    if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650)';
    return getParameter.call(this, parameter);
};

// ── Prevent iframe-based detection of headless ───────────────────
// Some sites check window.outerWidth / outerHeight = 0
if (window.outerWidth === 0) {
    Object.defineProperty(window, 'outerWidth',  { get: () => window.innerWidth });
    Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight });
}
"""


async def apply_stealth_scripts(page) -> None:
    """Inject stealth JS into *page* so it runs before every navigation.

    Uses ``add_init_script`` which fires before any page JS executes,
    making the overrides invisible to fingerprinting libraries.
    """
    await page.add_init_script(STEALTH_JS)
    logger.debug("Stealth scripts injected into page")


# ---------------------------------------------------------------------------
# 2. Stealth-aware browser-context factory options
# ---------------------------------------------------------------------------
def stealth_context_options() -> dict:
    """Return ``browser.new_context(**opts)`` kwargs that reduce detection.

    Randomises minor details so successive contexts don't share a single
    fingerprint.
    """
    # Slight viewport jitter (real monitors aren't always exactly 1920×1080)
    width = random.randint(1903, 1920)
    height = random.randint(1040, 1080)

    return {
        "viewport": {"width": width, "height": height},
        "screen": {"width": 1920, "height": 1080},
        "device_scale_factor": random.choice([1, 1, 1, 2]),  # mostly 1
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "color_scheme": "light",
        "has_touch": False,
        # Permissions that a normal user would have granted
        "permissions": ["geolocation"],
        # Important: set extra HTTP headers that headless Chrome omits
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-CH-UA": (
                '"Chromium";v="132", '
                '"Google Chrome";v="132", '
                '"Not-A.Brand";v="99"'
            ),
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
        },
    }


# ---------------------------------------------------------------------------
# 3. Human-like typing
# ---------------------------------------------------------------------------
async def human_type(
    locator, text: str, *, min_delay: int = 35, max_delay: int = 120
) -> None:
    """Type *text* into *locator* character-by-character with random delays.

    Real humans type at roughly 40-80 ms/char with occasional pauses.
    This produces a natural cadence that defeats keystroke-timing analysis.

    Args:
        locator:   Playwright Locator (e.g. a textarea).
        text:      The string to type.
        min_delay: Minimum per-key delay in milliseconds.
        max_delay: Maximum per-key delay in milliseconds.
    """
    for i, ch in enumerate(text):
        await locator.press(ch if len(ch) == 1 else ch)
        # Occasional "thinking" pause every 5-15 chars
        if i > 0 and not i % random.randint(5, 15):
            await asyncio.sleep(random.uniform(0.15, 0.4))
        else:
            await asyncio.sleep(random.randint(min_delay, max_delay) / 1000)

    logger.debug("Human-typed %d chars", len(text))


# ---------------------------------------------------------------------------
# 4. Human-like mouse movement (simplified Bézier)
# ---------------------------------------------------------------------------
async def human_move_to(page, locator, *, steps: int | None = None) -> None:
    """Move the mouse to *locator* along a slightly curved path.

    Real humans don't teleport the cursor — they sweep across the screen.
    This moves the mouse with small random offsets to simulate that.

    Args:
        page:    Playwright Page.
        locator: Target Playwright Locator to move toward.
        steps:   Number of intermediate points (default: random 8-20).
    """
    box = await locator.bounding_box()
    if not box:
        return

    # Target: a random point inside the element (not dead centre)
    target_x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
    target_y = box["y"] + box["height"] * random.uniform(0.25, 0.75)

    if steps is None:
        steps = random.randint(8, 20)

    await page.mouse.move(target_x, target_y, steps=steps)
    logger.debug("Mouse moved to (%.0f, %.0f) in %d steps", target_x, target_y, steps)


async def human_click(page, locator) -> None:
    """Move mouse to *locator* then click with a small random delay."""
    await human_move_to(page, locator)
    await asyncio.sleep(random.uniform(0.05, 0.2))
    await locator.click()


# ---------------------------------------------------------------------------
# 5. Random micro-delays (sprinkle between interactions)
# ---------------------------------------------------------------------------
async def random_delay(low: float = 0.3, high: float = 1.2) -> None:
    """Sleep for a random duration to break mechanical timing patterns."""
    await asyncio.sleep(random.uniform(low, high))
