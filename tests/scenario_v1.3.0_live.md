# TinkyWiki MCP v1.3.0 — Live Scenario Tests

> **Purpose**: End-to-end prompt-based test scenarios for features introduced
> in **v1.2.0** and **v1.3.0** — bare keyword resolution, MCP Elicitation
> disambiguation, GitHub API fallback (typos), indexing confirmation
> elicitation, and resolution notes.
>
> **Usage**: Run each scenario in the **VS Code Chat panel** (Ctrl+Shift+I).
> Prefix prompts with `@tinkywiki` so the master orchestrator agent handles
> routing.  Scenarios can also be tested directly against MCP tools in a
> debug session (see "Direct Tool Testing" section at the bottom).
>
> **Prerequisites**:
> 1. `tinkywiki-mcp` MCP server running (`C:\Users\alber\anaconda3\Scripts\tinkywiki-mcp.exe`)
> 2. `.vscode/mcp.json` points to the above exe
> 3. All 6 `.agent.md` files in `.github/agents/`
> 4. VS Code with MCP Elicitation support (v0.29+)

---

## Scenario 1: Bare Keyword — Ambiguous (Elicitation)

**Feature**: Bare keyword resolution with MCP Elicitation disambiguation.
**Trigger**: User provides a single word that maps to multiple repositories.

### Prompt

```
@tinkywiki What is vue?
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **TinkyWiki Researcher** (general exploration) |
| 2 | Researcher calls `tinkywiki_list_topics(repo_url="vue")` |
| 3 | Tool detects `"vue"` is a bare keyword (`is_bare_keyword()` → True) |
| 4 | Resolver scrapes TinkyWiki search for "vue" → multiple results |
| 5 | **MCP Elicitation fires**: VS Code shows a selection prompt listing vuejs/vue, vuejs/core, etc. |
| 6 | User selects a repo (e.g. `vuejs/core` for Vue 3) |
| 7 | Tool proceeds with the selected repo |
| 8 | Response includes **resolution note**: `> **Resolved:** keyword "vue" → **vuejs/core** (52.9k★)` |
| 9 | Response lists alternative candidates below the note |
| 10 | Normal TinkyWiki documentation follows |

### Validation

- [ ] Elicitation prompt appears with ≥3 options (vue, core, vue-element-admin, etc.)
- [ ] Each option shows owner/repo and star count
- [ ] After selection, the tool uses the **selected** repo (not the highest-star default)
- [x] Resolution note appears at the top of the response
- [x] Alternative candidates are listed
- [x] Actual TinkyWiki content follows (not hallucinated)

---

## Scenario 2: Bare Keyword — Canonical Auto-Select (No Elicitation)

**Feature**: Auto-selection when keyword == owner == repo (canonical match).
**Trigger**: Keyword where the most obvious repo has matching owner and repo name.

### Prompt

```
@tinkywiki What topics does openclaw have?
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **TinkyWiki Researcher** |
| 2 | Researcher calls `tinkywiki_list_topics(repo_url="openclaw")` |
| 3 | Resolver detects bare keyword, scrapes search |
| 4 | Finds `openclaw/openclaw` — canonical match (owner == repo == keyword) |
| 5 | **No elicitation** — auto-selects `openclaw/openclaw` |
| 6 | Response includes resolution note for the auto-selection |
| 7 | Returns topics list or NOT_INDEXED error |

### Validation

- [x] **No** elicitation prompt appears (auto-selected)
- [x] Resolution note shows: `> **Resolved:** keyword "openclaw" → **openclaw/openclaw**`
- [x] If the repo is indexed: normal topic list returned
- [ ] If NOT_INDEXED: subagent detects it and calls `tinkywiki_request_indexing`

---

## Scenario 3: Bare Keyword — Single Result Auto-Select

**Feature**: Auto-selection when only one search result exists.
**Trigger**: A keyword so specific that TinkyWiki returns exactly one repo.

### Prompt

```
@tinkywiki Explain the architecture of anthropic-sdk-python
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **TinkyWiki Architecture Explorer** |
| 2 | Explorer calls a TinkyWiki tool with `"anthropic-sdk-python"` |
| 3 | Resolver finds exactly 1 result → `anthropics/anthropic-sdk-python` |
| 4 | **No elicitation** — single result auto-selected |
| 5 | Resolution note shows the resolved repo |
| 6 | Normal architecture documentation follows |

### Validation

- [x] No elicitation prompt (single result)
- [x] Resolution note appears
- [x] Architecture-level content returned (not code-level review)
- [ ] Explorer uses `tinkywiki_read_structure` to map the documentation tree

---

## Scenario 4: GitHub API Fallback — Typo in Keyword

**Feature**: When TinkyWiki search returns 0 results, falls back to GitHub REST
API which supports fuzzy matching for typos and misspellings.

### Prompt

```
@tinkywiki What is flaask?
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **TinkyWiki Researcher** |
| 2 | Researcher calls `tinkywiki_list_topics(repo_url="flaask")` |
| 3 | Resolver scrapes TinkyWiki search for "flaask" → **0 results** |
| 4 | Resolver falls back to GitHub API: `api.github.com/search/repositories?q=flaask` |
| 5 | GitHub fuzzy matching finds `pallets/flask` and similar repos |
| 6 | If multiple results → **MCP Elicitation** fires |
| 7 | If single result → auto-selects |
| 8 | Tool proceeds with the resolved repo |
| 9 | Response includes resolution note mentioning the GitHub fallback result |

### Validation

- [ ] TinkyWiki search returns 0 results (keyword is misspelled)
- [ ] GitHub API fallback activates and finds relevant repos
- [ ] User can select the correct repo (pallets/flask)
- [x] Resolution note appears at the top
- [ ] Normal TinkyWiki content follows for the resolved repo
- [x] No error / crash from the empty TinkyWiki result

### Alternate Typo Prompts

```
@tinkywiki Tell me about fecbook/react
```

```
@tinkywiki What does veu do?
```

```
@tinkywiki Explain ract architecture
```

> **Note**: `fecbook/react` contains a `/` so it is treated as owner/repo
> (not a bare keyword). The Pydantic validator handles this differently —
> it will try to fetch `fecbook/react` as-is and likely get NOT_INDEXED.
> Only single-word inputs (no slash) trigger the keyword resolver.
> The best typo test keywords are single words: `flaask`, `veu`, `ract`.

---

## Scenario 5: Comparison with Bare Keywords

**Feature**: Bare keyword resolution works in multi-repo comparison scenarios.
**Trigger**: "compare" with bare product names instead of owner/repo.

### Prompt

```
@tinkywiki Compare vue vs react
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **TinkyWiki Comparison** ("compare", "vs") |
| 2 | Comparison agent calls TinkyWiki tools for "vue" and "react" |
| 3 | Each bare keyword triggers its own resolution pipeline |
| 4 | Elicitation fires **twice** (once per keyword, if ambiguous) |
| 5 | User picks repos for each keyword |
| 6 | Comparison proceeds with both resolved repos |
| 7 | Response includes resolution notes for each keyword |
| 8 | Structured comparison follows |

### Validation

- [ ] Master delegates to **TinkyWiki Comparison** (not Researcher)
- [ ] Both "vue" and "react" trigger keyword resolution
- [ ] Elicitation appears for each ambiguous keyword
- [ ] Resolution notes appear for both keywords
- [ ] Documentation from **both** resolved repos is used
- [ ] Structured comparison (table/bullets) is present

---

## Scenario 6: Indexing Confirmation Elicitation

**Feature**: `tinkywiki_request_indexing` asks the user to confirm before
submitting a repository for indexing via MCP Elicitation.

### Prompt

```
@tinkywiki Check if Snowflake-Labs/agent-world-model is available on TinkyWiki
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **TinkyWiki Researcher** |
| 2 | Researcher calls `tinkywiki_list_topics("Snowflake-Labs/agent-world-model")` |
| 3 | Returns `NOT_INDEXED` error |
| 4 | Researcher decides to call `tinkywiki_request_indexing` |
| 5 | **Indexing confirmation elicitation fires**: "Would you like to submit this repo for indexing?" |
| 6a | User selects "Yes, request indexing" → tool proceeds with Playwright submission |
| 6b | User selects "No, skip indexing" → tool returns skip message gracefully |
| 7 | Final response includes confirmation status and next steps |

### Validation — Accept Path

- [ ] Confirmation elicitation prompt appears with two choices
- [ ] Prompt message includes repo name and disclaimer about Google review
- [x] After "Yes" → Playwright navigates to TinkyWiki and submits the request
- [x] Response includes "Indexing request submitted successfully"
- [x] Next-step guidance is included (check back, TinkyWiki URL, timeline)

### Validation — Decline Path

Test by selecting "No, skip indexing" when prompted:

- [ ] Elicitation prompt appears
- [ ] After "No" → no Playwright interaction occurs
- [ ] Response says "Indexing request **skipped**"
- [ ] Includes link to submit manually later
- [ ] No error or crash

### Validation — Cancel Path

Test by pressing Escape or dismissing the elicitation:

- [ ] Elicitation is dismissed
- [ ] Tool falls through gracefully (submits without confirmation, backward compat)

---

## Scenario 7: Elicitation Decline → Heuristic Fallback

**Feature**: When the user declines or cancels keyword disambiguation
elicitation, the resolver falls back to heuristic selection (highest-star
repo with the best name match).

### Prompt

```
@tinkywiki Explain react
```

### Test Procedure

1. The elicitation prompt appears with multiple repos for "react"
2. **Dismiss or cancel** the elicitation (press Escape, click away)
3. Observe that the tool continues with a heuristic-selected repo

### Validation

- [ ] Elicitation appears (multiple facebook/react variants)
- [ ] After dismissal, tool does **not** error out
- [ ] Heuristic selects `facebook/react` (highest stars)
- [ ] Resolution note appears (heuristic selection, not user-chosen)
- [ ] Normal documentation follows

---

## Scenario 8: Owner/Repo — No Resolution (Backward Compat)

**Feature**: Traditional `owner/repo` input bypasses the keyword resolver
entirely. No resolution note, no elicitation.

### Prompt

```
@tinkywiki What topics does fastapi/fastapi have?
```

### Validation

- [ ] **No** elicitation prompt (not a bare keyword)
- [ ] **No** resolution note in the response
- [ ] Tool calls proceed directly with `fastapi/fastapi`
- [ ] Normal TinkyWiki topics returned
- [ ] Behaves identically to v1.1.0

---

## Scenario 9: Full URL — No Resolution (Backward Compat)

**Feature**: Full GitHub URL input bypasses the keyword resolver entirely.

### Prompt

```
@tinkywiki Read the architecture section of https://github.com/microsoft/vscode
```

### Validation

- [ ] **No** elicitation prompt (URL input)
- [ ] **No** resolution note
- [ ] Tool strips the URL to `microsoft/vscode` and proceeds normally
- [ ] Content returned from TinkyWiki
- [ ] Behaves identically to v1.1.0

---

## Scenario 10: SHA-256 Content Hash & Metadata

**Feature**: All responses include `content_hash` (SHA-256, 16-char hex
prefix) and `idempotency_key` in the response metadata.

### Prompt

```
@tinkywiki What topics does anthropics/anthropic-sdk-python have?
```

### Validation

- [ ] Response JSON (when running in debug/verbose mode) includes `content_hash`
- [ ] `content_hash` is a 16-character hex string (SHA-256 prefix)
- [ ] `idempotency_key` format: `{repo_url}:topic_name:content_hash`
- [ ] Calling the same tool again returns the **same** `content_hash` (deterministic)
- [ ] Cache hit on repeat calls (elapsed_ms < 10ms)

> **How to verify**: Run the MCP server with `--verbose` flag and inspect
> the JSON response envelope, or check the structured `ToolResponse` output
> in the VS Code MCP debug panel.

---

## Scenario 11: Synthesis with Bare Keywords

**Feature**: The Synthesizer agent handles bare keyword resolution for
multi-repo synthesis tasks.

### Prompt

```
@tinkywiki Combine the routing system from flask and the async handling from fastapi into a new API framework design.
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master detects synthesis intent ("combine", "from X and Y") |
| 2 | Master spawns **TinkyWiki Synthesizer** |
| 3 | Synthesizer calls TinkyWiki tools with `"flask"` and `"fastapi"` |
| 4 | Each keyword triggers resolution (elicitation if ambiguous) |
| 5 | Synthesizer researches both resolved repos |
| 6 | Produces integration blueprint with architecture + code |

### Validation

- [ ] Master delegates to **TinkyWiki Synthesizer** (not Comparison)
- [ ] Both "flask" and "fastapi" resolve correctly
- [ ] Resolution notes for each keyword appear
- [ ] Response includes Parts Extracted table
- [ ] Response includes Compatibility Analysis
- [ ] Response includes Integration Architecture
- [ ] All content grounded in TinkyWiki data

---

## Scenario 12: Rate Limiting Under Keyword Resolution

**Feature**: Rate limiting still works correctly when keyword resolution
adds extra API calls before the main tool fetch.

### Test Procedure

1. Set `RATE_LIMIT_MAX_CALLS = 3` in config (or use default)
2. Run the same bare keyword prompt rapidly:

```
@tinkywiki What is vue?          (1st — resolves + fetches)
@tinkywiki What is vue?          (2nd — cache hit on resolution, fetches)
@tinkywiki What is vue?          (3rd — cache hit on resolution, fetches)
@tinkywiki What is vue?          (4th — should hit rate limit)
```

### Validation

- [ ] First 3 calls succeed (keyword resolution cached after 1st)
- [ ] 4th call returns `RATE_LIMITED` error with clear message
- [ ] Rate limit message includes wait duration and max calls
- [ ] Keyword resolution cache is NOT counted against rate limit
  (only the main `fetch_wiki_page` call counts)

---

## Scenario 13: Caching Behaviour with Resolution

**Feature**: Keyword resolution results are cached for 30 minutes.
Subsequent calls with the same keyword skip the TinkyWiki/GitHub search.

### Test Procedure

```
@tinkywiki What is vue?                    (1st — full resolution + elicitation)
@tinkywiki Explain the architecture of vue  (2nd — cache HIT on resolution)
```

### Validation

- [ ] 1st call: elicitation fires, user picks a repo
- [ ] 2nd call: **no elicitation** (cache returns the same results)
- [ ] 2nd call uses the same heuristic/previous selection
- [ ] Server logs (verbose mode) show `cache HIT for keyword 'vue'`
- [ ] Resolution note still appears on 2nd call

> **Note**: The cached results are the raw search results, not the user's
> selection. However, since the same results produce the same heuristic
> selection, behaviour is consistent. If the user previously selected via
> elicitation, the 2nd call falls through to heuristic (the actual
> selection is not cached — only the search results are).

---

## Direct Tool Testing (Without Agent Routing)

For debugging individual tools without going through the master agent,
use the VS Code MCP debug panel or call tools directly:

### Tool: `tinkywiki_list_topics`

```json
{
  "tool": "tinkywiki_list_topics",
  "arguments": { "repo_url": "vue" }
}
```

Expected: Elicitation fires → user picks repo → topics returned.

### Tool: `tinkywiki_read_structure`

```json
{
  "tool": "tinkywiki_read_structure",
  "arguments": { "repo_url": "react" }
}
```

Expected: Elicitation fires → user picks repo → structure returned.

### Tool: `tinkywiki_read_contents`

```json
{
  "tool": "tinkywiki_read_contents",
  "arguments": { "repo_url": "flask", "topic": "Routing" }
}
```

Expected: "flask" resolves → content for the Routing section returned.

### Tool: `tinkywiki_search_wiki`

```json
{
  "tool": "tinkywiki_search_wiki",
  "arguments": { "repo_url": "veu", "query": "request handling" }
}
```

Expected: TinkyWiki search fails → GitHub API fallback catches typo →
resolves "veu" → "vue" → search proceeds.

### Tool: `tinkywiki_request_indexing`

```json
{
  "tool": "tinkywiki_request_indexing",
  "arguments": { "repo_url": "some-org/private-repo" }
}
```

Expected: Indexing confirmation elicitation fires → user confirms or
declines → appropriate response returned.

---

## Quick Reference: v1.3.0 Features Tested

| # | Scenario | Feature | Elicitation? |
|---|----------|---------|-------------|
| 1 | Ambiguous keyword | Bare keyword + disambiguation | Yes |
| 2 | Canonical keyword | Auto-select (owner == repo == kw) | No |
| 3 | Single-result keyword | Auto-select (1 result) | No |
| 4 | Typo keyword | GitHub API fallback | Maybe |
| 5 | Compare with keywords | Multi-repo keyword resolution | Yes (×2) |
| 6 | Indexing confirmation | Elicitation before indexing submit | Yes |
| 7 | Elicitation decline | Heuristic fallback on cancel | Yes → No |
| 8 | owner/repo input | Backward compat (no resolver) | No |
| 9 | Full URL input | Backward compat (no resolver) | No |
| 10 | SHA-256 hash | Content hash in metadata | No |
| 11 | Synthesis + keywords | Synthesizer agent with bare kw | Yes |
| 12 | Rate limiting | Rate limit with resolution overhead | No |
| 13 | Caching | Resolution cache across calls | 1st only |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Elicitation never appears | VS Code < 0.29 or client doesn't support MCP Elicitation | Update VS Code; check `ctx.elicit` availability |
| "vue" auto-selects without asking | Canonical match found (vuejs/vue → owner contains "vue") | Expected if heuristic is confident; try less obvious keywords |
| GitHub API fallback not firing | Keyword found on TinkyWiki (fallback only when 0 TinkyWiki results) | Use a truly misspelled keyword like "flaask" |
| Rate limit hits too early | Keyword resolution counts as separate calls | Resolution uses a separate cache; check `RATE_LIMIT_MAX_CALLS` config |
| Resolution note missing | Input was owner/repo or full URL (not a bare keyword) | Use single word without `/` |
| Indexing elicitation skipped | `ctx` is None or elicitation fails silently | Check verbose logs for "Elicitation failed" warnings |

---

## Test Run Summary (2026-02-17)

### Scenarios executed in this chat

| Scenario | Prompt used | Result |
|---|---|---|
| 1 | `@tinkywiki What is vue?` | **Partial pass (elicitation checks unverified)** |
| 2 | `@tinkywiki What topics does openclaw have?` (mapped from `What is openclaw? and how to use it?`) | **Pass (indexed branch)** |
| 3 | `@tinkywiki Explain the architecture of anthropic-sdk-python` | **Mostly pass (structure-call check unverified)** |
| 4 | `@tinkywiki What is flaask?` | **Partial (fallback target mismatch; some checks unverified)** |
| 6 | `@tinkywiki Check if Snowflake-Labs/agent-world-model is available on TinkyWiki` | **Accept path partial pass (elicitation prompt checks unverified)** |

> **Legend:** `[x]` = validated pass from observed evidence. Empty checkbox = **not checked / not observed in this run** (not automatically a failure).

### Why elicitation checks failed in this run

1. This run was executed through Copilot chat + `runSubagent` orchestration, not the **VS Code Chat panel `@tinkywiki` custom-agent runtime**.
2. In this mode, MCP elicitation UI (`ctx.elicit`) is typically not surfaced the same way as in direct `@tinkywiki` execution.
3. As a result, selection prompts that should appear for ambiguous keyword resolution and indexing confirmation were not observable, even when downstream tool actions completed.
4. Some scenarios therefore show a mixed outcome: content-level behavior succeeded (resolution note, indexing submit), while elicitation-specific validations stayed unverified in this run.

### Recommended re-test method for elicitation scenarios

- Re-run Scenarios 1, 4, 5, 6, and 7 in **VS Code Chat panel (Ctrl+Shift+I)** with the literal `@tinkywiki ...` prompts.
- Keep MCP server running and verify VS Code version supports elicitation.
- Capture screenshots/logs of selection prompts to conclusively validate elicitation-specific checklist items.
