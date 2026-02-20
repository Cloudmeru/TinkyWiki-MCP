# TinkyWiki Researcher — Full Workflow Scenario Prompt

> **Purpose**: A single prompt designed to trigger all 5 workflow steps
> (Discover → Navigate → Read → Search → Synthesize) defined in
> `.github/agents/tinkywiki-researcher.agent.md`.
>
> **Usage**: Paste this prompt into a chat session that has the
> `TinkyWiki Researcher` agent active, or prefix with `@tinkywiki-researcher`.

---

## Scenario Prompt

```
I want a deep technical explanation of the React Compiler's compilation pipeline.

Specifically:
1. First, check what topics Google TinkyWiki has for facebook/react.
2. Then look at the full table of contents to find sections about the compiler.
3. Read the section on "React Compiler Internals" to understand the
   multi-stage compilation pipeline, the IRs (HIR and ReactiveFunction),
   and the key optimization passes.
4. Search for "How does the React Compiler handle memoization and
   reactive scopes?" to get implementation-level details.
5. Combine everything into a single technical summary that covers:
   - The overall compilation pipeline (AST → HIR → ReactiveFunction → codegen)
   - The key intermediate representations and their purpose
   - How reactive scopes are inferred and merged
   - How the compiler replaces manual useMemo/useCallback
   - Cite which TinkyWiki sections your answer comes from
```

---

## Expected Tool Calls

| Step | Workflow Phase | Tool Call | Purpose |
|------|---------------|-----------|---------|
| 1 | **Discover** | `tinkywiki_list_topics("facebook/react")` | Verify wiki exists, see available topics |
| 2 | **Navigate** | `tinkywiki_read_structure("facebook/react")` | Get full ToC with section hierarchy |
| 3 | **Read** | `tinkywiki_read_contents("facebook/react", "React Compiler Internals")` | Fetch detailed compiler pipeline docs |
| 4 | **Search** | `tinkywiki_search_wiki("facebook/react", "How does the React Compiler handle memoization and reactive scopes?")` | Get Gemini-powered implementation details |
| 5 | **Synthesize** | *(no tool call — agent combines results)* | Produce cited summary from steps 1-4 |

---

## Validation Checklist

After running the scenario, verify:

- [ ] **Step 1**: Returns `status: "ok"` with topic list (expect ~26 sections)
- [ ] **Step 2**: Returns `status: "ok"` with hierarchical section structure
- [ ] **Step 3**: Returns `status: "ok"` with detailed content about HIR,
      ReactiveFunction, compilation passes (expect ~8 KB)
- [ ] **Step 4**: Returns `status: "ok"` OR `RETRY_EXHAUSTED` (upstream timeout
      is a known TinkyWiki issue, not a bug in our code)
- [ ] **Step 5**: Agent produces a coherent summary citing specific TinkyWiki sections
- [ ] **v1.0.3 features**: All responses include `content_hash` and `idempotency_key`
- [ ] **Caching**: Subsequent identical calls return in <10ms (cache hit)
- [ ] **No looping**: Agent does NOT call the same tool >2 times for the same repo

---

## Alternative Repos for Testing

If `facebook/react` is too large or slow, try these smaller repos:

```
# Small SDK — fast wiki generation
anthropics/anthropic-sdk-python

# Medium framework
fastapi/fastapi

# Microsoft tooling
microsoft/vscode-copilot-chat
```
