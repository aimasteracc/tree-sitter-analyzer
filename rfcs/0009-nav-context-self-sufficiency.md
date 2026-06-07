# RFC-0009: `nav context` self-sufficiency — answer in one call, close the turn gap

- **Status**: draft
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-07
- **Last updated**: 2026-06-07
- **Tracking issue**: TBD
- **Supersedes (in part)**: RFC-0006 (context progressive disclosure) — amends its
  blanket per-block source cap; see Motivation.
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/mcp/tools/codegraph_context_tool.py` (`_build_code_blocks`, `_MAX_BLOCK_LINES`, ranking)
  - `tree_sitter_analyzer/mcp/tools/_codegraph_explore_helpers.py` (snippet extraction)
  - the symbol start-line indexing path (TBD — see root cause B)
  - `tests/unit/test_codegraph_context_tool.py`, `benchmarks/codegraph_compare/`

## Summary

Make `nav action=context` (the MCP server's documented PRIMARY call, codegraph
parity: `codegraph_context`) **self-sufficient**: an agent should be able to
answer a "how does X work / trace a flow" question from a SINGLE `context`
response, without follow-up reads. Today it forces 2–N follow-ups, and that
turn count — not the tool-definition prefix — is the dominant driver of TSA's
only measured competitive deficit: end-to-end cost vs CodeGraph (expert panel,
2026-06-06; see ROADMAP-beyond-codegraph and the `feedback_benchmark-cost-analysis-rigor`
memory). Correctness wins the argument; **turns win the default**. This RFC
closes the turn gap by making the first response carry the answer.

## Motivation

### Measured deficit
On the gin routing-trace benchmark TSA took **8 agent turns vs CodeGraph's 6**
for the same question. The expert panel established cost is driven by OUTPUT
tokens + TURNS, not the cached tool-definition prefix; the engineering lead is
"why does TSA need more turns?" This RFC answers it.

### Dogfood evidence (2026-06-07, on TSA's own code)
Task: *"how does resolve_callee dispatch a Java call to resolve_java_callee"*.
One `nav context` call returned a response that **does not contain the answer**:

1. **Root cause A — entry-point bodies are truncated.** `_MAX_BLOCK_LINES = 16`
   caps every code block to 16 lines even when the symbol's full range is known
   (`resolve_java_callee` is 95 lines; the block showed 16 + `# … 80 more lines`).
   The dispatch logic that answers the question is behind a "read more" pointer,
   forcing a follow-up. This cap is RFC-0006's per-call token optimisation — but
   the cost analysis shows it is **net-negative**: it trades a smaller first
   response for one or more extra turns, and turns cost more than the saved
   lines.

2. **Root cause B — symbol start-lines are mis-indexed.** `search action=symbol
   resolve_java_callee` (and `nav context`) report `line: 222`, but line 222 is
   the *previous* function `_lookup_in_file`; `resolve_java_callee` actually
   starts at line 232. Every block/snippet for an affected symbol is therefore
   sliced from the wrong window (shows the wrong function). This corrupts both
   `search` and `nav` — a "trust the graph" violation independent of the cap.

3. **Root cause C — blocks are ranked by graph centrality, not relevance.**
   `_build_code_blocks` ranks nodes by `-edge_degree` (most-connected first), so
   a high-degree hub like `_route_cache.get` (a SQL cache, irrelevant to callee
   dispatch) wins a code-block slot over the actual `resolve_callee` dispatcher
   in `synapse_resolver/__init__.py` — which got **no block at all**. 2 of 5
   blocks were noise; the answer symbol was absent.

4. **Root cause D — query tokenisation over-matches.** "dispatch" matched
   unrelated event dispatchers (`file_watcher`, `health_homeostasis`,
   `health_notifier`), spending entry-point slots on wrong symbols.

Net: after the prescribed 2-call chain the agent still lacked the dispatch body
and the dispatcher function, forcing follow-up reads — the turn explosion.

## Detailed design

### A — inline full bodies for relevant symbols, capped only for the long tail
Replace the blanket 16-line cap with a **two-tier budget**:
- An **entry-point / task-relevant** symbol gets its FULL body inlined up to a
  generous per-symbol budget (`_MAX_ENTRY_BODY_LINES`, proposed 120). Most
  functions fit; the agent answers without a follow-up.
- A symbol over the budget gets head + tail with the existing truncation marker.
- **Tangential** nodes (not task-relevant, pulled in only by graph expansion)
  keep a small cap (or are dropped — see C), preserving RFC-0006's thrift where
  it doesn't cost a turn.

Net token framing (to be MEASURED, not assumed): a larger first response that
removes ≥1 follow-up turn is cheaper end-to-end (output tokens + per-turn
replayed context dominate; see the cost memory). The acceptance criteria below
require demonstrating the turn drop, not just the bigger payload.

### B — fix symbol start-line indexing
Investigate and fix the start-line offset (resolve_java_callee indexed at the
preceding function's line). Likely in the function-symbol extraction (leading
decorator/blank-line/comment handling or a node-start vs def-line mismatch).
This is a prerequisite: a correct cap/ranking on a wrong line still shows the
wrong function. Ships with a regression test asserting the indexed `line` lands
on the `def`/signature for a function preceded by another top-level function.

### C — rank code blocks by task-relevance first
Rank `_build_code_blocks` by: (1) is the node a named entry point / candidate
match for the task, then (2) edge-degree, then (3) line. Guarantee every named
entry point that has source gets a block before any purely-high-degree hub.
Drop nodes that are neither task-relevant nor on a path between relevant nodes.

### D — tighten query tokenisation
Down-weight or stop-word generic verbs ("dispatch", "handle", "run", "get")
when they also match unrelated symbols, OR require a candidate to co-occur with
a higher-signal token from the task. Keep it conservative — precision over
recall on entry-point selection.

### MCP surface (facade + action)
`nav action=context`. No new action; the response shape is unchanged (same keys:
`entry_points`, `code_blocks`, `related_symbols`, …). Only the CONTENT of
`code_blocks` (fuller, correctly-aligned, better-ranked) changes. Backward
compatible.

## Three-Surface impact (CLI ↔ MCP parity)
`nav context` mirrors the CLI `--codegraph-context` path; both build blocks via
the same `_build_code_blocks`. The fix lands in the shared builder, so CLI and
MCP move together. A parity test asserts identical block selection/content for
the same task across both surfaces.

## Drawbacks
- Larger first responses. Mitigated by the per-symbol budget + dropping
  tangential blocks + the measurement gate (we only keep the change if it nets
  out cheaper in turns).
- Partially reverses RFC-0006. Justified: RFC-0006 optimised per-call payload in
  isolation; the end-to-end (multi-turn) measurement shows the cap costs more
  than it saves. This RFC re-tunes with the missing metric.

## Alternatives
- **Keep the 16-line cap, add a one-shot "read entry body" convenience**:
  rejected — still a second turn; doesn't fix self-sufficiency.
- **Always inline full bodies, no budget**: rejected — unbounded payload on
  large functions; the long tail genuinely should truncate.
- **Fix only B (indexing)**: necessary but insufficient — alignment without
  full bodies + relevance ranking still forces follow-ups.

## Prior art
- RFC-0006 (this repo) — the progressive-disclosure cap this RFC re-tunes.
- CodeGraph `codegraph_context` / `codegraph_explore` — the parity target whose
  6-turn answer this aims to match or beat.

## Test plan (RED-first)
- **B**: index a file with two adjacent top-level functions; assert the second's
  indexed `line`/`start_line` is its `def` line, not the first's. (RED today.)
- **A**: `nav context` on a task whose answer is a ~90-line function returns the
  FULL body inline (no `# … N more lines` for a sub-budget symbol). (RED today —
  capped at 16.)
- **C**: `nav context` for "resolve_callee → java" includes a block for the
  actual `resolve_callee` dispatcher and excludes `_route_cache.get` noise.
  (RED today — dispatcher absent, noise present.)
- **D**: a task containing "dispatch" does not surface unrelated event
  dispatchers as entry points. (RED today.)
- **Parity**: CLI and MCP return identical blocks for the same task.

## Acceptance criteria
- [ ] Symbol start-line lands on the `def`/signature (B) — regression test green
- [ ] Sub-budget entry-point bodies inline in full (A); long tail truncates
- [ ] Named entry points always get blocks before high-degree noise (C)
- [ ] Query tokenisation no longer surfaces generic-verb false entry points (D)
- [ ] **MEASURED turn drop**: re-run the gin routing-trace benchmark
      (symmetric warm cache, n≥5, separate cache_read/cache_creation/output/turns
      columns — per `feedback_benchmark-cost-analysis-rigor`); turns-to-answer
      ≤ CodeGraph's 6 on the sampled tasks, end-to-end `total_cost_usd` not worse
- [ ] CLI↔MCP parity test green
- [ ] Docs/CODEMAPS + RFC status → implemented; RFC-0006 cross-linked as amended

## What this RFC does NOT do (deferred)
- A full relevance-ranking model (semantic re-rank) — start with entry-point
  membership + degree.
- Changing the response schema or adding actions.
- The benchmark run-id infra fix (separate NOW-wave item) — but the measurement
  criterion above depends on it, so it lands first.

## Open questions
1. `_MAX_ENTRY_BODY_LINES` value — 120? Tune against the measurement.
2. Is B systemic (all functions preceded by another) or specific? Scope the fix
   from the regression test's blast radius.
3. Should tangential blocks be capped-small or dropped entirely? Measure both.
