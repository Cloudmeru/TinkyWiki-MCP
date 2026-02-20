"""Diagnostic script — run our headless Playwright against TinkyWiki chat.

Usage:
    python tests/diagnose_search.py

This replicates exactly what search.py does but with verbose logging at
each step so we can see where the flow breaks.
"""

import asyncio
import time

# ---------------------------------------------------------------------------
# Configuration (mirrors config.py)
# ---------------------------------------------------------------------------
TARGET_URL = "https://codewiki.google/github.com/facebook/react"
QUERY = "What is the React Scheduler?"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36"
)

CHAT_OPEN_SELECTOR = "chat.is-open"
CHAT_TOGGLE_SELECTOR = "chat-toggle button"
CHAT_INPUT_SELECTORS = [
    "textarea[data-test-id='chat-input']",
    "textarea#message-textarea",
    "textarea[placeholder*='Ask about this repository']",
    "new-message-form textarea",
    "chat textarea",
]
SUBMIT_BUTTON_SELECTORS = [
    "button[data-test-id='send-message-button']",
    "button[aria-label='Send message']",
    "new-message-form button[type='submit']",
    "chat .send-button",
]
RESPONSE_ELEMENT_SELECTORS = [
    "chat .cdk-virtual-scroll-content-wrapper documentation-markdown",
    "chat .cdk-virtual-scroll-content-wrapper",
    "chat thread",
]
CHAT_EMPTY_STATE_SELECTOR = "chat .empty-house-container"


def log(msg: str) -> None:
    elapsed = time.monotonic() - _start
    print(f"[{elapsed:7.1f}s] {msg}", flush=True)


_start = time.monotonic()


async def main():
    from playwright.async_api import async_playwright

    log("Launching Playwright (headless)...")
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1920,1080",
            "--start-maximized",
        ],
    )
    log("Browser launched")

    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        screen={"width": 1920, "height": 1080},
        locale="en-US",
        timezone_id="America/New_York",
        color_scheme="light",
        has_touch=False,
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-CH-UA": '"Chromium";v="132", "Google Chrome";v="132", "Not-A.Brand";v="99"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
        },
    )
    page = await context.new_page()

    # Inject stealth JS
    # Import stealth JS inline
    from tinkywiki_mcp.stealth import STEALTH_JS

    await page.add_init_script(STEALTH_JS)
    log("Stealth scripts injected")

    # --- Step 1: Navigate ---
    log(f"Navigating to {TARGET_URL}...")
    await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
    log(f"Page loaded — title: {await page.title()}")

    # Wait for SPA content
    try:
        await page.wait_for_selector(
            "body-content-section, documentation-markdown, h1",
            timeout=20000,
        )
        log("SPA content selector found")
    except Exception as e:
        log(f"SPA content selector timeout: {e}")

    await asyncio.sleep(3)
    log("JS settle done")

    # --- Step 2: Check if chat toggle exists ---
    toggle = page.locator(CHAT_TOGGLE_SELECTOR).first
    is_vis = await toggle.is_visible(timeout=2000)
    log(f"Chat toggle visible: {is_vis}")

    # --- Step 3: Open chat ---
    chat = page.locator(CHAT_OPEN_SELECTOR)
    already_open = False
    try:
        already_open = await chat.is_visible(timeout=2000)
    except Exception:
        pass
    log(f"Chat already open: {already_open}")

    if not already_open:
        log("Clicking chat toggle...")
        await toggle.click()
        await asyncio.sleep(2)
        is_open = await chat.is_visible(timeout=3000)
        log(f"Chat open after click: {is_open}")
        if not is_open:
            log("FATAL: Could not open chat panel")
            await browser.close()
            await pw.stop()
            return

    # --- Step 4: Check empty state ---
    empty = page.locator(CHAT_EMPTY_STATE_SELECTOR)
    empty_visible = False
    try:
        empty_visible = await empty.is_visible(timeout=2000)
    except Exception:
        pass
    log(f"Empty house visible: {empty_visible}")

    # --- Step 5: Find chat input ---
    chat_input = None
    for sel in CHAT_INPUT_SELECTORS:
        try:
            elem = page.locator(sel).first
            if await elem.is_visible(timeout=2000):
                chat_input = elem
                log(f"Found chat input: {sel}")
                break
        except Exception:
            continue
    if not chat_input:
        log("FATAL: No chat input found")
        await browser.close()
        await pw.stop()
        return

    # --- Step 6: Type the query (char by char to mimic human) ---
    await chat_input.click()
    await asyncio.sleep(0.3)
    await chat_input.fill("")
    await asyncio.sleep(0.3)
    log(f"Typing query: '{QUERY}'")
    for ch in QUERY:
        await chat_input.press(ch)
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.5)
    log("Typing done")

    # Check current input value
    val = await chat_input.input_value()
    log(f"Input value: '{val}'")

    # --- Step 7: Check send button ---
    send_btn = None
    for sel in SUBMIT_BUTTON_SELECTORS:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1000):
                disabled = await btn.is_disabled()
                log(f"Send button '{sel}': visible=True, disabled={disabled}")
                if not disabled:
                    send_btn = btn
                    break
        except Exception:
            continue
    if not send_btn:
        log("FATAL: No enabled send button found")
        await browser.close()
        await pw.stop()
        return

    # --- Step 8: Submit via Enter, fall back to click only if Enter didn't work ---
    log("Pressing Enter...")
    await chat_input.press("Enter")
    await asyncio.sleep(0.5)

    # Check if Enter already submitted (button disabled = message sent)
    submitted = False
    for sel in SUBMIT_BUTTON_SELECTORS:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1000):
                if await btn.is_disabled():
                    log("Enter submitted successfully (button now disabled)")
                    submitted = True
                    break
                # Button still enabled → Enter didn't work, click it
                log("Enter didn't submit, clicking send button...")
                await btn.click()
                submitted = True
                break
        except Exception:
            continue

    if not submitted:
        log("WARNING: Could not confirm submission")

    log("Submitted! Waiting for response...")

    # --- Step 9: Wait for empty state to disappear ---
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            ev = page.locator(CHAT_EMPTY_STATE_SELECTOR)
            if not await ev.is_visible(timeout=500):
                log("Empty house disappeared (response arriving)")
                break
        except Exception:
            break
        await asyncio.sleep(1)

    # --- Step 10: Poll for response content ---
    content = ""
    log("Polling for response content...")
    while time.monotonic() < deadline:
        await asyncio.sleep(2)
        for sel in RESPONSE_ELEMENT_SELECTORS:
            try:
                elem = page.locator(sel).last
                if await elem.is_visible(timeout=500):
                    text = await elem.inner_text()
                    if len(text) > 50:
                        content = text
                        log(f"Got response ({len(text)} chars) via '{sel}'")
                        break
            except Exception:
                continue
        if content:
            break
        log(f"  ... no content yet ({time.monotonic() - _start:.1f}s)")

    if not content:
        log("TIMEOUT: No response received")
        # Take a screenshot for debugging
        await page.screenshot(path="tests/diagnose_timeout.png", full_page=False)
        log("Screenshot saved to tests/diagnose_timeout.png")

        # Dump all selectors state
        result = await page.evaluate(
            """() => {
            const r = {};
            r['chat.is-open'] = !!document.querySelector('chat.is-open');
            r['empty-house'] = !!document.querySelector('chat .empty-house-container');
            r['thread'] = !!document.querySelector('chat thread');
            r['doc-markdown'] = !!document.querySelector('chat .cdk-virtual-scroll-content-wrapper documentation-markdown');
            r['scroll-wrapper-text'] = (document.querySelector('chat .cdk-virtual-scroll-content-wrapper') || {}).innerText || '';
            return r;
        }"""
        )
        log(f"DOM state at timeout: {result}")
    else:
        log(f"SUCCESS! Response preview: {content[:200]}...")

    # --- Cleanup ---
    await page.close()
    await context.close()
    await browser.close()
    await pw.stop()
    log("Done")


if __name__ == "__main__":
    asyncio.run(main())
