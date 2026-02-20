"""tinkywiki_request_indexing tool — Submit a repo to TinkyWiki for indexing.

When a repository is not yet indexed by Google TinkyWiki, this tool:
1. Searches for the repo on TinkyWiki's homepage.
2. Clicks "Request repository" if the repo is not found.
3. Fills in the repo URL in the dialog and submits.
4. Returns a confirmation message with next-step guidance.

Uses Playwright (via the shared browser loop) to interact with the
TinkyWiki Angular SPA, following the same patterns as tinkywiki_search_wiki.
"""

from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse

from typing import Literal

from anyio import from_thread
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .. import config
from ..browser import _get_browser, run_in_browser_loop
from ..stealth import apply_stealth_scripts, random_delay, stealth_context_options
from ..types import (
    ErrorCode,
    ResponseMeta,
    ResponseStatus,
    ToolResponse,
    validate_topics_input,
)
from ._helpers import build_tinkywiki_url, build_resolution_note, pre_resolve_keyword

logger = logging.getLogger("TinkyWiki")


# ---------------------------------------------------------------------------
# DeepWiki indexing helper (v1.4.0)
# ---------------------------------------------------------------------------
def _try_deepwiki_indexing(repo_url: str) -> str | None:
    """Best-effort DeepWiki indexing request. Returns a note or None."""
    if not config.DEEPWIKI_ENABLED:
        return None
    try:
        from ..deepwiki import deepwiki_request_indexing  # noqa: E402
        success = deepwiki_request_indexing(repo_url)
        if success:
            return (
                f"**DeepWiki:** Also submitted indexing request. "
                f"Visit {config.DEEPWIKI_BASE_URL}/"
                f"{repo_url.replace('https://github.com/', '')} to check status."
            )
        return (
            f"**DeepWiki:** Could not submit indexing request. "
            f"Try visiting {config.DEEPWIKI_BASE_URL}/"
            f"{repo_url.replace('https://github.com/', '')} directly."
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("DeepWiki indexing request failed: %s", exc)
        return (
            f"**DeepWiki:** Indexing request failed ({exc}). "
            f"Try visiting {config.DEEPWIKI_BASE_URL}/"
            f"{repo_url.replace('https://github.com/', '')} directly."
        )

# ---------------------------------------------------------------------------
# Selectors for the request-repo flow
# ---------------------------------------------------------------------------
SEARCH_INPUT_SELECTOR = "input[type='text'], input[type='search'], textbox"
REQUEST_REPO_BUTTON = "button:has-text('Request repository')"
DIALOG_URL_INPUT = "dialog input, dialog textbox"
DIALOG_SUBMIT_BUTTON = "dialog button:has-text('Submit')"
CONFIRMATION_HEADING = "h3:has-text('Repo requested')"


# ---------------------------------------------------------------------------
# MCP Elicitation — indexing confirmation
# ---------------------------------------------------------------------------
class _IndexingConfirmation(BaseModel):
    """Schema for the indexing confirmation elicitation."""

    confirm: Literal["Yes, request indexing", "No, skip indexing"] = Field(
        description="Do you want to request TinkyWiki to index this repository?",
    )


async def _elicit_indexing_confirmation(repo_url: str, ctx: Context) -> bool:
    """Ask the user to confirm before submitting an indexing request.

    Returns *True* if the user accepted, *False* otherwise.
    """
    result = await ctx.elicit(
        message=(
            f"The repository **{repo_url}** will be submitted to Google "
            f"TinkyWiki for indexing.\n\n"
            f"**Note:** Google reviews requests and indexes repos based on "
            f"popularity and demand — there is no guaranteed timeline.\n\n"
            f"Would you like to proceed?"
        ),
        schema=_IndexingConfirmation,
    )
    if result.action == "accept":
        # Handle both dict and Pydantic model responses
        value = (
            result.data.get("confirm", "")
            if isinstance(result.data, dict)
            else getattr(result.data, "confirm", "")
        )
        return value == "Yes, request indexing"
    return False


# ---------------------------------------------------------------------------
# Async implementation
# ---------------------------------------------------------------------------
def _build_search_url(repo_url: str) -> str:
    """Build the TinkyWiki search URL for a repo."""
    clean = repo_url.replace("https://github.com/", "").replace(
        "http://github.com/", ""
    )
    return (
        f"{config.TINKYWIKI_BASE_URL}/search"
        f"?q={urllib.parse.quote(clean, safe='')}"
    )


def _request_button_missing_response(repo_url: str, search_url: str) -> ToolResponse:
    """Build response for missing request button."""
    return ToolResponse(
        status=ResponseStatus.OK,
        code=ErrorCode.NOT_INDEXED,
        data=(
            f"Could not find the 'Request repository' button for "
            f"**{repo_url}**. The repo may already be queued for "
            f"indexing, or TinkyWiki's UI has changed.\n\n"
            f"You can try manually at: {search_url}"
        ),
        repo_url=repo_url,
    )


def _dialog_input_missing_response(repo_url: str, search_url: str) -> ToolResponse:
    """Build response for missing dialog input field."""
    return ToolResponse(
        status=ResponseStatus.OK,
        code=ErrorCode.NOT_INDEXED,
        data=(
            f"The request dialog opened but the URL input field "
            f"was not found for **{repo_url}**.\n\n"
            f"Please submit manually at: {search_url}"
        ),
        repo_url=repo_url,
    )


def _submit_failed_response(
    repo_url: str,
    search_url: str,
    exc: Exception,
) -> ToolResponse:
    """Build response for submit failures."""
    return ToolResponse(
        status=ResponseStatus.OK,
        code=ErrorCode.NOT_INDEXED,
        data=(
            f"Filled URL but could not click Submit for **{repo_url}**: "
            f"{exc}\n\nPlease submit manually at: {search_url}"
        ),
        repo_url=repo_url,
    )


async def _find_dialog_url_input(page: object) -> object | None:
    """Find URL input inside the request dialog."""
    try:
        url_input = page.get_by_role("textbox", name="Enter URL")
        await url_input.wait_for(state="visible", timeout=5_000)
        return url_input
    except PlaywrightTimeoutError:
        try:
            fallback = page.locator("dialog textbox, dialog input").first
            await fallback.wait_for(state="visible", timeout=3_000)
            return fallback
        except (PlaywrightTimeoutError, RuntimeError, ValueError, TypeError):
            return None


async def _click_submit(page: object) -> None:
    """Click submit in the request dialog after it becomes enabled."""
    submit_btn = page.get_by_role("button", name="Submit")
    await submit_btn.wait_for(state="visible", timeout=3_000)
    for _ in range(10):
        if not await submit_btn.is_disabled():
            break
        await asyncio.sleep(0.3)
    await submit_btn.click()
    logger.debug("Clicked 'Submit' in request dialog")


async def _is_confirmed(page: object) -> bool:
    """Detect whether TinkyWiki showed request confirmation."""
    try:
        heading = page.get_by_role("heading", name="Repo requested")
        if await heading.is_visible(timeout=5_000):
            return True
    except (PlaywrightTimeoutError, RuntimeError, ValueError, TypeError):
        logger.debug("Suppressed exception during cleanup", exc_info=True)

    try:
        body_text = await page.inner_text("body")
        return (
            "repo requested" in body_text.lower()
            or "we'll review" in body_text.lower()
        )
    except (PlaywrightTimeoutError, RuntimeError, ValueError, TypeError):
        logger.debug("Suppressed exception during cleanup", exc_info=True)
        return False


def _build_outcome_message(repo_url: str, search_url: str, confirmed: bool) -> str:
    """Build success/uncertain response message."""
    tinkywiki_url = build_tinkywiki_url(repo_url)
    if confirmed:
        return (
            f"**Indexing request submitted successfully** for "
            f"**{repo_url}**.\n\n"
            f'Google TinkyWiki confirmed: *"Repo requested — Thanks for '
            f"reaching out. We'll review your request.\"*\n\n"
            f"**What to do next:**\n"
            f"- The wiki will be generated once Google reviews and "
            f"approves the request.\n"
            f"- Check back later at: {tinkywiki_url}\n"
            f"- Indexing timelines vary — popular repos with more stars "
            f"and activity are typically indexed sooner.\n"
            f"- Try querying this repo again in a few days."
        )

    return (
        f"The indexing request was submitted for **{repo_url}**, "
        f"but we could not confirm whether it was accepted.\n\n"
        f"**What to do next:**\n"
        f"- Check: {tinkywiki_url}\n"
        f"- Or submit manually at: {search_url}\n"
        f"- Try again in a few days."
    )


async def _request_indexing_impl(repo_url: str) -> ToolResponse:
    """Submit a repo-indexing request on TinkyWiki via Playwright."""
    search_url = _build_search_url(repo_url)

    browser = await _get_browser()
    ctx_opts = stealth_context_options()
    ctx_opts["user_agent"] = config.USER_AGENT
    context = await browser.new_context(**ctx_opts)
    page = await context.new_page()
    await apply_stealth_scripts(page)

    try:
        logger.info("tinkywiki_request_indexing: navigating to %s", search_url)
        await page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=config.PAGE_LOAD_TIMEOUT_SECONDS * 1000,
        )
        await asyncio.sleep(config.JS_LOAD_DELAY_SECONDS)

        req_btn = page.get_by_role("button", name="Request repository")
        try:
            await req_btn.wait_for(state="visible", timeout=10_000)
        except PlaywrightTimeoutError:
            return _request_button_missing_response(repo_url, search_url)

        await random_delay(0.3, 0.8)
        await req_btn.click()
        logger.debug("Clicked 'Request repository'")
        await random_delay(0.5, 1.0)

        url_input = await _find_dialog_url_input(page)
        if url_input is None:
            return _dialog_input_missing_response(repo_url, search_url)

        await url_input.fill(repo_url)
        await random_delay(0.3, 0.6)

        try:
            await _click_submit(page)
        except (
            PlaywrightTimeoutError,
            asyncio.TimeoutError,
            RuntimeError,
            ValueError,
            TypeError,
        ) as exc:
            return _submit_failed_response(repo_url, search_url, exc)

        await asyncio.sleep(2)
        confirmed = await _is_confirmed(page)
        message = _build_outcome_message(repo_url, search_url, confirmed)

        return ToolResponse(
            status=ResponseStatus.OK,
            code=ErrorCode.NOT_INDEXED,
            data=message,
            repo_url=repo_url,
            meta=ResponseMeta(char_count=len(message)),
        )

    except (
        PlaywrightTimeoutError,
        asyncio.TimeoutError,
        RuntimeError,
        ValueError,
        TypeError,
    ) as exc:
        logger.error("tinkywiki_request_indexing failed: %s", exc)
        return ToolResponse.error(
            ErrorCode.DRIVER_ERROR,
            f"Playwright error during indexing request: {exc}",
            repo_url=repo_url,
        )
    finally:
        await page.close()
        await context.close()


# ---------------------------------------------------------------------------
# Sync wrapper
# ---------------------------------------------------------------------------
def _run_request_indexing(repo_url: str) -> ToolResponse:
    """Run the async request in the persistent Playwright event loop."""
    try:
        return run_in_browser_loop(_request_indexing_impl(repo_url))
    except asyncio.TimeoutError:
        return ToolResponse.error(
            ErrorCode.TIMEOUT,
            f"Request timed out after {config.HARD_TIMEOUT_SECONDS}s.",
            repo_url=repo_url,
        )
    except (RuntimeError, ValueError, TypeError) as exc:
        return ToolResponse.error(
            ErrorCode.INTERNAL,
            str(exc),
            repo_url=repo_url,
        )


# ---------------------------------------------------------------------------
# Public: tool registration
# ---------------------------------------------------------------------------
def register(mcp: FastMCP) -> None:
    """Register the tinkywiki_request_indexing tool on the MCP server."""

    @mcp.tool()
    def tinkywiki_request_indexing(repo_url: str, ctx: Context) -> str:
        """
        Request Google TinkyWiki to index a repository that is not yet available.

        Use this tool when ``tinkywiki_list_topics`` or ``tinkywiki_read_structure``
        returns a ``NOT_INDEXED`` error, indicating the repository has no
        TinkyWiki documentation yet.

        This tool will:
        1. Search for the repository on TinkyWiki.
        2. Click "Request repository" to open the submission dialog.
        3. Fill in the GitHub URL and submit the request.
        4. Return confirmation and next-step guidance.

        **Note**: Google TinkyWiki reviews requests and indexes repositories
        based on popularity and demand.  There is no guaranteed timeline.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/owner/repo)
                      or shorthand owner/repo (e.g. owner/repo).
                      Bare keywords (e.g. 'vue') are auto-resolved with
                      interactive disambiguation.
        """
        start = time.monotonic()
        logger.info("tinkywiki_request_indexing — repo: %s", repo_url)

        original_input = repo_url  # save before resolution
        repo_url = pre_resolve_keyword(repo_url, ctx)  # elicitation for bare keywords

        validated = validate_topics_input(repo_url)
        if isinstance(validated, ToolResponse):
            return validated.to_text()

        note = build_resolution_note(original_input, validated.repo_url)

        # --- Elicit confirmation before submitting indexing request ---
        try:
            confirmed = from_thread.run(
                _elicit_indexing_confirmation,
                validated.repo_url,
                ctx,
            )
            if not confirmed:
                skip_msg = (
                    f"Indexing request **skipped** for **{validated.repo_url}**.\n\n"
                    f"You can request indexing later by calling this tool again, "
                    f"or submit manually at: "
                    f"{config.TINKYWIKI_BASE_URL}/search?q="
                    f"{urllib.parse.quote(validated.repo_url, safe='')}"
                )
                result = ToolResponse(
                    status=ResponseStatus.OK,
                    code=ErrorCode.NOT_INDEXED,
                    data=skip_msg,
                    repo_url=validated.repo_url,
                )
                result.meta.elapsed_ms = int((time.monotonic() - start) * 1000)
                if note:
                    result.data = note + (result.data or "")
                return result.to_text()
        except (RuntimeError, ValueError, TypeError) as exc:
            logger.warning(
                "Elicitation failed for indexing confirmation (client may not "
                "support it): %s — proceeding without confirmation",
                exc,
            )
            # Fall through: submit without confirmation (backward compat)

        result = _run_request_indexing(validated.repo_url)
        result.meta.elapsed_ms = int((time.monotonic() - start) * 1000)
        if result.data and note:
            result.data = note + (result.data or "")

        # --- v1.4.0: Also try DeepWiki indexing ---
        deepwiki_note = _try_deepwiki_indexing(validated.repo_url)
        if deepwiki_note and result.data:
            result.data += f"\n\n---\n{deepwiki_note}"

        return result.to_text()
