# Vision: TSA as Proprioception for AI Coding Agents

**Simulated scenarios + data walkthroughs for what the tool becomes — and the
exact steps to get there.**

> 核心一句话：让 AI 使用 TSA 就像触摸自己的身体——瞬间、精准、无需检索。
> The goal is that using TSA feels like proprioception: instant, precise,
> zero-query. This document simulates the workflows that make that concrete,
> with data everyone can read, and the step-by-step path to each.

- Status: vision draft (guides RFC-0025 and RFC-0026 implementation)
- Companion RFCs: RFC-0025 (instant causal proprioception), RFC-0026
  (NO1-010B VCSR benchmark), ROADMAP-no1-agent-trust.md
- Numbers marked **illustrative** are to be replaced by pinned measurements
  from RFC-0026 B2; numbers marked **criterion** are RFC-0025 completion
  criteria.

---

## 0. Why "proprioception" and why it is the moat

A human does not *search* to know what their hand just touched. The nervous
system delivers the answer in milliseconds, unasked. An AI agent today works
the opposite way: before every edit it must *ask* — `--change-impact`,
`--callers`, `--callees`, `edit.safe`, test discovery, health — and it only
learns what it remembered to ask. The gap between "instantly knows" and
"frantically retrieves" is the entire distance between a tool an agent uses
and a tool an agent **relies on**.

The scenarios below make that distance measurable. Each shows the same task
through two lenses:

- **TODAY (pull)** — the query-by-query experience, with round-trip and
  token data.
- **DREAM (proprioception)** — the same task with the RFC-0025 layers:
  an edit carries its full causal envelope; the agent is *pushed* what
  touched it; certification is standing, not per-call.

Why this is **not surpassable by copying**: the VCSR loop (RFC-0026) makes
every claim continuously falsifiable against a pre-registered corpus. A
competitor can copy a feature; they cannot copy an evidence base built by
running the same pinned oracles every CI cycle. The moat is the *measurement
itself*.

---

## 1. Scenario A — The bugfix (null-deref on unknown route)

**Task**: `dispatch()` returns `None` for an unknown route; fix it to return a
`404` object.

### TODAY (pull) — an honest transcript of how an agent actually works

| Step | Agent action | Tool cost |
|---|---|---|
| 1 | "Who calls `dispatch`?" | 1 `--callers` query |
| 2 | "What does `dispatch` call?" | 1 `--callees` query |
| 3 | "What breaks if I change it?" | 1 `--change-impact` query |
| 4 | "Is it safe to edit?" | 1 `edit.safe` query |
| 5 | "Which tests exercise it?" | 1 test-discovery query |
| 6 | "What's its health?" | 1 `--file-health` query |
| 7 | Re-check freshness after the edit | 1 `--change-impact` again |
| 8 | Run the verification the agent *guessed* | 1 test run |

**Data (illustrative baseline, RFC-0026 B2 will pin)**: 8 tool calls, ~6
round-trips of latency, ~4× the tokens of the edit itself, and — the silent
killer — **the agent may skip steps 3–6 entirely on a "quick fix"**, which is
where VCSR leaks. Any forgotten query is an unmeasured risk.

### DREAM (proprioception) — one edit, full awareness

```
edit.safe(file="src/dispatch.py", change="add 404 branch")
→ {
  verdict: "safe",
  causal_envelope: {
    dependents: ["routes.py", "tests/test_dispatch.py"],
    dependencies: ["pkg/router.py"],
    exercising_tests: ["tests/test_dispatch.py"],
    verification_command: "uv run pytest tests/test_dispatch.py -q",
    constraint_verdict: "safe"
  }
}
```

The agent knows in **one round-trip** everything steps 1–8 answered
separately. The verification command is not guessed — it is derived from the
certified snapshot (RFC-0022 C32), so it actually runs the affected test.

**Data (criterion)**: 1 tool call instead of 8; edit→causal-envelope in one
round-trip; verification is never guessed.

### Steps (which RFC delivers it)

1. **RFC-0025 P1** — `edit.safe` returns `causal_envelope` from the certified
   snapshot (dependents/dependencies/tests already available from #1299's
   snapshot reader; the work is composing them into one envelope).
2. **RFC-0026 B1** — the seed corpus records "zero separate causality
   queries" as a measured task property, making this regression-proof.

---

## 2. Scenario B — The rename refactor across a package

**Task**: rename `UserService.get_user` → `UserService.fetch_user` across
`src/` and `tests/`.

### TODAY (pull)

| Step | Tool cost |
|---|---|
| `--callers UserService.get_user` for each call site | 1 query per site (~9 sites → 9 queries) |
| `--find-references` + per-file `--change-impact` | ~5 queries |
| `edit.safe` on each touched file | ~6 queries |
| test discovery + health per file | ~6 queries |
| re-verify the full change | 1 `--change-impact` |

**Data (illustrative)**: ~27 queries, ~18 round-trips, and the agent must
*hold the whole rename in context* — every missed call site is a stale symbol
row the tool detects only after the fact (if the agent remembers to re-ask).

### DREAM (proprioception) — touch/was-touched, pushed

The agent registers interest once:

```
session.subscribe_change_events({paths: ["src/**"], filter: ["dependents"]})
```

As it renames each call site, the analyzer **pushes** `dependent_changed`
events: *"src/routes.py now depends on nothing named get_user; its import is
stale"*. The agent is told the moment a reference is missed — not on a later
re-query, but in real time. The rename converges without holding the graph in
context.

**Data (criterion)**: event latency < 100 ms after save; the agent performs
**zero** `--callers` queries for the rename; the standing index (RFC-0025
Layer 1) means no re-index wait (index update < 50 ms).

### Steps

1. **RFC-0025 P2** — watch-driven incremental causality index
   (`watchdog` is already a dependency; the work is incremental edges +
   dependents recomputation by diff).
2. **RFC-0025 P2** — `session.subscribe_change_events` MCP surface (a *new*
   facade → must pass the RFC-0022 pre-registration menu gate first, locked
   decision).

---

## 3. Scenario C — The API migration (standing certification)

**Task**: migrate `pkg.old_api` → `pkg.new_api` across the repo.

### TODAY (pull)

Freshness is **per-call**: after any edit, the agent must re-run impact or
re-read the index to know what is stale. Between calls, the agent operates on
belief, not knowledge. A CI-stale edge or a half-applied migration is found
when someone happens to re-query.

### DREAM (proprioception) — the analyzer knows its own state

```
authority.status
→ {state: "stale", generation: "idxsrc-v3:…", drift: ["src/migrated.py"]}
```

The agent reads **one** status line and knows exactly which files are out of
sync with the certified index — before touching anything. During the
migration, every `edit.safe` consumes the standing state; a stale file fails
closed exactly like today's `SOURCE_GENERATION_MISMATCH`, so a half-applied
migration can never be silently served as fresh.

**Data (criterion)**: standing-state staleness window < 200 ms after a source
change; 100% of certified-route failures are stable codes (the #1299 seam
contract, extended to standing state).

### Steps

1. **RFC-0025 P3** — standing certification state + continuous re-validation
   of the watch index against the source oracle; per-call recapture stays as
   the fallback and audit trail.
2. **RFC-0022 C21 follow-up** — constraint rows bound to an evaluation epoch
   (already tracked).

---

## 4. Scenario D — Two agents, one repo (what touched me)

**Task**: Agent A is editing `src/checkout.py`; Agent B, in parallel, edits a
function A's code calls.

### TODAY (pull)

A finishes, runs its verification, and passes — using an index that predates
B's change. A's test suite passes against *A's own copy* of the dependency,
and the integration breaks only in CI, hours later, discovered by a human.

### DREAM (proprioception) — the push channel

A receives, mid-edit:

```
{kind: "dependent_changed", file: "src/checkout.py",
 now_depends_on: ["pkg/pricing.py"], changed_by: "agent-B",
 changed_generation: "idxsrc-v3:…"}
```

A's standing certification flips to `stale` **immediately**; A re-runs the
one affected test *before* finishing, not after CI. The parallel-edit race is
a push event, not a surprise.

**Data (criterion)**: push latency < 100 ms; the affected test is identified
from the causal index, not from a full re-run.

### Steps

Same as Scenario B steps 1–2 (Layer 1 + Layer 3); the event carries the
generation token so A's standing state can be invalidated precisely.

---

## 5. Scenario E — A new agent trusts the tool on day one (self-proprioception)

**Task**: a fresh agent (Claude Code / Cursor / Codex — NO1-013A) is pointed
at the repo. Why would it *trust* the tool before proving it?

### DREAM (proprioception) — the tool senses itself

```
tsa --self-health --format json
→ {
  tool_latency_p50_ms: 12, tool_latency_p95_ms: 41,
  index_hit_rate: 0.97, index_staleness_median_ms: 85,
  vcsr_last_run: "0.90 (18/20) on no1-010b v3 @ <sha>",
  last_full_measurement: "2026-08-17T12:00Z"
}
```

The agent reads **one report** and knows: how fast the tool answers, how
fresh its index is, and — the decisive line — **the last measured VCSR with
its corpus version and commit**. That is not a marketing claim; it is a CI
artifact, pre-registered and continuously reproduced (RFC-0026 B2–B3). Trust
is established by evidence before the first query.

**Data (criterion)**: `--self-health` pinned in CI with exact values (no
`>=` bounds — the project's exact-assertion rule); the VCSR line only exists
when the E4 admission conditions hold (zero UNKNOWNs, pre-registration,
CI reproduction).

### Steps

1. **RFC-0026 B2** — first VCSR baseline on the 10-task seed corpus; record
   provenance in `report.json`.
2. **RFC-0025 P4** — `--self-health` surface + CI pins.
3. **NO1-013A** — integrations (Claude Code / Cursor / Codex) surface
   `authority.status` + the causal envelope in the agent's native loop.

---

## 6. The data table — why it is not surpassable

| Scenario | TODAY (pull) | DREAM (proprioception) | Criterion |
|---|---|---|---|
| A bugfix | 8 tool calls, ~6 round-trips | 1 edit call + envelope | one round-trip |
| B rename (9 sites) | ~27 queries, ~18 round-trips | 0 queries + pushed events | event < 100 ms |
| C migration freshness | per-call re-query | standing `authority.status` | stale window < 200 ms |
| D parallel agents | discovered in CI, hours later | push event mid-edit | push < 100 ms |
| E agent trust | trial-and-error | `--self-health` + VCSR line | pinned in CI |

**The moat**: none of these are single features. They are a *system* —
watch-driven incremental index (Layer 1), edit-time envelopes (Layer 2), push
events (Layer 3), standing certification (Layer 4), self-measurement (Layer
5) — and every layer is held honest by the VCSR pre-registration loop
(RFC-0026). A competitor can clone any one layer; cloning the loop means
publishing their own falsifiable numbers, which is the exact thing a
marketing-driven tool will not do.

---

## 7. Step-by-step implementation (what ships when)

| # | Ship | Artifact | Depends on |
|---|---|---|---|
| 1 | #1299 (merged) | Certified `read_existing` for `nav.context`/`edit.safe`; fail-closed seam; strace-certified on Linux | RFC-0022 P0.4 |
| 2 | RFC-0025 (merged) | Proprioception vision, phased P0–P4 | — |
| 3 | RFC-0026 (PR #1305) | VCSR benchmark design, 10-task seed corpus spec | NO1-010A |
| 4 | **P1: causal envelope** | `edit.safe` returns `causal_envelope` | #1299's snapshot reader |
| 5 | **B0: corpus + contract tests** | `benchmarks/no1_010b/` with 10 tasks; oracle red-ness enforced | RFC-0026 accepted |
| 6 | **B1: runner** | `report.json` with exact reason codes | B0 |
| 7 | **B2: VCSR baseline** | pinned VCSR + provenance; STATE.md record | B1 |
| 8 | **P2: watch index + events** | 50 ms index / 100 ms events | RFC-0025 P2; menu gate |
| 9 | **P3: standing certification** | `authority.status` < 200 ms | P2; C21 epoch |
| 10 | **P4 = NO1** | `--self-health` + E4-bounded VCSR admission | B2 + P3; NO1-013A |

**When is NO1 done?** The ledger definition (ROADMAP §3 + RFC-0026 §4): VCSR
on the pre-registered corpus ≥ the admitted E4 bound, measured continuously
in CI, with the edit→causal-envelope path requiring zero separate causality
queries. Until those numbers exist and are pinned, no unqualified claim is
made.

---

## 8. What this document does not claim

- Numbers marked **illustrative** are not measurements; they are
  placeholders that RFC-0026 B2 must replace with pinned values.
- The dream states are the *target*, not today's behavior; each row in §7 is
  a real PR with a real CI gate.
- This is a vision document, not a design spec: RFC-0025 owns the design,
  RFC-0026 owns the measurement.
