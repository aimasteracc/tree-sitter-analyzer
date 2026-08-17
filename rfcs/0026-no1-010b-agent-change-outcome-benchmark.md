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

1. **Supplied patch** (validation channel, not the agent measurement): the
   corpus runner receives a **unified diff in `git apply`-parseable form**
   (`--patch <file>`; the stdin `-` mode is mutually exclusive with the
   corpus `-` mode — one stdin stream cannot feed both parsers, so at most
   one input may use `-` and the other must be a file). The patch input is
   **bounded before `git apply`** — CANONICAL limits bound into the
   registered manifest, not examples: `patch_max_bytes = 1 MiB`,
   `patch_max_hunks = 512`, `patch_max_lines_per_hunk = 2000` (C41). An
   over-bound patch is `UNKNOWN`, never applied (C40). The limits are part
   of the manifest hash so an evaluator cannot choose thresholds after
   observing an attempt. A `--repo` commit,
   `--arm` identity, and — for criterion 5 — a **provenance transcript**
   (the set of graph relationships the patch producer recorded seeing/using,
   e.g. the `nav.context` + `edit.safe` envelopes observed during
   production) are required. The runner creates an isolated worktree copy at
   the pinned commit, applies the patch with `git apply --check` first (a
   non-applicable patch is `UNKNOWN`, never `FAIL`), then evaluates the five
   criteria on the patched tree. **Criterion 5 is `UNKNOWN` for any supplied
   patch without a provenance transcript** — a final diff cannot prove which
   relationships justified the change.
2. **Agent arm** (provenance-bound, MANDATORY gate): a runner mode that
   drives a pinned model/client through the task layer and captures the
   agent's produced patch AND its **verification-command transcript** (the
   exact commands the agent selected and ran, recorded with their outputs).
   Each arm carries `client`, `model`, `backend`, `arm_id`, AND a **frozen
   full configuration hash** (client executable/version, system and
   developer prompts, tool permissions/config, sampling parameters) — the
   configuration is frozen before execution and any change invalidates the
   arm (C29). The arm ALSO records the **graph evidence it was presented
   with and used** (the `nav.context`/`edit.safe`/impact envelopes observed
   during production) so criterion 5 is evaluable for arms, not only for
   supplied patches (C33). Each arm has a **pre-authorized spend gate**: a
   registered per-arm ceiling on calls, tokens, and cost, plus an
   authorization artifact, per the ROADMAP budget-gate rule (C36). Arms are
   never pooled (ROADMAP requires ≥3 clients/models measured without
   pooling). **At least three distinct client/model arms, isolated and
   non-pooled, are a mandatory B2 completion gate** — a VCSR baseline
   produced only from supplied reference patches does not satisfy NO1-010B.
   **Paired control arms are also mandatory for the Wave-2 outcome**: for
   each evidence-enabled arm there is a pre-registered control arm (graph
   evidence disabled) so the counterfactual "graph evidence improved the
   change" is measurable, not asserted (C28). The pair holds **every
   non-evidence parameter constant** — same backend, system/developer
   prompts, sampling parameters, permissions, budgets, random seeds, and
   repeat schedule; the ONLY permitted difference is the pre-registered
   evidence toggle (C37).

**Sandbox**: patched code is executed in a resource-bounded sandbox — no
network, no secrets/credentials mounted, and only the disposable worktree
writable (C21). An isolated Git worktree does not isolate processes; the
oracle and verification command must run with host permissions that cannot
read credentials or touch files outside the worktree.

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
| no high-confidence unsupported relationship used to justify the change | **explicit oracle**: the RFC-0023 `edge_evidence` rejection family (concrete per-edge rules: unsupported kind, unresolved callee with high-confidence reliance, provenance-conflicting rows) applied to the recorded graph-evidence transcript; the RFC-0022 truth table alone does not classify this criterion (C30) | `UNSUPPORTED_RELATIONSHIP` |
| evidence insufficient / infra failure | any check unavailable, oracle error, patch not applicable, timeout | `UNKNOWN` |

**Oracle result protocol (trusted wrapper, not raw exit codes)**:

Raw numeric codes are insufficient: an uncaught `AssertionError`,
`ImportError`, or `SyntaxError` in a Python oracle all exit with code 1, so a
missing dependency or malformed oracle would masquerade as a behavioral
failure (C19). The runner instead invokes each oracle through a **trusted
wrapper** that separates loading/execution from the declared assertion:

- wrapper performs import/load first; any import/syntax/type error → `UNKNOWN`;
- only the oracle's explicitly declared assertion result maps to PASS
  (exit 0) or FAIL (exit 1 → `ORACLE_FAILED`);
- every other exception, timeout (60 s), or unexpected process exit → `UNKNOWN`.
The baseline validation uses a **typed reason protocol** (C42): on a FAIL
result the oracle also prints a second declared line
`NO1_010B_ORACLE_REASON: <token>`; the runner requires the baseline FAIL
reason token to EQUAL the registered `oracle_baseline_reason` token (exact
match, no exception-text comparison). A baseline red for a different reason —
or missing the reason line — is a corpus/fixture error and fails closed.

**Stale-row check (persisted rows, not evidence freshness)**:

`task/edge_evidence.py` validates *bundles*; it cannot see obsolete rows
already in the index. The runner compares the **refreshed projection** with a
**clean-rebuild projection** of the patched tree and requires byte-identical
rows for the affected files — this covers added, deleted, AND modified rows
(a symbol that keeps `(file, name)` but moves line, or an edge that keeps
endpoints but changes kind/line/resolution, must not survive) (C16):

1. index the BASELINE (pre-patch) tree;
2. apply the incremental refresh over the baseline→patched transition (the
   transition where stale rows actually arise — refreshing an index already
   representing the patched sources proves nothing, C24);
3. index the patched tree fresh (clean rebuild);
4. assert the refreshed projection equals the clean-rebuild projection using
   a **canonical semantic identity** that EXCLUDES surrogate keys
   (`ast_symbol_rows.id`, `edges.id`, and the inherited `callee_symbol_id`)
   — autoincrement keys differ across rebuilds even when every semantic
   symbol/edge is correct (C35); compare `(file_path, name, line, kind, ...)`
   and `(source, target, kind, line, resolution, provenance, ...)`;
5. include **incoming edges owned by unchanged files** (an unchanged caller's
   `edges.file_path` row whose `callee_resolved_file` points into the changed
   file must be compared too) — restricting to affected files misses those
   cross-file rows (C34).

**Allowed-path recheck**: the allowlist is compared against the applied diff
AND re-compared after every executed command (oracle, verification) against a
worktree snapshot, including untracked files — an allowed test-file change
that rewrites a production file during evaluation is `PATH_VIOLATION` (C18).
**Trusted tool artifacts are excluded**: files the declared verification
command or oracle legitimately creates (`.pytest_cache/`, `__pycache__/`,
`.mypy_cache/`, `.ruff_cache/`) are on a pinned allowlist of excluded paths,
so a correct reference patch never deterministically fails path enforcement
(C25).

### 4. Claim policy and pre-registration gate

- **Immutable registration record**: before the first execution of any task,
  the runner appends the corpus manifest hash + per-task oracle hashes +
  **`repo_commit` + clean-tree fingerprint** (C15) + a **run/attempt
  identity** to an **append-only registration registry**. **Every execution
  attempt is retained in the score** — a stochastic arm rerun after a
  failing patch cannot discard that run; a fixed repeat count and retry rule
  are registered per arm, and the report reflects all attempts, never a
  cherry-picked subset (C23). The registry is anchored OUTSIDE evaluator
  control (C14): an externally timestamped or independently controlled
  append-only store (e.g. a CI-only workflow with a dedicated key, or a
  third-party notary) — a plain git-committed file is NOT sufficient,
  because the evaluator can run privately, tune, and then commit an entry
  that appears to pre-date the disclosed run. ALL registration attempts are
  retained (including superseded ones). A run's report is only valid if every
  task/oracle hash in it was registered *before* that run's first execution;
  a run whose hashes were registered after the fact is rejected.
- E0–E3: internal numbers only, no public competitive wording.
- **E3 requires separately attested reproduction**: an independent machine,
  blind evaluation, and a separate attestation record — a CI job in the
  repository is still internal evidence and does not satisfy E3.
- **E4** (the only admissible public sentence — must be bounded by arm
  identity, repository revisions, date, and versions per ROADMAP §6-7, C20):
  `VCSR = X/Y (Z%) on the pre-registered NO1-010B corpus vN at analyzer commit
  <sha>, arm <client>/<model>/<backend>/<arm_id>, repos <repo@commit,...>,
  run <date>, evidence E4`. Requires all of: corpus pre-registered before the
  run, zero UNKNOWNs, the three non-pooled agent arms executed, the E3
  independent reproduction, AND an external E4 reproduction artifact (a
  third party reproducing the report from the registration record). Absent
  any one, no public wording is emitted.

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
  exact code;
- `TEST_SELECTION_FAILED`: on a test_selection task, a transcript with an
  incorrect, empty, or full-suite selected-test set → exact code (C17).

An implementation that always returns `UNKNOWN` or always `FAIL` fails B1.

For **test_selection** tasks, the check compares the agent arm's recorded
selected-test transcript (or the supplied `selected_tests` field — a typed,
canonical relative-path list on the strict `BenchmarkRecord`, provided
through the same `--patch`/`--selected-tests` CLI channel, C32) against an
**independently pre-registered affected-test oracle** — frozen per task at
registration, never derived at runtime from the causality index being
evaluated (a self-derived oracle would validate comparison plumbing, not
selection correctness, C26). Running the full suite, no tests, or the wrong
subset is `TEST_SELECTION_FAILED`, not a pass.

## Phases with visible exit artifacts

| Phase | Scope | Verifiable exit artifact |
|---|---|---|
| **B0** | RFC accepted; strict `BenchmarkRecord` model; 10-task seed corpus; registration registry | `benchmarks/no1_010b/` with 10 tasks; corpus contract tests green (unknown-field rejection, oracle red-baseline + reason, allowlist semantics, per-class counts) |
| **B1** | Patch-verifier runner complete (all 5 checks + oracle exit-code contract + stale-row queries + mutation suite) | 10/10 pre-registered outcomes matched exactly; mutation suite forces all 7 reason codes; CI reproduces |
| **B2** | VCSR baseline measurement on pinned versions | `report.json` with VCSR + per-class/per-repo **and per-arm** breakdown (exact task counts and outcomes per client/model/backend — arms are never pooled in the report, C31) + **the reliability metric per arm and overall**: `successful_indexed_trials / all_trials` with exact numerator, denominator, failure classes (infrastructure vs product), and the 99% reliability gate status (C38). **B2 does not complete unless the 99% reliability threshold is met per arm and overall** — a below-threshold run is recorded but cannot advance to baseline (C39) + provenance; baseline recorded in STATE.md; E0–E3 internal only |
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
2. Whether the externally controlled registration store should be a CI-only
   workflow with a dedicated signing key or a third-party notary (both are
   outside evaluator control; the committed-file + SQLite-mirror proposal is
   rejected — it cannot establish pre-execution ordering, C27).
3. Whether `git apply` should accept fuzz (propose: no — fuzz would admit
   patches that do not match the pinned commit, breaking pre-registration).
