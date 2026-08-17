# RFC-0025: Instant Causal Proprioception for Agent Change Intelligence

- **Status**: draft
- **Author(s)**: @lead-agent
- **Created**: 2026-08-17
- **Last updated**: 2026-08-17
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/ast_cache.py` (watch-based incremental causality index)
  - `tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py` (edit-time causal envelope)
  - `tree_sitter_analyzer/mcp/tools/change_impact_tool.py` (push-based touch delivery)
  - `tree_sitter_analyzer/index_snapshot.py` (standing certification state)
  - `tree_sitter_analyzer/mcp/server.py` (event subscription surface)
  - `tests/unit/...` (per-phase benchmarks)

## Summary

The analyzer is currently **pull-based**: an AI agent must *query* to learn
what a change touches (`change_impact`), whether a file is safe to edit
(`edit.safe`), what tests exist, or what broke. Every query is a round-trip
with latency, and the agent only learns what it remembered to ask. The human
body does the opposite: **proprioception** tells it instantly what it touched
and what touched it, with zero conscious queries.

This RFC proposes a **causality proprioception layer**: a continuously
maintained, watch-driven, incremental causality index that lets every edit
carry its full causal envelope (dependents, dependencies, exercising tests,
risk, verification) in the same response, and lets agents *subscribe* to
touch/was-touched events instead of polling. The north star (VCSR, per
`ROADMAP-no1-agent-trust.md`) stays unchanged; this RFC is the sensing layer
that makes the three task outcomes (`understand` / `plan_change` /
`assess_change`) *instant* instead of query-latency-bound.

## Motivation

A self-observation from dogfooding: an autonomous coding agent (including the
author of this RFC) spends a large fraction of its turns *querying the
analyzer* — `--change-impact`, `--callers`, `--callees`, `--class-hierarchy`,
`edit.safe`, health — and then *reasoning* over the answers before each edit.
The nervous system never does this: a hand touching a hot surface withdraws
via a spinal reflex in ~15 ms, and the brain *knows what was touched* as an
immediate given, not as the result of a query. Two properties are missing from
the analyzer that make agents query-heavy:

1. **Push vs pull**: the analyzer holds the causality facts but only reveals
   them on request. There is no event channel.
2. **No standing state**: every call re-derives or re-acquires certification
   (RFC-0022 P0.4 read_existing is a *per-call* certification). The agent
   cannot *rely* on a known-good state between calls.

Measured consequence: each `change_impact` + `edit.safe` + test-discovery
sequence costs 3+ round-trips and 2–5× the tokens of a single envelope
(`nav.context`/`edit.safe` certified reads already cut this in #1299, but
safety and impact remain separate calls). The VCSR north star is bounded by
how often an agent *forgets* to ask — a query-gap problem, not a
correctness-of-answer problem.

## Detailed design

### Layer 1 — Watch-driven incremental causality index (receptors)

A background, bounded **file watcher** (the repo already depends on
`watchdog`) maintains a persistent causality index:

- `symbols` (file, name, line, kind, id)
- `edges` (caller → callee, imports, implements, with `callee_resolved_file`)
- `dependents` (reverse edges, precomputed at write time)
- `tests_by_symbol` (which indexed test file exercises which symbol, derived
  from the import graph, not filename patterns)
- `constraint_rows` bound to an evaluation epoch (RFC-0022 C21)

Updates are **incremental and idempotent**: a changed file re-parses only
itself and re-writes only its out-edges; dependents of the removed symbols are
recomputed by diff. The index is crash-safe (WAL, generation-stamped rows).
Budget: the watcher yields CPU to agent work (pause on active analysis),
bounded to `WATCH_INDEX_BUDGET_MB` (default 512 MiB) and `WATCH_INDEX_ROWS`
(default 2M rows), evicting least-recently-touched files — mirroring the
RFC-0022 P0.1 registry's boundedness.

**Completion criterion (measurable)**: on a 100k-symbol repository, a single
file edit reflects in the causality index in **< 50 ms median** after save
(measured by a new `tests/benchmarks/test_causality_latency.py`), with zero
agent-visible re-index waits.

### Layer 2 — Edit-time causal envelope (reflexes)

`edit.safe` (and the read_existing certified path from #1299) grows a
**causal envelope** field returned with the edit verdict itself:

```python
{
  "verdict": "safe" | "caution" | "dangerous" | "unknown",
  "causal_envelope": {
    "dependents": ["routes.py", "tests/test_app.py"],   # who I touch back
    "dependencies": ["pkg/util.py"],                     # what touches me
    "exercising_tests": ["tests/test_app.py"],           # tests that cover me
    "constraint_verdict": "safe" | "caution" | "unsafe" | "unknown",
    "verification_command": "uv run pytest -q",          # snapshot-bound or None
    "stale_edges": [],                                   # index rows invalidated by this edit
  }
}
```

This is the **reflex**: the agent does not need to ask "who depends on this?"
— the answer arrives with the edit result. RFC-0022's input-only contract
applies (no raw task echo; the envelope is derived data, safe to return).

**Completion criterion (measurable)**: an agent performing a 10-edit refactor
performs **0 separate causality queries** (dependents/impact/tests) — verified
by a dogfood script recording analyzer calls per task.

### Layer 3 — Push-based touch/was-touched (nerve signals)

A lightweight **event subscription** surface:

```
MCP: session.subscribe_change_events({paths: ["src/*.py"], filters: ["dependents", "constraints"]})
→ stream: {kind: "dependent_changed", file: "src/app.py", now_depends_on: ["pkg/util.py"]}
```

Agents register interest once; the analyzer pushes on change (event latency
bounded by Layer 1). No polling. This is the *"what touched me"* channel the
user's proprioception analogy names directly: the agent knows instantly, in
its own context, that a file it depends on changed — without asking.

**Completion criterion (measurable)**: after a watched-file save, the
subscribed agent receives the `dependent_changed` event in **< 100 ms median**
(measured by `test_causality_events.py`); event delivery is exactly-once per
index generation.

### Layer 4 — Standing certification (verified state, not per-call belief)

RFC-0022 P0.4 currently certifies *per call*. The proprioception ideal is a
**standing certification state**: the analyzer continuously re-validates the
watch index against the source oracle and exposes a single
`authority.status` signal:

```
{state: "certified" | "stale" | "unknown",
 generation: "idxsrc-v3:...", since: 12.4s, drift: ["src/app.py"]}
```

`edit.safe` / `nav.context` read_existing routes then **consume the standing
state** instead of re-capturing per call; a `stale` state fails closed exactly
like today's `SOURCE_GENERATION_MISMATCH`. Per-call recapture remains as the
fallback and as the audit trail.

**Completion criterion (measurable)**: `authority.status` median staleness
window < 200 ms after a source change; 100% of certified route failures are
classified stable codes (the #1299 seam's contract, extended to the standing
state).

### Layer 5 — Self-proprioception (the analyzer sensing itself)

The analyzer observes its own health like the body senses itself: cache hit
rates, index staleness, per-tool latency percentiles, unresolved-relationship
rate — surfaced as `--self-health` and fed into the dogfood loop. This is the
precondition for *believing* the north star's claims: if the tool cannot tell
you how well it is sensing, it cannot claim VCSR honestly (RFC-0021 evidence
levels).

**Completion criterion (measurable)**: `--self-health` reports per-tool
p50/p95 latency and index-hit-rate with exact pins in CI (no `>=` bounds —
CLAUDE.md exact-assertion rule).

## Phased roadmap with visible completion

Each phase ends with a **visible, verifiable artifact** so progress toward NO1
is legible (this addresses the "I can't tell when NO1 finishes" concern):

| Phase | Scope | Verifiable exit artifact |
|---|---|---|
| **P0** (done in #1299) | Certified read_existing for `nav.context` / `edit.safe`; fail-closed seam; patch-gate green | PR #1299 merged; CI green; strace certification (RFC-0022 P0.4) |
| **P1** | Merge #1299; `edit.safe` causal envelope (Layer 2, non-watch: envelope from the certified snapshot) | `edit.safe` returns `causal_envelope`; 0-extra-query refactor dogfood script green |
| **P2** | Watch-driven incremental causality index (Layer 1) + event subscription (Layer 3) | 50 ms index latency + 100 ms event latency benchmarks green on a 100k-symbol corpus |
| **P3** | Standing certification (Layer 4) + constraint epoch binding (RFC-0022 C21 follow-up) | `authority.status` window < 200 ms; constraint rows epoch-bound |
| **P4 = NO1 proprioception complete** | Self-health (Layer 5); VCSR benchmark (NO1-010B) with the causality layer as substrate | VCSR baseline published on the pre-registered benchmark; `--self-health` pinned in CI; median edit→causal-envelope < 1 round-trip |

The **NO1 completion definition** (answering "when is it done"): *VCSR on the
NO1-010B pre-registered task corpus ≥ the admitted bounded claim level (E4),
measured continuously in CI, with the edit→causal-envelope path requiring zero
separate causality queries.* Until those numbers exist and are pinned, NO1 is
not claimed — exactly per `ROADMAP-no1-agent-trust.md` claim policy.

## Interaction with locked decisions

- **MCP `output_format` default stays `toon`** (user-locked): the causal
  envelope is a regular envelope field; TOON carries the same scalars.
- **RFC-0022 menu-gate**: the event-subscription facade is a *new facade* and
  must pass the pre-registration menu experiment gate before registration
  (locked); P1–P2 do not add facades.
- **`task/` import boundary**: the proprioception layer lives in the analyzer
  (primitives); the task layer consumes envelopes/events via the same boundary
  as today's task outcomes.
- **Fail-closed honesty**: `unknown` remains a first-class answer; the standing
  state degrades to per-call certification, never to unsupported claims.

## Alternatives considered

1. **Keep per-call queries** (status quo): simplest, but the query-gap is the
   dominant VCSR leak — agents forget to ask. Rejected for the north star.
2. **Full re-index on every change** (no watcher): correct but latency-unbounded;
   violates the 50 ms criterion. Rejected.
3. **In-memory-only causality** (no persistence): fast but dies with the
   process; agents run per-process. The SQLite index (RFC-0020) is the
   persistence substrate. Chosen.
4. **Polling subscriptions** (agents poll a `has_changed` endpoint): cheaper to
   build, but reintroduces the query-gap; push is the point. Rejected.

## Open questions

1. Watch budget policy when the agent process is memory-constrained
   (evict LRU files vs degrade to per-call capture) — propose evict-then-degrade.
2. Event delivery durability: at-least-once with generation dedup (chosen) vs
   exactly-once (needs ack protocol). Propose at-least-once + dedup first.
3. Whether the standing state reuses the P0.1 registry (16-snapshot bound)
   or needs its own bound — propose its own, same budget style.
