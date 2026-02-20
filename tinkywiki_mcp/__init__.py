"""TinkyWiki MCP Server — AI-powered access to Google TinkyWiki."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__: str = version("tinkywiki-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
