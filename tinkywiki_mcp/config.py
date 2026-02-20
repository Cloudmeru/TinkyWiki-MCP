"""Environment-variable-driven configuration for TinkyWiki MCP.

All settings have sensible defaults and can be overridden via env vars
(like DeepWiki MCP's DEEPWIKI_MAX_CONCURRENCY / DEEPWIKI_REQUEST_TIMEOUT).
"""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name, "")
    if val.strip():
        try:
            return int(val)
        except ValueError:
            pass
    return default


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name, "").strip().lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    return default


# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
HARD_TIMEOUT_SECONDS: int = _env_int("TINKYWIKI_HARD_TIMEOUT", 60)
PAGE_LOAD_TIMEOUT_SECONDS: int = _env_int("TINKYWIKI_PAGE_LOAD_TIMEOUT", 30)
ELEMENT_WAIT_TIMEOUT_SECONDS: int = _env_int("TINKYWIKI_ELEMENT_WAIT_TIMEOUT", 20)
RESPONSE_WAIT_TIMEOUT_SECONDS: int = _env_int("TINKYWIKI_RESPONSE_WAIT_TIMEOUT", 45)
HTTPX_TIMEOUT_SECONDS: int = _env_int("TINKYWIKI_HTTPX_TIMEOUT", 30)

# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------
MAX_RETRIES: int = _env_int("TINKYWIKI_MAX_RETRIES", 2)
RETRY_DELAY_SECONDS: int = _env_int("TINKYWIKI_RETRY_DELAY", 3)

# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------
RESPONSE_MAX_CHARS: int = _env_int("TINKYWIKI_RESPONSE_MAX_CHARS", 30000)

# ---------------------------------------------------------------------------
# Cache (cachetools TTLCache)
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS: int = _env_int("TINKYWIKI_CACHE_TTL", 300)  # 5 minutes
CACHE_MAX_SIZE: int = _env_int("TINKYWIKI_CACHE_MAX_SIZE", 50)
SEARCH_CACHE_TTL_SECONDS: int = _env_int("TINKYWIKI_SEARCH_CACHE_TTL", 120)  # 2 minutes
SEARCH_CACHE_MAX_SIZE: int = _env_int("TINKYWIKI_SEARCH_CACHE_MAX_SIZE", 30)
PARSED_CACHE_MAX_SIZE: int = _env_int("TINKYWIKI_PARSED_CACHE_MAX_SIZE", 30)

# Topic-list cache — structural data that rarely changes (longer TTL)
TOPIC_CACHE_TTL_SECONDS: int = _env_int("TINKYWIKI_TOPIC_CACHE_TTL", 1800)  # 30 min
TOPIC_CACHE_MAX_SIZE: int = _env_int("TINKYWIKI_TOPIC_CACHE_MAX_SIZE", 30)

# ---------------------------------------------------------------------------
# Rate limiting (per-repo sliding window)
# ---------------------------------------------------------------------------
RATE_LIMIT_WINDOW_SECONDS: int = _env_int("TINKYWIKI_RATE_LIMIT_WINDOW", 60)
RATE_LIMIT_MAX_CALLS: int = _env_int("TINKYWIKI_RATE_LIMIT_MAX_CALLS", 10)
RATE_LIMIT_AUTO_WAIT: bool = (
    os.environ.get("TINKYWIKI_RATE_LIMIT_AUTO_WAIT", "1").strip().lower()
    not in ("0", "false", "no")
)
RATE_LIMIT_MAX_WAIT_SECONDS: int = _env_int("TINKYWIKI_RATE_LIMIT_MAX_WAIT", 30)

# ---------------------------------------------------------------------------
# Playwright chat timing
# ---------------------------------------------------------------------------
RESPONSE_INITIAL_DELAY_SECONDS: int = _env_int("TINKYWIKI_RESPONSE_INITIAL_DELAY", 5)
RESPONSE_POLL_INTERVAL_SECONDS: int = _env_int("TINKYWIKI_RESPONSE_POLL_INTERVAL", 2)
RESPONSE_STABLE_INTERVAL_SECONDS: int = _env_int("TINKYWIKI_RESPONSE_STABLE_INTERVAL", 2)
JS_LOAD_DELAY_SECONDS: int = _env_int("TINKYWIKI_JS_LOAD_DELAY", 3)
INPUT_CLEAR_DELAY: float = 0.3
INPUT_TYPE_DELAY: float = 0.5
SUBMIT_DELAY: float = 1.0

# ---------------------------------------------------------------------------
# Content detection
# ---------------------------------------------------------------------------
NEW_CONTENT_THRESHOLD_CHARS: int = 50
FALLBACK_MIN_TEXT_LENGTH: int = 20

# ---------------------------------------------------------------------------
# Topic preview
# ---------------------------------------------------------------------------
TOPIC_PREVIEW_CHARS: int = _env_int("TINKYWIKI_TOPIC_PREVIEW_CHARS", 200)

# ---------------------------------------------------------------------------
# Session pool
# ---------------------------------------------------------------------------
SESSION_POOL_SIZE: int = _env_int("TINKYWIKI_SESSION_POOL_SIZE", 10)

# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------
VERBOSE: bool = _env_bool("TINKYWIKI_VERBOSE", False)

# ---------------------------------------------------------------------------
# Base URL
# ---------------------------------------------------------------------------
TINKYWIKI_BASE_URL: str = os.environ.get("TINKYWIKI_BASE_URL", "https://codewiki.google")

# ---------------------------------------------------------------------------
# Request / indexing URL (shown to users when a repo is not indexed)
# ---------------------------------------------------------------------------
TINKYWIKI_REQUEST_URL: str = os.environ.get(
    "TINKYWIKI_REQUEST_URL",
    "https://codewiki.google",
)

# ---------------------------------------------------------------------------
# DeepWiki — second-layer fallback (v1.4.0)
# ---------------------------------------------------------------------------
DEEPWIKI_BASE_URL: str = os.environ.get("DEEPWIKI_BASE_URL", "https://deepwiki.com")
DEEPWIKI_ENABLED: bool = _env_bool("DEEPWIKI_ENABLED", True)

# ---------------------------------------------------------------------------
# GitHub API — last-resort fallback (v1.4.0)
# ---------------------------------------------------------------------------
GITHUB_API_BASE_URL: str = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
GITHUB_API_ENABLED: bool = _env_bool("GITHUB_API_ENABLED", True)
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API_TIMEOUT: int = _env_int("GITHUB_API_TIMEOUT", 15)

# ---------------------------------------------------------------------------
# Fallback control (v1.4.0)
# ---------------------------------------------------------------------------
FALLBACK_ENABLED: bool = _env_bool("TINKYWIKI_FALLBACK_ENABLED", True)

# Strings that indicate a 404 / not-indexed page in TinkyWiki's rendered HTML
NOT_INDEXED_INDICATORS: list[str] = [
    "This page doesn\u2019t exist",  # curly apostrophe on the 404 page
    "This page doesn't exist",
    "404",
]

# ---------------------------------------------------------------------------
# User agent — keep in sync with a recent stable Chrome release
# ---------------------------------------------------------------------------
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Selectors (for Playwright chat interaction — TinkyWiki Angular SPA)
#
# These selectors target the actual TinkyWiki SPA elements:
#   <chat class="is-open">
#     <thread>  →  <cdk-virtual-scroll-viewport>  (messages)
#     <new-message-form>  →  <form>  →  <textarea id="message-textarea">
#     <button data-test-id="send-message-button">
# ---------------------------------------------------------------------------
CHAT_ELEMENT_SELECTOR: str = "chat"
CHAT_OPEN_SELECTOR: str = "chat.is-open"
CHAT_TOGGLE_SELECTOR: str = "chat-toggle button"

CHAT_INPUT_SELECTORS: list[str] = [
    "textarea[data-test-id='chat-input']",
    "textarea#message-textarea",
    "textarea[placeholder*='Ask about this repository']",
    "new-message-form textarea",
    "chat textarea",
]

SUBMIT_BUTTON_SELECTORS: list[str] = [
    "button[data-test-id='send-message-button']",
    "button[aria-label='Send message']",
    "new-message-form button[type='submit']",
    "chat .send-button",
]

# Response messages appear inside the <thread> → <cdk-virtual-scroll-viewport>
CHAT_THREAD_SELECTOR: str = "chat thread"
CHAT_SCROLL_VIEWPORT: str = "chat cdk-virtual-scroll-viewport"
CHAT_SCROLL_CONTENT: str = "chat .cdk-virtual-scroll-content-wrapper"

# Individual message elements inside the thread
RESPONSE_ELEMENT_SELECTORS: list[str] = [
    "chat .cdk-virtual-scroll-content-wrapper documentation-markdown",
    "chat .cdk-virtual-scroll-content-wrapper",
    "chat thread",
]

# The empty state has "Hi there!" — we use this to detect pre-response state
CHAT_EMPTY_STATE_SELECTOR: str = "chat .empty-house-container"

UI_ARTIFACTS: list[str] = [
    "content_copy",
    "refresh",
    "thumb_up",
    "thumb_down",
    "arrow_menu_open",
    "Gemini can make mistakes, so double-check it.",
]

# ---------------------------------------------------------------------------
# DeepWiki selectors (v1.4.0)
# ---------------------------------------------------------------------------
# DeepWiki is a Next.js app with sidebar navigation + markdown content areas.
# Topics are in sidebar <a> links pointing to /owner/repo/slug.
# Content is rendered in the main content area as standard HTML headings + text.
DEEPWIKI_SIDEBAR_SELECTOR: str = "nav a[href], aside a[href]"
DEEPWIKI_CONTENT_SELECTORS: list[str] = [
    "article",
    "main",
    ".prose",
    "[class*='content']",
    "[class*='markdown']",
]
DEEPWIKI_NOT_INDEXED_INDICATORS: list[str] = [
    "Profile Not Found",
    "GitHub profile not found",
    "Repository not found",
    "not found",
]
DEEPWIKI_ASK_INPUT_SELECTORS: list[str] = [
    "textarea[placeholder*='Ask']",
    "textarea[placeholder*='ask']",
    "textarea[placeholder*='question']",
    "input[placeholder*='Ask']",
    "textarea",
]
DEEPWIKI_ASK_SUBMIT_SELECTORS: list[str] = [
    "button[type='submit']",
    "button[aria-label*='send']",
    "button[aria-label*='Send']",
    "button:has(svg)",
]
DEEPWIKI_UI_ARTIFACTS: list[str] = [
    "Fast",
    "Detailed",
]
