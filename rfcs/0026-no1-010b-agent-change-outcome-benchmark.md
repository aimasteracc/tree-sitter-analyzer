# RFC-0026: NO1-010B Agent Change-Outcome Benchmark (VCSR Primary Endpoint)

- **Status**: draft
- **Author(s)**: @lead-agent
- **Created**: 2026-08-17
- **Last updated**: 2026-08-17
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/task_harness.py` (corpus runner, stdin route)
  - `tree_sitter_analyzer/task/` (router truth-table, edge-evidence)
  - `benchmarks/no1_010b/` (corpus, oracles, runner, report, registration)
  - `tests/unit/task/test_no1_010b_corpus.py` (exact pins for the runner)
  - `rfcs/ROADMAP-no1-agent-trust.md` (ledger row NO1-010B)

## Summary

A pre-registered, reproducible **agent change-outcome benchmark** whose primary
endpoint is **Verified Change Success Rate (VCSR)** — the north star of
`ROADMAP-no1-agent-trust.md`. The corpus is a pinned set of change tasks, each
with a repo fixture, a behavioral oracle, an allowed-path set, a declared
verification command, and a closed-enum task class. The runner is a
**patch verifier**: it applies an externally supplied patch (or a
provenance-bound agent-arm output) and evaluates the five VCSR criteria on the
resulting tree. A task PASSES only when all five hold; `unknown` is a
first-class outcome, never a pass. The benchmark must fail closed when
evidence is insufficient, exactly like RFC-0021 and RFC-0022's fail-closed
honesty.

## Motivation

NO1-010A (#1290 + follow-ups) proved the task layer runs end-to-end
(`understand` / `plan_change` / `assess_change` through the internal harness
bridge). What is missing is the **measurement**: no pre-registered corpus and
oracle protocol operationalizes the VCSR north-star criteria into runnable
tasks with pass/fail rules. A change is "verified" today only by whichever
tests an agent happens to run; there is no corpus where the expected outcome
is known a priori, so routing/evidence regressions are found by dogfooding,
not by CI. This RFC closes that gap: **every task's expected outcome is pinned
before any run**, so CI detects regressions and the VCSR number is real.

## Detailed design

### 1. Corpus format (JSONL, pre-registered, strict model)

One task per line. A **dedicated `BenchmarkRecord` model** (not
`task_harness._strict_json_loads`) validates the record with a strict
allowlist: unknown fields are rejected (schema typos fail), every field is
typed, and only the `understand`/`plan_change`/`assess_change` projection is
forwarded to the task harness `request_from_dict`. A record example:

```json
{
  "id": "no1-010b/0001-bugfix-dispatch-null",
  "task_class": "bugfix",
  "repo": "fixtures/dispatch_app",
  "operation": "plan_change",
  "task": "dispatch returns None for an unknown route; return a 404 object instead",
  "allowed_paths": ["src/dispatch.py", "tests/"],
  "oracle": "oracles/0001.py",
  "oracle_baseline_reason": "returns None, no 404 branch",
  "verification_command": "uv run pytest tests/ -q",
  "defect": {"file": "src/dispatch.py", "line": 12, "kind": "missing-else"}
}
```

- `task_class` is a **required closed enum**: `bugfix | refactor | migration |
  test_selection`. The report must include exact per-class counts and VCSR per
  class per repo (the ROADMAP scorecard requires it); classes are never
  inferred from IDs.
- `allowed_paths` entries are **canonical, repository-relative**, with
  segment-aware semantics: a directory entry (`tests/`) matches its exact
  descendants on path-segment boundaries (`tests/test_dispatch.py` yes,
  `tests-escape/file.py` no); a file entry matches exactly.
- `oracle_baseline_reason` documents why the oracle is red on the unmodified
  fixture; the runner asserts the baseline failure matches it (see §3).
- `repo` is pinned by git commit; the runner checks out the pinned commit and
  fails closed on drift.

### 2. Patch protocol (how a change reaches the runner)

The runner is a **patch verifier**; it never mutates the repository itself
(the `task_harness` bridge contract stays read-only). Two input channels:

1. **Supplied patch** (default): the corpus runner receives a **unified diff
   in `git apply`-parseable form** (stdin `-` route or `--patch <file>`), a
   `--repo` commit, and an optional `--arm` identity. The runner creates an
   isolated worktree copy at the pinned commit, applies the patch with
   `git apply --check` first (a non-applicable patch is `UNKNOWN`, never
   `FAIL`), then evaluates the five criteria on the patched tree.
2. **Agent arm** (separate, provenance-bound): an optional runner mode that
   drives a pinned model/client through the task layer and captures the
   agent's produced patch AND its **verification-command transcript** (the
   exact commands the agent selected and ran, recorded with their outputs).
   Each arm carries `client`, `model`, `backend`, and `arm_id` identity in the
   manifest; arms are never pooled (ROADMAP requires ≥3 clients/models
   measured without pooling). The primary B0–B2 endpoint is the patch
   verifier; agent arms are isolated measurements feeding the same report
   format.

The corpus record gains an optional `patch` field only for *fixture* tasks
used to validate the runner's positive/negative controls (§5) — the real
benchmark inputs always arrive through the channels above.

### 3. Runner checks (exact VCSR criteria)

After applying the patch in the isolated worktree:

| Criterion | Runner check | Reason code |
|---|---|---|
| modify only allowed paths | segment-aware allowlist vs the applied diff | `PATH_VIOLATION` |
| satisfy the behavioral oracle | oracle exit-code contract (below) | `ORACLE_FAILED` |
| pass the declared verification command | run `verification_command`, exit 0 required | `VERIFICATION_FAILED` |
| leave no stale symbol or edge rows | **exact persisted-row queries** (below) | `STALE_ROWS` |
| no high-confidence unsupported relationship used to justify the change | RFC-0022 truth-table rejection family | `UNSUPPORTED_RELATIONSHIP` |
| evidence insufficient / infra failure | any check unavailable, oracle error, patch not applicable, timeout | `UNKNOWN` |

**Oracle exit-code contract** (three channels, never conflated):

- `0` = behavioral assertion PASSED;
- `1` = behavioral assertion FAILED (this is the only path that yields
  `ORACLE_FAILED`);
- `2` = oracle execution error (syntax error, missing interpreter/dependency,
  harness failure);
- timeout (60 s) or non-zero `2`-class exits and any `UNKNOWN`-class
  infrastructure failure are scored `UNKNOWN`, never `FAIL`. The runner
  validates that the baseline run fails with the recorded
  `oracle_baseline_reason` before any patch is evaluated.

**Stale-row check (persisted rows, not evidence freshness)**:

`task/edge_evidence.py` validates *bundles*; it cannot see obsolete rows
already in the index. The runner instead runs exact, post-change queries
against the refreshed index and asserts present/absent counts, mirroring
RFC-0021's incremental oracle:

- for every deleted symbol `S` (file, name): `SELECT 1 FROM ast_symbol_rows
  WHERE file_path = ? AND name = ?` must return no row;
- for every deleted edge `E` (caller, callee): no `edges` row may reference
  `E`;
- for every added symbol/edge: exactly the expected rows exist (count-pinned,
  no `>=` bounds).
The refresh operation is specified as: rebuild the changed files' symbol and
edge rows from the patched tree, then run the above queries.

### 4. Claim policy and pre-registration gate

- **Immutable registration record**: before the first execution of any task,
  the runner appends the corpus manifest hash + per-task oracle hashes to an
  **append-only registration registry** (a committed `registration.jsonl`
  under `benchmarks/no1_010b/`, itself committed to git). A run's report is
  only valid if every task/oracle hash in it was registered *before* that
  run's first execution; a run whose hashes were registered after the fact is
  rejected. Post-result oracle replacement is impossible by construction.
- E0–E3: internal numbers only, no public competitive wording.
- **E3 requires separately attested reproduction**: an independent machine,
  blind evaluation, and a separate attestation record — a CI job in the
  repository is still internal evidence and does not satisfy E3.
- **E4** (the only admissible public sentence —
  `VCSR = X/Y (Z%) on the pre-registered NO1-010B corpus vN at analyzer commit
  <sha>`): requires all of: corpus pre-registered before the run, zero
  UNKNOWNs, the E3 independent reproduction, AND an external E4 reproduction
  artifact (a third party reproducing the report from the registration
  record). Absent any one, no public wording is emitted.

### 5. Seed corpus and B1 non-vacuous gate

The first corpus ships with **10 pre-registered tasks** (4 bugfix, 2
refactor, 2 migration, 2 test_selection), each with a **pre-registered
expected outcome** (9 PASS + 1 FAIL for a known-wrong reference patch).

**B1 completes only when the runner matches exact expected outcomes AND
survives a mutation suite** that forces every reason code:

- positive mutation: the reference (correct) patch → must yield the pinned
  PASS with all five checks exercised;
- `PATH_VIOLATION`: patch touching an out-of-allowlist path → exact code;
- `ORACLE_FAILED`: patch leaving the oracle red → exact code;
- `VERIFICATION_FAILED`: patch that passes the oracle but breaks the
  verification command → exact code;
- `STALE_ROWS`: patch whose index refresh leaves a stale row (injected) →
  exact code;
- `UNSUPPORTED_RELATIONSHIP`: patch justified by a high-confidence
  unsupported relationship (fixture) → exact code;
- `UNKNOWN`: a non-applicable patch and an oracle-execution-error fixture →
  exact code.

An implementation that always returns `UNKNOWN` or always `FAIL` fails B1.

For **test_selection** tasks, the check compares the agent arm's recorded
selected-test transcript (or the supplied `selected_tests` field) against an
exact affected-test oracle derived from the causality index — running the
full suite, no tests, or the wrong subset is `TEST_SELECTION_FAILED`, not a
pass.

## Phases with visible exit artifacts

| Phase | Scope | Verifiable exit artifact |
|---|---|---|
| **B0** | RFC accepted; strict `BenchmarkRecord` model; 10-task seed corpus; registration registry | `benchmarks/no1_010b/` with 10 tasks; corpus contract tests green (unknown-field rejection, oracle red-baseline + reason, allowlist semantics, per-class counts) |
| **B1** | Patch-verifier runner complete (all 5 checks + oracle exit-code contract + stale-row queries + mutation suite) | 10/10 pre-registered outcomes matched exactly; mutation suite forces all 7 reason codes; CI reproduces |
| **B2** | VCSR baseline measurement on pinned versions | `report.json` with VCSR + per-class/per-repo breakdown + provenance; baseline recorded in STATE.md; E0–E3 internal only |
| **B3** | (gated) E4 bounded admission | only with zero UNKNOWNs, E3 independent attestation, external E4 reproduction — per §4 |

## Interaction with existing seams

- The runner drives the task layer through `task_harness.McpPrimitiveExecutor`
  (same-process bridge, read-only); the `task/` import boundary is preserved.
- The stale-row/unsupported checks use the RFC-0022 truth-table rejection
  family plus the new persisted-row queries (§3); `edge_evidence` remains the
  bundle validator, not the staleness oracle.
- The harness stdin route (`load_corpus("-")`, 8 MiB bound) carries corpus
  input; the patch channel is a separate stdin/`--patch` stream so a corpus
  record and a patch never share a parser.

## Alternatives considered

1. **Benchmark the analyzer, not the change** (compare tool answers on fixed
   prompts): measures retrieval, not whether a *change* succeeds. RFC-0021
   keeps the competitive answer-quality role; NO1-010B is the change-outcome
   endpoint.
2. **Agent-in-the-loop only**: closest to production, but provider/model
   variance and cost make it non-reproducible in CI; also violates the
   no-pooling rule if arms share backends. Chosen: patch verifier as the
   primary endpoint, provenance-bound agent arms as isolated measurements.
3. **No pre-registration** (run tasks, then decide oracles): invalid for the
   evidence level. Rejected.

## Open questions

1. Whether the agent-arm transcript should include raw stdout or only
   exit-code + selected-test sets (propose: exit-codes + selected sets for
   privacy; raw stdout stored locally, never in the committed report).
2. Registration registry rotation: append-only file vs SQLite table (propose:
   committed `registration.jsonl` + the runner's local SQLite mirror).
3. Whether `git apply` should accept fuzz (propose: no — fuzz would admit
   patches that do not match the pinned commit, breaking pre-registration).
