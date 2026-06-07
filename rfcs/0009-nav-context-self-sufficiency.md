# RFC-0009: `nav context` self-sufficiency — answer in one call, close the turn gap

- **Status**: accepted — A/B/C implemented (#330/#331/#333, on develop); measured turn-drop pending (gated on the benchmark integrity fix + N≥5 re-run)
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-07
- **Last updated**: 2026-06-07
- **Tracking issue**: TBD
- **Supersedes (in part)**: RFC-0006 (context progressive disclosure) — amends its
  blanket per-block source cap; see Motivation.
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/mcp/tools/codegraph_context_tool.py` (`_build_code_blocks`, `_MAX_BLOCK_LINES`, ranking)
  - `tree_sitter_analyzer/mcp/tools/_codegraph_explore_helpers.py` (snippet extraction)
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
   (`resolve_java_callee` is 127 lines — 232-358; the block showed 16 + a
   `# … N more lines` pointer). The dispatch logic that answers the question is
   behind a "read more" pointer, forcing a follow-up. This cap is RFC-0006's
   per-call token optimisation — but the cost analysis shows it is
   **net-negative**: it trades a smaller first response for one or more extra
   turns, and turns cost more than the saved lines.

2. **Root cause B — blocks are ranked by graph centrality, not relevance.**
   `_build_code_blocks` ranks nodes by `-edge_degree` (most-connected first), so
   a high-degree hub like `_route_cache.get` (a SQL cache, irrelevant to callee
   dispatch) wins a code-block slot over the actual `resolve_callee` dispatcher
   in `synapse_resolver/__init__.py` — which got **no block at all**. 2 of 5
   blocks were noise; the answer symbol was absent.

3. **Root cause C — query tokenisation over-matches.** "dispatch" matched
   unrelated event dispatchers (`file_watcher`, `health_homeostasis`,
   `health_notifier`), spending entry-point slots on wrong symbols.

Net: after the prescribed 2-call chain the agent still lacked the dispatch body
and the dispatcher function, forcing follow-up reads — the turn explosion.

> **Withdrawn root cause (was "B: mis-indexed start-lines").** An earlier draft
> claimed `resolve_java_callee` was indexed at line 222 (the previous function).
> Codex review (#330) correctly identified this as a **stale-index artifact**:
> the `.ast-cache` lagged the working tree (`_java.py` had un-synced edits).
> After `index sync`, `search`/`nav` correctly report `line: 232`. There is no
> start-line indexing bug. Operational lesson — dogfood on a freshly-synced
> index — but nothing for this RFC to fix.

## Detailed design

### A — inline full bodies for relevant symbols, capped only for the long tail
Replace the blanket 16-line cap with a **two-tier budget**:
- An **entry-point / task-relevant** symbol gets its FULL body inlined up to a
  generous per-symbol budget (`_MAX_ENTRY_BODY_LINES`). The budget MUST cover the
  motivating target: `resolve_java_callee` is 127 lines (232-358), so the budget
  is set at **160** (covers the target with headroom; tuned against the
  measurement in Acceptance). At 120 the flagship case would still truncate
  (Codex #330) — defeating the RFC's own example.
- A symbol over the budget gets head + tail with the existing truncation marker.
- **Tangential** nodes (not task-relevant, pulled in only by graph expansion)
  keep a small cap (or are dropped — see B), preserving RFC-0006's thrift where
  it doesn't cost a turn.

Net token framing (to be MEASURED, not assumed): a larger first response that
removes ≥1 follow-up turn is cheaper end-to-end (output tokens + per-turn
replayed context dominate; see the cost memory). The acceptance criteria below
require demonstrating the turn drop, not just the bigger payload.

### B — rank code blocks by task-relevance first
Rank `_build_code_blocks` by: (1) is the node a named entry point / candidate
match for the task, then (2) edge-degree, then (3) line. Guarantee every named
entry point that has source gets a block before any purely-high-degree hub.
Drop nodes that are neither task-relevant nor on a path between relevant nodes.

### C — tighten query tokenisation
Down-weight or stop-word generic verbs ("dispatch", "handle", "run", "get")
when they also match unrelated symbols, OR require a candidate to co-occur with
a higher-signal token from the task. Keep it conservative — precision over
recall on entry-point selection.

### MCP surface (facade + action)
`nav action=context`. No new action; the response shape is unchanged (same keys:
`entry_points`, `code_blocks`, `related_symbols`, …). Only the CONTENT of
`code_blocks` (fuller, better-ranked) changes. Backward compatible.

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

## Prior art
- RFC-0006 (this repo) — the progressive-disclosure cap this RFC re-tunes.
- CodeGraph `codegraph_context` / `codegraph_explore` — the parity target whose
  6-turn answer this aims to match or beat.

## Test plan (RED-first)
- **A**: `nav context` on a task whose answer is a sub-budget function (e.g.
  `resolve_java_callee`, 127 lines) returns the FULL body inline (no
  `# … N more lines` for a sub-budget symbol). (RED today — capped at 16.)
- **B**: `nav context` for "resolve_callee → java" includes a block for the
  actual `resolve_callee` dispatcher and excludes `_route_cache.get` noise.
  (RED today — dispatcher absent, noise present.)
- **C**: a task containing "dispatch" does not surface unrelated event
  dispatchers as entry points. (RED today.)
- **Parity**: CLI and MCP return identical blocks for the same task.
- All tests run against a **freshly-synced index** (the withdrawn root cause was
  a stale-index artifact — assert freshness in the fixture).

## Acceptance criteria
- [x] Sub-budget entry-point bodies inline in full (A); long tail truncates; the
      127-line motivating target inlines fully at the chosen budget — #331
- [x] Named entry points always get blocks before high-degree noise (B) — #331
- [x] Query tokenisation no longer surfaces generic-verb false entry points (C) — #333
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
1. `_MAX_ENTRY_BODY_LINES` — set at 160 to cover the 127-line target; tune
   against the measurement (does a higher budget net out cheaper or worse?).
2. Should tangential blocks be capped-small or dropped entirely? Measure both.
