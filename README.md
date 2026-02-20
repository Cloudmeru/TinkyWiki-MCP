# TinkyWiki MCP Server

<p align="center">
  <img src="https://raw.githubusercontent.com/Cloudmeru/TinkyWiki-MCP/main/docs/favicon.svg" alt="TinkyWiki MCP logo" width="96" height="96">
</p>

<p align="center">
  <a href="https://pypi.org/project/tinkywiki-mcp/"><img src="https://img.shields.io/pypi/v/tinkywiki-mcp" alt="PyPI"></a>
  <a href="https://github.com/Cloudmeru/TinkyWiki-MCP/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Cloudmeru/TinkyWiki-MCP" alt="License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/pypi/pyversions/tinkywiki-mcp" alt="Python"></a>
</p>

An [MCP](https://modelcontextprotocol.io/) server that brings [Google TinkyWiki](https://codewiki.google/) into your editor. Query any GitHub, GitLab, or Bitbucket repository and get AI-generated answers about the codebase — powered by Gemini.

**[Documentation](https://cloudmeru.github.io/TinkyWiki-MCP)** · **[Release Notes](https://cloudmeru.github.io/TinkyWiki-MCP/release-notes.html)** · **[PyPI](https://pypi.org/project/tinkywiki-mcp/)**

---

## Sample Conversation

<p align="center">
  <img src="https://raw.githubusercontent.com/Cloudmeru/TinkyWiki-MCP/main/docs/sample_chat.gif" alt="Sample conversation using TinkyWiki MCP and TinkyWiki Agent" width="800">
</p>

<p align="center">
  <em>Sample conversation using TinkyWiki MCP server with the TinkyWiki Agent in VS Code Chat.</em>
</p>

---

## Quick Start

```bash
pip install tinkywiki-mcp
playwright install chromium
```

## Client Setup

### VS Code

Open **Command Palette** (`Ctrl+Shift+P`) → **MCP: Add Server** → **Command (stdio)** → enter `tinkywiki-mcp`.

Or add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "tinkywiki-mcp": {
      "type": "stdio",
      "command": "tinkywiki-mcp"
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tinkywiki": {
      "command": "tinkywiki-mcp"
    }
  }
}
```

### Docker

```bash
docker build -t tinkywiki-mcp .
docker run -it --rm tinkywiki-mcp
```

## Tools

| Tool | Description |
|------|-------------|
| `tinkywiki_list_topics` | Topics overview with previews |
| `tinkywiki_read_structure` | JSON table of contents |
| `tinkywiki_read_contents` | Full or section-specific docs (paginated) |
| `tinkywiki_search_wiki` | Gemini-powered Q&A chat |
| `tinkywiki_request_indexing` | Submit unindexed repos for indexing |

All tools accept `repo_url` as a full URL or `owner/repo` shorthand.

## Documentation

Configuration, architecture, agentic AI guides, and more — see the **[full documentation](https://cloudmeru.github.io/TinkyWiki-MCP)**.

## License

MIT
