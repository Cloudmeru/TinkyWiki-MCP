---
name: tinkywiki-usage
description: Best practices for using Google TinkyWiki MCP tools to explore open-source repositories. Covers tool selection strategy, token efficiency, pagination, error handling, and multi-repo workflows.
---

# TinkyWiki MCP — Usage Best Practices

## Tool Selection Strategy (ordered by cost)

| Tool | Tokens | Use When |
|------|--------|----------|
| `tinkywiki_read_structure` | ~Low | First call — get the table of contents as JSON |
| `tinkywiki_list_topics` | ~Medium | Need section titles + short previews to pick the right one |
| `tinkywiki_read_contents` | ~High | Read full section content (supports pagination) |
| `tinkywiki_search_wiki` | ~High | Ask Gemini a specific question about the repo |
| `tinkywiki_request_indexing` | ~Minimal | Submit an unindexed repo for Google to process |

## Recommended Workflow

1. **Start cheap**: Call `tinkywiki_read_structure(repo_url)` to see what sections exist.
2. **Pick sections**: Based on the question, identify 1–3 relevant section titles.
3. **Read targeted**: Call `tinkywiki_read_contents(repo_url, section_title=<title>)` for each.
4. **Search if needed**: Only use `tinkywiki_search_wiki` for specific questions not covered by sections.
5. **Paginate large sections**: Use `offset` and `limit` parameters in `tinkywiki_read_contents` to avoid pulling everything at once.

## Anti-Patterns to Avoid

- **Don't call `tinkywiki_list_topics` AND `tinkywiki_read_contents` without a section_title** — they overlap significantly.
- **Don't call `tinkywiki_search_wiki` first** — it's the most expensive tool. Use structure/contents first.
- **Don't read all sections** — pick only what's relevant to the question.
- **Don't guess section titles** — always get the real titles from `tinkywiki_read_structure` first.

## Handling NOT_INDEXED Errors

When any tool returns a `NOT_INDEXED` error:
1. Tell the user the repo is not yet indexed by Google TinkyWiki.
2. Call `tinkywiki_request_indexing(repo_url)` to submit the request.
3. Explain that indexing depends on demand and popularity — suggest trying again later.
4. **Never fabricate documentation** for an unindexed repo.

## Multi-Repo Comparisons

When comparing two or more repositories:
1. Gather documentation for **each repo independently** — don't assume they have the same sections.
2. Use the same question/angle for each repo to ensure a fair comparison.
3. Structure the comparison as a table or side-by-side sections.

## Citation Rules

- Always cite which TinkyWiki section your information comes from.
- Use format: `[Section Title] from owner/repo`.
- If information comes from `tinkywiki_search_wiki`, note it was an AI-generated answer from TinkyWiki.
