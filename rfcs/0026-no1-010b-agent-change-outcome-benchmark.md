# RFC-0026: NO1-010B Agent Change-Outcome Benchmark (VCSR Primary Endpoint)

- **Status**: draft
- **Author(s)**: @lead-agent
- **Created**: 2026-08-17
- **Last updated**: 2026-08-18
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/task_harness.py` (corpus runner, stdin route)
  - `tree_sitter_analyzer/task/` (router truth-table, edge-evidence)
  - `tree_sitter_analyzer/no1_010b/` (record, patch bounds, oracle, runner)
  - `benchmarks/no1_010b/` (corpus, oracles, runner, report, registration)
  - `tests/unit/no1_010b/` (exact record/oracle/runner contracts)
  - `rfcs/ROADMAP-no1-agent-trust.md` (ledger row NO1-010B)

## Summary

A pre-registered, reproducible **agent change-outcome benchmark** whose primary
endpoint is **Verified Change Success Rate (VCSR)** — the north star of
`ROADMAP-no1-agent-trust.md`. The corpus is a pinned set of change tasks, each
with a repo fixture, a behavioral oracle, an allowed-path set, a typed
verification argv (no shell parsing), and a closed-enum task class. The runner is a
**patch verifier**: it applies an externally supplied patch (or a
provenance-bound agent-arm output) and evaluates the VCSR criteria on the
resulting tree. A task PASSES only when **every applicable criterion holds**
(five, plus the selected-test criterion for `test_selection` tasks);
`unknown` is a first-class outcome, never a pass. The benchmark must fail closed when
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
  "repo_commit": "0000000000000000000000000000000000000000",
  "operation": "plan_change",
  "task": "dispatch returns None for an unknown route; return a 404 object instead",
  "allowed_paths": ["src/dispatch.py", "tests/"],
  "oracle": "oracles/0001.py",
  "oracle_baseline_reason": "dispatch-returns-none",
  "verification_argv": ["uv", "run", "pytest", "tests/", "-q"],
  "expected_terminal": {"verdict": "PASS", "reason_code": null},
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
- `oracle_baseline_reason` is a **canonical token** (lowercase-kebab, e.g.
  `dispatch-returns-none`) identifying the pre-registered assertion that is
  red on the unmodified fixture; the runner asserts the oracle emits that
  same token on every declared PASS or FAIL (see §3). Free-text descriptions
  are rejected at load (C43).
- `expected_terminal` is a **required strict object** registered per task and
  included in the manifest hash. Its `verdict` is `PASS | FAIL | UNKNOWN`.
  `reason_code` is `null` only for `PASS`, one exact product reason code for
  `FAIL`, and one exact `unknown_reason` member for `UNKNOWN`. The aggregate
  `9 PASS + 1 FAIL` statement is not executable truth; this object is. A
  runner compares each reference attempt with this exact pair and may not
  choose the failing task or code after execution (C55).
- The verification executable is a **typed argv list, never a shell string**:
  `verification_argv` is executed with no shell, no quoting rules, and no
  globbing; a display-only `verification_command` string may accompany it for
  humans but is never the execution spec (C43).
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
   observing an attempt. `patch_max_lines_per_hunk` counts **every physical
   hunk-body line** after an `@@` header and before the next hunk/file header:
   additions, deletions, context, blank body lines, and
   `\ No newline at end of file` markers all count; only the `@@` header and
   file/diff headers do not. A hunk at exactly the limit is accepted, limit+1
   is over-bound (C43/C44). **The same bounds
   apply to every input channel** — an agent-produced patch from a
   mandatory arm must pass the same registered streaming limits before
   parsing, so an oversized arm output is `UNKNOWN`, never processed (C43).
   A `--repo` commit,
   `--arm` identity, and — for criterion 5 — a **provenance transcript**
   (the set of graph relationships the patch producer recorded seeing/using,
   e.g. the `nav.context` + `edit.safe` envelopes observed during
   production) are required. The runner creates an isolated worktree copy at
   the pinned commit, applies the patch with `git apply --check` first (a
   non-applicable patch is `UNKNOWN`, never `FAIL`), then evaluates the
   criteria on the patched tree (five, plus the selected-test criterion for
   `test_selection` tasks). **Criterion 5 is `UNKNOWN` for any supplied
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
   evidence toggle (C37). **Fresh state per attempt (C43)**: every
   registered arm-task-repeat attempt starts from a fresh isolated worktree
   at the pinned commit AND a fresh client conversation/session — no prior
   attempt's conversation context, tool caches, or index state may carry
   over; the treatment/control pair uses identical fresh-state procedures so
   results are order-independent.

**Pre-registered paired evidence-effect endpoint** (C56): every treatment
arm has a `pair_id` with exactly one evidence-disabled control, and the
external registration freezes the complete `pair_id × task_id ×
repeat_index` matrix, matched random seed, and these endpoint parameters:
`minimum_effect = 0.05`, one-sided exact McNemar/binomial test
`alpha = 0.05`. For each registered cell, let `T`/`C` be 1 only when the
treatment/control verdict is `PASS` (every FAIL or UNKNOWN is 0). Report
`n11`, `n10`, `n01`, `n00`, where `n10` means treatment-only success, and
`paired_effect = (n10 - n01) / N`. For `D = n10 + n01 > 0`, the exact
one-sided p-value is `sum(comb(D, k) * 0.5^D for k = n10..D)`; for `D = 0`,
`p = 1`. The improvement endpoint is `ADMITTED`
iff the matrix is complete, there are zero UNKNOWN attempts, every arm and
the overall run pass the 99% reliability gate, `paired_effect >= 0.05`, and
the one-sided exact binomial test over the `n10 + n01` discordant pairs has
`p <= 0.05` in the direction `n10 > n01`; with zero discordant pairs,
`p = 1`. Missing cells are never dropped or imputed: they make the matrix
invalid and block B2. The report always emits the counts, effect, p-value,
thresholds, and `ADMITTED | NOT_ADMITTED`; only `ADMITTED` permits the
bounded statement that graph evidence improved changes. A valid negative
result remains publishable as `NOT_ADMITTED` and cannot be reframed after
the run.

**Sandbox**: patched code is executed in a resource-bounded sandbox — no
network and no secrets/credentials mounted (C21). Patch application is the
only phase allowed to write the candidate tree. Before oracle, verification,
or index checks begin, the runner snapshots then mounts the **entire patched
candidate tree read-only**, including paths that were allowed during patch
application. The only writable mount is a fresh runner-owned scratch root
outside the candidate tree; `TMPDIR`, tool caches, coverage files, Python
bytecode, and both analyzer comparison databases are redirected there via
the frozen environment. An isolated Git worktree alone is not a sandbox.

The corpus record gains an optional `patch` field only for *fixture* tasks
used to validate the runner's positive/negative controls (§5) — the real
benchmark inputs always arrive through the channels above.

### 3. Runner checks (exact VCSR criteria)

After applying the patch in the isolated worktree:

| Criterion | Runner check | Reason code |
|---|---|---|
| modify only allowed paths | segment-aware allowlist vs the applied diff | `PATH_VIOLATION` |
| satisfy the behavioral oracle | oracle exit-code contract (below) | `ORACLE_FAILED` |
| pass the declared verification command | run the typed `verification_argv`, exit 0 required | `VERIFICATION_FAILED` |
| leave no stale symbol or edge rows | **exact persisted-row queries** (below) | `STALE_ROWS` |
| no high-confidence unsupported relationship used to justify the change | **explicit oracle**: the RFC-0023 `edge_evidence` rejection family (concrete per-edge rules: unsupported kind, unresolved callee with high-confidence reliance, provenance-conflicting rows) applied to the recorded graph-evidence transcript; the RFC-0022 truth table alone does not classify this criterion (C30) | `UNSUPPORTED_RELATIONSHIP` |
| (test_selection tasks only) selected-test transcript equals the pre-registered affected-test oracle | compare the recorded transcript with the frozen oracle set (§5) | `TEST_SELECTION_FAILED` |
| evidence insufficient / infra failure | any check unavailable, oracle error, patch not applicable, timeout | `UNKNOWN` (+ required `unknown_reason` subcode, below) |

**Oracle result protocol (trusted wrapper, not raw exit codes)**:

Raw numeric codes are insufficient: an uncaught `AssertionError`,
`ImportError`, or `SyntaxError` in a Python oracle all exit with code 1, so a
missing dependency or malformed oracle would masquerade as a behavioral
failure (C19). The runner instead invokes each oracle through a **trusted
wrapper** that separates loading/execution from the declared assertion:

- wrapper performs import/load first; any import/syntax/type error → `UNKNOWN`;
- only a process exit 0 with exactly one final declared assertion result maps
  to PASS or FAIL (`FAIL` → `ORACLE_FAILED`); the result marker, not the raw
  process code, carries the behavioral verdict;
- every other exception, timeout, or unexpected process exit → `UNKNOWN`
  (see the canonical timeouts below).
The baseline validation uses a **typed reason protocol** (C42, C43): on every
declared PASS or FAIL the oracle also prints exactly one declared line
`NO1_010B_ORACLE_REASON: <token>`; the token must EQUAL the registered
`oracle_baseline_reason` token (exact string match, no exception-text
comparison). Preflight executes the oracle on the unmodified fixture and
requires declared FAIL plus the exact token. Missing, duplicate, or
mismatched lines during that baseline check are corpus validation failures:
they consume zero attempts and emit no report. After preflight, the same
protocol failure during a retained patched-tree attempt is `UNKNOWN /
ORACLE_PROTOCOL_ERROR`; it is never silently converted to PASS or a product
failure.

**Canonical execution spec (typed argv, frozen environment, canonical
timeouts)** (C43):

- Every executed command (oracle, verification) is a **typed argv list**
  executed with no shell, no quoting rules, no globbing; cwd is always the
  worktree root; the environment is the registered frozen base environment
  (pinned PATH entries, no inherited secrets, an `env_digest` included in the
  manifest hash). A free-form `verification_command` string may exist only as
  a display hint, never as the execution spec.
- Canonical wall-clock timeouts are bound into the registered manifest:
  `oracle_timeout = 60 s`, `verification_timeout = 120 s`. On expiry the
  runner terminates the **whole process tree** (SIGTERM to the process group,
  a short grace period, then SIGKILL) and records `UNKNOWN` with
  `unknown_reason = ORACLE_TIMEOUT` / `VERIFICATION_TIMEOUT`.

**Reliability mapping (exhaustive terminal states)** (C43/C55): every retained
attempt ends in exactly one terminal state; `UNKNOWN` outcomes MUST carry an
`unknown_reason` subcode from the closed enum below. No catch-all string is
permitted:

`{PATCH_NOT_APPLICABLE, PATCH_OVER_BOUND, PROVENANCE_MISSING,
AGENT_OUTPUT_ERROR, ORACLE_LOAD_ERROR, ORACLE_EXECUTION_ERROR,
ORACLE_PROTOCOL_ERROR, ORACLE_TIMEOUT, VERIFICATION_EXECUTION_ERROR,
VERIFICATION_TIMEOUT, INDEX_REFRESH_ERROR, INDEX_QUERY_ERROR,
EVIDENCE_CHECK_ERROR, SANDBOX_FAILURE, REGISTRY_FAILURE}`.

`ORACLE_EXECUTION_ERROR` covers runtime exceptions and unexpected exits after
load; `PROVENANCE_MISSING` covers a supplied patch or arm without the required
graph transcript; `INDEX_REFRESH_ERROR` and `INDEX_QUERY_ERROR` distinguish
index construction/refresh from semantic comparison failures; command spawn,
signal termination, or protocol-level launch failures use
`VERIFICATION_EXECUTION_ERROR` (an ordinary nonzero verification exit remains
the product verdict `VERIFICATION_FAILED`). A write
journal or read-only mount failure is `SANDBOX_FAILURE`, and an unavailable
unsupported-evidence check is `EVIDENCE_CHECK_ERROR`. The mapping to the
per-arm reliability metric `successful_indexed_trials / all_trials` is fixed:

| Terminal state | Verdict reached? | Counts toward numerator | Failure class |
|---|---|---|---|
| `PASS` | yes | yes | — |
| `PATH_VIOLATION`, `ORACLE_FAILED`, `VERIFICATION_FAILED`, `STALE_ROWS`, `UNSUPPORTED_RELATIONSHIP`, `TEST_SELECTION_FAILED` (`{FAIL, reason_code}`) | yes | yes | product |
| `UNKNOWN` (`PATCH_NOT_APPLICABLE`, `PATCH_OVER_BOUND`, `PROVENANCE_MISSING`, `AGENT_OUTPUT_ERROR`) | no | no | product (input/output) |
| `UNKNOWN` (`ORACLE_LOAD_ERROR`, `ORACLE_EXECUTION_ERROR`, `ORACLE_PROTOCOL_ERROR`, `ORACLE_TIMEOUT`, `VERIFICATION_EXECUTION_ERROR`, `VERIFICATION_TIMEOUT`) | no | no | infrastructure (execution) |
| `UNKNOWN` (`INDEX_REFRESH_ERROR`, `INDEX_QUERY_ERROR`, `EVIDENCE_CHECK_ERROR`, `SANDBOX_FAILURE`, `REGISTRY_FAILURE`) | no | no | infrastructure (runner) |

The 99% reliability gate is `numerator / denominator ≥ 0.99` per arm and
overall: at most 1% of retained attempts may end as `UNKNOWN`. Every product
outcome — `PASS` or any named reason code — counts as a successfully indexed
trial (a verdict was reached), so an agent failing tasks does not itself block
the gate; only attempts that die before a verdict (input or infrastructure
`UNKNOWN`) reduce reliability. Failure classes are reported for diagnosis,
but the gate counts every non-verdict attempt equally, because a baseline
whose denominator silently drops attempts is not trustworthy (C38, C43).

**Stale-row check (persisted rows, not evidence freshness)**:

`task/edge_evidence.py` validates *bundles*; it cannot see obsolete rows
already in the index. The runner compares the **refreshed projection** with a
**clean-rebuild projection** of the patched tree and requires byte-identical
semantic rows across the **complete symbol and edge tables** — benchmark
fixtures are bounded, and a partial affected-file projection misses global
resolution changes such as a new duplicate name altering an unchanged
caller's target. This covers added, deleted, AND modified rows
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
5. compare the complete canonical edge projection, including incoming edges
   owned by unchanged files and edges whose source/target files are unchanged
   but whose resolution changed through a duplicate/renamed symbol; separately
   validate referential integrity after deterministic surrogate-ID remapping
   (C34/C57).

**Allowed-path recheck**: the allowlist is compared against the applied diff.
After patch application, the immutable candidate-tree snapshot is re-compared
after every executed command, including untracked files. Any candidate-tree
change is `PATH_VIOLATION`, even if it touches a path that was allowed for the
patch itself (C18/C55).

**Write-boundary enforcement during execution, not only after** (C43):
post-command snapshots cannot detect a write that is reverted before the
process exits — an allowed test hook can temporarily overwrite a candidate
production file, run verification against the altered implementation, then
restore the original bytes, leaving the snapshot clean
while an otherwise failing patch passes. The runner therefore enforces the
boundary WHILE each process runs: the **entire candidate tree is read-only**
(kernel-enforced) AND an audit/write journal records attempted and successful
writes during each command. A journaled candidate-tree write is
`PATH_VIOLATION` regardless of allowlist membership or final bytes. This
prevents a candidate-controlled test hook from temporarily replacing even an
allowed production file and restoring it after verification (C55). The
post-command snapshot remains defense in depth. There is no trusted-artifact
exception inside the candidate tree: `.pytest_cache`, `__pycache__`, mypy,
ruff, coverage, temporary files, and TSA `.ast-cache` databases are redirected
to the fresh runner scratch mount; if one appears in the candidate tree it is
a violation (C25/C58).

### 4. Claim policy and pre-registration gate

- **Immutable registration record**: before the first execution of any task,
  the runner appends an explicit canonical payload containing the corpus
  manifest hash; each task's `repo_commit`, clean-tree fingerprint,
  `expected_terminal`, oracle hash, affected-test-oracle hash, and independent
  oracle signature; the frozen environment/timeout/patch-limit digest; every
  `arm_id`, `pair_id`, evidence toggle, full arm-configuration hash, spend
  authorization hash, and random seed; the complete arm × task × repeat
  matrix; repeat/retry policy; paired-endpoint thresholds; and every
  **run/attempt identity** to an **append-only registration registry**. Any
  execution-time mismatch rejects the run. **Every execution
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
  a run whose hashes were registered after the fact is rejected. **Corpus
  preflight runs before any attempt is recorded**: baseline-reason tokens,
  typed argv, manifest limits, and oracle strict-subset validation (§5) are
  all checked first; a preflight failure rejects the corpus run with zero
  attempts consumed (C43).
- **Independent oracle approval**: each registered behavioral and
  affected-test oracle is signed over `(task_id, repo_commit, oracle_hash,
  expected_terminal)` by at least one reviewer who is neither the corpus/
  reference-patch author nor an author of the implementation under test. The
  signer identity, public-key fingerprint, signature, and non-tool provenance
  declaration are part of the external registration payload. Missing,
  invalid, or non-independent signatures fail preflight; a hash timestamp
  alone is not oracle truth (C59).
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
refactor, 2 migration, 2 test_selection), each with its exact
`expected_terminal = {verdict, reason_code}` in the strict JSONL and manifest
hash (9 `PASS/null` + 1 named `FAIL/<product-code>` for a known-wrong
reference patch). Aggregate counts never substitute for per-task truth.

**B1 completes only when the runner matches exact expected outcomes AND
survives a mutation suite** that forces every reason code:

- positive mutation: the reference (correct) patch → must yield the pinned
  PASS with all applicable checks exercised (six for `test_selection` tasks);
- `PATH_VIOLATION`: patch touching an out-of-allowlist path → exact code;
- `ORACLE_FAILED`: patch leaving the oracle red → exact code;
- `VERIFICATION_FAILED`: patch that passes the oracle but breaks the
  verification command → exact code;
- `STALE_ROWS`: patch whose index refresh leaves a stale row (injected) →
  exact code;
- `UNSUPPORTED_RELATIONSHIP`: patch justified by a high-confidence
  unsupported relationship (fixture) → exact code;
- `UNKNOWN`: each closed subcode is forced independently, including a
  non-applicable patch (`PATCH_NOT_APPLICABLE`), missing provenance
  (`PROVENANCE_MISSING`), oracle runtime/unexpected exit
  (`ORACLE_EXECUTION_ERROR`), index refresh/query failures, and hunk-boundary
  fixtures (a physical-body hunk at exactly
  `patch_max_lines_per_hunk` is processed; limit+1 is
  `UNKNOWN/PATCH_OVER_BOUND`) → exact verdict/subcode;
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
selection correctness, C26). **The affected-test oracle must be a strict
subset of the fixture's complete suite** — validated at corpus load; a
full-suite or non-existent-path oracle is a registration error that fails
preflight, because a full-suite oracle carries no selection signal and such a
change is not a valid `test_selection` task (C43). With a strict-subset
oracle, running the full suite, no tests, or the wrong subset is always
`TEST_SELECTION_FAILED`, not a pass.

## Phases with visible exit artifacts

| Phase | Scope | Verifiable exit artifact |
|---|---|---|
| **B0** | RFC accepted; strict `BenchmarkRecord` model; 10-task seed corpus; registration registry | `benchmarks/no1_010b/` with 10 tasks; corpus contract tests green (unknown-field rejection, exact per-task terminal state, oracle red-baseline + reason/signature, allowlist semantics, per-class counts) |
| **B1** | Patch-verifier runner complete (all applicable checks + oracle exit-code contract + stale-row queries + mutation suite) | 10/10 pre-registered terminal pairs matched exactly; mutation suite forces every named product reason and every closed UNKNOWN subcode; CI reproduces |
| **B2** | VCSR baseline measurement on pinned versions | `report.json` with VCSR + per-class/per-repo **and per-arm** breakdown (exact task counts and outcomes per client/model/backend — arms are never pooled in the report, C31) + **the reliability metric per arm and overall**: `successful_indexed_trials / all_trials` with exact numerator, denominator, failure classes (infrastructure vs product), and the 99% reliability gate status (C38); the terminal-state → numerator/failure-class mapping is fixed in §3 (C43). The complete registered arm × task × repeat matrix is mandatory; a missing cell blocks B2. The report also emits the paired endpoint's `n11/n10/n01/n00`, effect, exact p-value, frozen thresholds, and admission state. **B2 does not complete unless the 99% reliability threshold is met per arm and overall** — a below-threshold run is recorded but cannot advance to baseline (C39) + provenance; baseline recorded in STATE.md; E0–E3 internal only |
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
