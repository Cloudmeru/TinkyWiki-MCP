# TinkyWiki Agent — Test Prompts

> **Purpose**: Sample prompts to test the master orchestrator agent
> (`tinkywiki.agent.md`) and verify it correctly delegates to each
> specialist subagent.
>
> **Usage**: Prefix each prompt with `@tinkywiki` in VS Code chat.
>
> **Important**: These prompts must be tested in the **VS Code Chat panel**
> (Ctrl+Shift+I), not in a regular Copilot inline chat or conversation.
> The `.agent.md` custom agents only activate when invoked via `@tinkywiki`
> in the Chat panel. The `runSubagent` tool in regular Copilot chat does
> NOT wire up MCP tools to subagents.
>
> **Prerequisites**:
> 1. The `tinkywiki-mcp` MCP server must be running and configured in
>    `.vscode/mcp.json` (included in this repo).
> 2. All 6 `.agent.md` files must be in `.github/agents/`.

---

## Agent Configuration Reference

Current YAML frontmatter for each agent (must match `.github/agents/` files):

### Master Orchestrator (`tinkywiki.agent.md`)

```yaml
name: TinkyWiki
description: Master agent that routes your request to the right TinkyWiki specialist
model: GPT-5.3-Codex
tools:
  [read, agent, tinkywiki-mcp/*]
agents:
  [TinkyWiki Researcher, TinkyWiki Code Review, TinkyWiki Architecture Explorer, TinkyWiki Comparison, TinkyWiki Synthesizer]
```

> **⚠️ Model:** The master must use a **1× credit model** like `GPT-5.3-Codex`.
> Free/low-tier models (GPT-5 mini) produce inconsistent routing, truncated
> results, and skipped delegation.
>
> **Why `tinkywiki-mcp/*` on the master?** The master must declare MCP tools
> so they are exposed to subagents when spawned. The master itself still acts
> as a router — it delegates via `agent` and does not call TinkyWiki tools directly.

### Subagents (4 use GPT-5 mini, 1 uses GPT-5.3-Codex)

```yaml
# Researcher, Code Review, Architecture Explorer, Comparison:
model: GPT-5 mini
user-invokable: false
tools:
  [read, tinkywiki-mcp/*]

# Synthesizer (needs stronger reasoning for multi-repo integration):
model: GPT-5.3-Codex
user-invokable: false
tools:
  [read, tinkywiki-mcp/*]
```

| Agent File | Name | Specialty |
|-----------|------|-----------|
| `tinkywiki-researcher.agent.md` | TinkyWiki Researcher | General exploration |
| `tinkywiki-reviewer.agent.md` | TinkyWiki Code Review | Module/function analysis |
| `tinkywiki-architect.agent.md` | TinkyWiki Architecture Explorer | System design |
| `tinkywiki-comparison.agent.md` | TinkyWiki Comparison | Multi-repo comparison |
| `tinkywiki-synthesizer.agent.md` | TinkyWiki Synthesizer | Combine parts from multiple repos |

---

## 1. TinkyWiki Researcher (General Exploration)

**Routing trigger**: General "what is", "explain", "tell me about" questions.

### Prompts

```
@tinkywiki What is facebook/prophet and what are its main features?
```

```
@tinkywiki Explain the key concepts behind pallets/flask
```

```
@tinkywiki What topics does TinkyWiki have for microsoft/vscode?
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **TinkyWiki Researcher** via the `agent` tool |
| 2 | Researcher calls `tinkywiki_list_topics` to discover available wiki sections |
| 3 | Researcher calls `tinkywiki_read_structure` and/or `tinkywiki_read_contents` |
| 4 | Researcher synthesises a summary from TinkyWiki content |

### Validation

- [ ] Master does **not** answer from its own knowledge
- [ ] Master uses the `agent` tool (not direct tool calls)
- [ ] Researcher cites TinkyWiki sections in its answer
- [ ] Response contains real documentation content, not generic descriptions
- [ ] Master presents the **full** subagent response (not a brief summary)

---

## 2. TinkyWiki Code Review (Module / Function Analysis)

**Routing trigger**: "review", "analyse", "what does module X do", code-level questions.

### Prompts

```
@tinkywiki Review the forecaster module in facebook/prophet — what does it do?
```

```
@tinkywiki What code patterns are used in the routing module of pallets/flask?
```

```
@tinkywiki Analyse the error handling approach in fastapi/fastapi
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **TinkyWiki Code Review** via the `agent` tool |
| 2 | Reviewer calls `tinkywiki_search_wiki` to find relevant code documentation |
| 3 | Reviewer calls `tinkywiki_read_contents` for detailed section content |
| 4 | Reviewer provides code-level analysis with citations |

### Validation

- [ ] Master delegates to **TinkyWiki Code Review**, not Researcher
- [ ] Reviewer focuses on code structure, patterns, and implementation details
- [ ] Response references specific modules, classes, or functions
- [ ] No hallucinated code — all content sourced from TinkyWiki
- [ ] Master presents the **full** subagent response (not a brief summary)

---

## 3. TinkyWiki Architecture Explorer (System Design)

**Routing trigger**: "architecture", "design", "how is X structured", "component hierarchy".

### Prompts

```
@tinkywiki Explain the overall architecture of facebook/react
```

```
@tinkywiki How is the plugin system architected in vitejs/vite?
```

```
@tinkywiki Describe the component hierarchy and data flow in vuejs/core
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **TinkyWiki Architecture Explorer** via the `agent` tool |
| 2 | Explorer calls `tinkywiki_read_structure` to map the documentation tree |
| 3 | Explorer calls `tinkywiki_read_contents` for architecture-related sections |
| 4 | Explorer produces a structured architecture overview |

### Validation

- [ ] Master delegates to **TinkyWiki Architecture Explorer**
- [ ] Response covers high-level design (layers, components, data flow)
- [ ] Includes or references diagrams / structural breakdowns from TinkyWiki
- [ ] Does not devolve into code-level details (that's the Reviewer's job)
- [ ] Master presents the **full** subagent response (not a brief summary)

---

## 4. TinkyWiki Comparison (Multi-Repo)

**Routing trigger**: "compare", "vs", "difference between", "X or Y".

### Prompts

```
@tinkywiki Compare fastapi/fastapi vs pallets/flask — architecture, performance, and developer experience
```

```
@tinkywiki Compare facebook/react vs vuejs/core in terms of rendering strategy
```

```
@tinkywiki What are the differences between expressjs/express and koajs/koa?
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **TinkyWiki Comparison** via the `agent` tool |
| 2 | Comparison agent calls TinkyWiki tools for **each** repo independently |
| 3 | Agent builds a side-by-side analysis from real documentation |
| 4 | Agent produces a structured comparison table or narrative |

### Validation

- [ ] Master delegates to **TinkyWiki Comparison**, not Researcher
- [ ] Agent fetches documentation from **both** repos (not just one)
- [ ] Comparison is grounded in TinkyWiki content, not generic knowledge
- [ ] Response includes a structured comparison (table, bullet list, or sections)
- [ ] Master presents the **full** subagent response (not a brief summary)

---

## 5. Request Indexing (Unindexed Repo — Subagent Handles It)

**Routing trigger**: Repo that returns `NOT_INDEXED` from any TinkyWiki tool.

### Prompts

```
@tinkywiki Check if Snowflake-Labs/agent-world-model is available on TinkyWiki
```

```
@tinkywiki What does TinkyWiki have for some-org/obscure-repo?
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master classifies this as a general exploration request |
| 2 | Master spawns **TinkyWiki Researcher** via the `agent` tool |
| 3 | Researcher calls a TinkyWiki tool and gets `NOT_INDEXED` error |
| 4 | Researcher calls `tinkywiki_request_indexing` to submit the repo |
| 5 | Researcher reports back; Master presents the full result to user |

### Validation

- [ ] Master does **not** call any MCP tools directly (it has none)
- [ ] A subagent detects `NOT_INDEXED` and calls `tinkywiki_request_indexing`
- [ ] User is informed the repo has been submitted for indexing
- [ ] Master presents the **full** subagent response (not a brief summary)

---

## 6. TinkyWiki Synthesizer (Multi-Repo Solution Building)

**Routing trigger**: User wants to BUILD something new by combining parts from multiple repos. Distinct from Comparison which evaluates/contrasts.

### Prompts

```
@tinkywiki I want to build an API server that uses the routing system from pallets/flask and the async handling from fastapi/fastapi. Help me design it.
```

```
@tinkywiki Take the plugin architecture from vitejs/vite and the component model from vuejs/core — design a new framework that combines both.
```

```
@tinkywiki Combine the authentication approach from supabase/supabase with the event pipeline from apache/kafka into a real-time auth notification system.
```

```
@tinkywiki Can you combine the best parts from fastapi/fastapi and pallets/flask into a new web framework solution?
```

> **Note:** The last prompt is intentionally vague — the user does NOT specify
> which parts to take. The Synthesizer should activate its DISCOVER phase:
> explore both repos, identify standout features, select complementary parts,
> and explain why it chose them.

### Expected Behaviour

| Step | What should happen |
|------|-----------------------|
| 1 | Master detects synthesis intent ("build", "combine", "take X from A and Y from B") |
| 2 | Master spawns **TinkyWiki Synthesizer** via the `agent` tool |
| 3 | Synthesizer researches each repo using TinkyWiki tools (read_structure, read_contents, search_wiki) |
| 4 | Synthesizer extracts the specific parts the user requested from each repo |
| 5 | Synthesizer identifies cross-repo conflicts and proposes adapters |
| 6 | Synthesizer delivers a blueprint: architecture diagram, directory structure, integration code, implementation guide |
| 7 | For vague requests: Synthesizer shows a "Parts Selected" table explaining WHY it chose each part |

### Validation

- [ ] Master delegates to **TinkyWiki Synthesizer**, not Comparison
- [ ] Synthesizer fetches documentation from **all** mentioned repos
- [ ] Response includes a **Parts Extracted** table citing source repos
- [ ] Response includes **Compatibility Analysis** (conflicts + resolutions)
- [ ] Response includes **Integration Architecture** (Mermaid diagram or description)
- [ ] Response includes **Directory Structure** for the new project
- [ ] Response includes **Implementation Guide** with actionable steps
- [ ] For vague requests: includes **Parts Selected** table with reasoning
- [ ] All content is grounded in TinkyWiki data, not generic knowledge
- [ ] Master presents the **full** subagent response (not a brief summary)

---

## 6. Keyword Resolution & Disambiguation (Bare Product Names)

**Routing trigger**: Any prompt using a bare keyword instead of owner/repo format.

### Prompts

```
@tinkywiki What is vue?
```

```
@tinkywiki Explain the architecture of react
```

```
@tinkywiki Compare vue vs react
```

```
@tinkywiki What topics does openclaw have?
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master delegates to the appropriate subagent (Researcher, Comparison, etc.) |
| 2 | Subagent calls a TinkyWiki tool with the bare keyword (e.g., `repo_url="vue"`) |
| 3 | Tool detects bare keyword and triggers **MCP Elicitation** (if multiple ambiguous repos found) |
| 4 | VS Code shows a selection prompt: "Multiple repositories match 'vue'. Which do you want?" |
| 5 | User selects the desired repo (e.g., `vuejs/core` for Vue 3) |
| 6 | Response includes resolution note: `> **Resolved:** keyword "vue" → **vuejs/core** (52,900★)` |
| 7 | Response shows top alternative candidates |
| 8 | The rest of the response contains normal TinkyWiki documentation |

**Auto-select (no elicitation)**:
- Canonical match: "openclaw" → `openclaw/openclaw` (owner == repo == keyword)
- Single result: only one repo found → auto-selected

**Fallback**: If elicitation is unavailable (client doesn't support it), heuristic
selection by star count is used (same as v1.1.0 behaviour).

### Validation

- [ ] Bare keyword "vue" triggers elicitation with multiple options (vuejs/vue, vuejs/core, etc.)
- [ ] User can select `vuejs/core` (Vue 3) instead of auto-picking `vuejs/vue` (Vue 2)
- [ ] Bare keyword "openclaw" auto-resolves to `openclaw/openclaw` (canonical match, NO elicitation)
- [ ] Bare keyword "react" triggers elicitation showing facebook/react and alternatives
- [ ] Resolution note appears at the top of the response with star count
- [ ] Alternative candidates are listed
- [ ] Declining/cancelling elicitation falls back to heuristic selection
- [ ] owner/repo format still works as before (no resolution note, no elicitation)
- [ ] Full URLs still work as before (no resolution note, no elicitation)

---

## Quick Reference: Routing Rules

| User intent | Subagent | Key signal words |
|-------------|----------|-----------------|
| General exploration | TinkyWiki Researcher | "what is", "explain", "tell me about", "overview" |
| Code analysis | TinkyWiki Code Review | "review", "analyse", "module", "function", "code" |
| System design | TinkyWiki Architecture Explorer | "architecture", "design", "structure", "hierarchy" |
| Multi-repo comparison | TinkyWiki Comparison | "compare", "vs", "difference", "or" |
| Multi-repo synthesis | TinkyWiki Synthesizer | "combine", "merge", "build using", "take X from A and Y from B" |
| Unindexed repo | TinkyWiki Researcher | Subagent detects NOT_INDEXED and calls `tinkywiki_request_indexing` |

---

## Alternative Repos for Testing

If a repo is too large or slow, try these:

```
# Small SDK — fast wiki generation
anthropics/anthropic-sdk-python

# Medium framework
fastapi/fastapi

# Microsoft tooling
microsoft/vscode-copilot-chat
```
