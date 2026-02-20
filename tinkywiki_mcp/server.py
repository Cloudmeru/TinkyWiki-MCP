"""TinkyWiki MCP Server — modular server setup with CLI arguments.

Inspired by DeepWiki MCP's multi-transport and CLI-argument patterns.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from mcp.server.fastmcp import FastMCP

from . import config
from .tools import register_all_tools

# ---------------------------------------------------------------------------
# Logging (configurable via TINKYWIKI_VERBOSE)
# ---------------------------------------------------------------------------
logger = logging.getLogger("TinkyWiki")
logger.setLevel(logging.DEBUG if config.VERBOSE else logging.INFO)
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("[%(name)s %(levelname)s] %(message)s"))
logger.addHandler(_handler)


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
def _shutdown(signum: int, _frame) -> None:
    """Handle SIGINT/SIGTERM — clean up Playwright and exit quietly."""
    sig_name = signal.Signals(signum).name
    logger.info("Received %s — shutting down…", sig_name)

    # Clean up the session pool (best-effort)
    try:
        from .session_pool import (
            cleanup_pool,
        )  # pylint: disable=import-outside-toplevel

        cleanup_pool()
    except (RuntimeError, OSError, asyncio.TimeoutError, ValueError):
        logger.debug("Suppressed exception during cleanup", exc_info=True)

    # Clean up the shared Playwright browser (best-effort)
    try:
        from .browser import (  # pylint: disable=import-outside-toplevel
            cleanup_browser,
            run_in_browser_loop,
        )

        run_in_browser_loop(cleanup_browser())
    except (RuntimeError, OSError, asyncio.TimeoutError, ValueError):
        logger.debug("Suppressed exception during cleanup", exc_info=True)

    logger.info("TinkyWiki MCP server stopped.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------
def create_server(name: str = "TinkyWiki", *, transport: str = "stdio") -> FastMCP:
    """Create and configure the MCP server with all tools registered."""
    mcp = FastMCP(name)
    register_all_tools(mcp)
    logger.info("TinkyWiki MCP server created (transport=%s)", transport)
    return mcp


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments (mirrors DeepWiki MCP's --http/--sse/--port flags)."""
    parser = argparse.ArgumentParser(
        prog="tinkywiki-mcp",
        description="TinkyWiki MCP Server — AI-powered access to Google TinkyWiki",
    )
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument(
        "--stdio",
        action="store_const",
        const="stdio",
        dest="transport",
        help="Run with stdio transport (default)",
    )
    transport.add_argument(
        "--sse",
        action="store_const",
        const="sse",
        dest="transport",
        help="Run with SSE transport",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="Port for SSE transport (default: 3000)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=config.VERBOSE,
        help="Enable verbose/debug logging",
    )
    parser.set_defaults(transport="stdio")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point — starts the MCP server with chosen transport."""
    args = parse_args(argv)

    # ---- ASCII banner (stderr so it never pollutes stdio JSON) ----
    from . import __version__  # pylint: disable=import-outside-toplevel

    banner = (
        "\n"
        "   ___          _    __        ___ _    _   __  __  ___ ___\n"
        "  / __|___   __| |__\\ \\      / (_) | _(_) |  \\/  |/ __| _ \\\n"
        " | |  / _ \\ / _` / -_) \\ /\\ / /| | |/ / | | |\\/| | (__|  _/\n"
        " | |_| (_) | (_| \\___|\\ \\V  V / |_|   <|_| |_|  |_|\\___|_|\n"
        "  \\___\\___/ \\__,_\\___| \\_/\\_/  |_||_|\\_\\_| |___/\n"
        f"                        v{__version__}\n"
        "  TinkyWiki MCP Server 2026 - by CloudMeru\n"
    )
    print(banner, file=sys.stderr, flush=True)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Update log level based on --verbose flag
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    mcp = create_server(transport=args.transport)

    try:
        if args.transport == "sse":
            logger.info("Starting SSE server on port %d...", args.port)
            mcp.run(transport="sse")
        else:
            mcp.run()
    except KeyboardInterrupt:
        pass
    except SystemExit:
        pass
    finally:
        # Ensure session pool + Playwright cleanup even if signal handler didn't fire
        try:
            from .session_pool import (
                cleanup_pool,
            )  # pylint: disable=import-outside-toplevel

            cleanup_pool()
        except (RuntimeError, OSError, asyncio.TimeoutError, ValueError):
            logger.debug("Suppressed exception during cleanup", exc_info=True)
        try:
            from .browser import (  # pylint: disable=import-outside-toplevel
                cleanup_browser,
                run_in_browser_loop,
            )

            run_in_browser_loop(cleanup_browser())
        except (RuntimeError, OSError, asyncio.TimeoutError, ValueError):
            logger.debug("Suppressed exception during cleanup", exc_info=True)
        logger.info("TinkyWiki MCP server stopped.")


if __name__ == "__main__":
    main()
