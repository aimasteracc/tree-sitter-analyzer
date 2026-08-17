# RFC-0026: NO1-010B Agent Change-Outcome Benchmark (VCSR Primary Endpoint)

- **Status**: draft
- **Author(s)**: @lead-agent
- **Created**: 2026-08-17
- **Last updated**: 2026-08-17
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/task_harness.py` (corpus runner, stdin route)
  - `tree_sitter_analyzer/task/` (router truth-table, edge-evidence)
  - `benchmarks/no1_010b/` (corpus, oracles, runner, report)
  - `tests/unit/task/test_task_harness.py` (exact pins for the runner)
  - `rfcs/ROADMAP-no1-agent-trust.md` (ledger row NO1-010B)

## Summary

A pre-registered, reproducible **agent change-outcome benchmark** whose primary
endpoint is **Verified Change Success Rate (VCSR)** — the north star of
`ROADMAP-no1-agent-trust.md`. The corpus is a pinned set of agent tasks, each
with a repo fixture, a behavioral oracle, an allowed-path set, and a declared
verification command. A task PASSES only when all five VCSR criteria hold;
`unknown` is a first-class outcome, never a pass. The benchmark must fail
closed when evidence is insufficient, exactly like RFC-0021's competitive
benchmark and RFC-0022's fail-closed honesty.

## Motivation

NO1-010A (#1290 + follow-ups) proved the task layer runs end-to-end
(`understand` / `plan_change` / `assess_change` through the internal harness
bridge with exact wire contracts). What is missing is the **measurement**: no
pre-registered corpus and oracle protocol exists that would let us claim
VCSR with evidence. The north-star definition in
`ROADMAP-no1-agent-trust.md` §3 names the five criteria but nothing
operationalizes them into runnable tasks and pass/fail rules.

Concrete pain: today a change is "verified" only by whichever tests an agent
happens to run; there is no corpus where the expected outcome is known a
priori, so regressions in task-layer routing (wrong primitive, dropped
evidence, stale edges) are found by dogfooding, not by CI. The benchmark
closes that gap: **every task's expected outcome is pinned before any arm
runs**, so CI can detect routing/evidence regressions and the VCSR number is
real.

## Detailed design

### 1. Corpus format (JSONL, pre-registered)

One task per line, strict JSON (reuse `task_harness._strict_json_loads`'s
rejection of unknown fields / duplicate keys / non-standard constants):

```json
{
  "id": "no1-010b/0001-bugfix-dispatch-null",
  "repo": "fixtures/dispatch_app",          // pinned fixture repo (git commit)
  "operation": "plan_change",               // understand | plan_change | assess_change
  "task": "dispatch returns None for an unknown route; return a 404 object instead",
  "allowed_paths": ["src/dispatch.py", "tests/"],
  "oracle": "oracles/0001.py",              // exact behavioral oracle (run after the change)
  "verification_command": "uv run pytest tests/ -q",
  "defect": {"file": "src/dispatch.py", "line": 12, "kind": "missing-else"}
}
```

- **repo**: a committed fixture under `benchmarks/no1_010b/fixtures/` (small
  multi-file apps, pinned by git commit; the runner checks out the pinned
  commit and fails closed on drift).
- **oracle**: a deterministic script that asserts the *post-change* behavior.
  It must be pass/fail with a stable exit code and a one-line reason on
  failure; no timers, no network.
- **allowed_paths**: the only paths a compliant change may modify. A change
  touching any other path fails the first VCSR criterion.
- **verification_command**: the command the agent's declared verification must
  satisfy; the harness runs it on the final tree.
- **defect**: the seeded defect metadata (for bugfix tasks) so the oracle is
  *demonstrably* red on the unmodified fixture — a corpus task whose oracle
  passes before the change is a corpus bug, not a pass.

### 2. Harness runner

`benchmarks/no1_010b/runner.py` consumes the corpus and produces
`report.json`:

- `run` phase: for each task, apply the agent's patch (input via
  `task_harness.load_corpus` stdin/`--corpus` route, 8 MiB bound), then:
  1. **paths**: diff vs `allowed_paths` (exact, no glob escape);
  2. **oracle**: run `oracle.py` on the final tree (must be red pre-change);
  3. **verification**: run `verification_command` on the final tree;
  4. **stale rows**: run the analyzer's post-index staleness probe
     (`edge_evidence` rejection family: no stale symbol/edge rows for the
     modified files);
  5. **unsupported relationships**: no high-confidence relationship used to
     justify the change may be unsupported (the RFC-0022 truth-table
     rejection family).
- `score` phase: classify each task PASS / FAIL / UNKNOWN with an exact reason
  code; VCSR = `PASS / corpus_size`. UNKNOWN counts as neither PASS nor FAIL
  for the numerator but is reported separately (fail-closed: a run with any
  UNKNOWN cannot produce a bounded "better-than" claim).

### 3. VCSR criteria ↔ code mapping (exact)

| North-star criterion | Runner check | Reason code |
|---|---|---|
| modify only allowed paths | `paths` check | `PATH_VIOLATION` |
| satisfy exact behavioral oracles | `oracle` check | `ORACLE_FAILED` |
| pass the declared verification command | `verification` check | `VERIFICATION_FAILED` |
| leave no stale symbol or edge rows | staleness probe | `STALE_ROWS` |
| contain no high-confidence unsupported relationship used to justify the change | truth-table rejection family | `UNSUPPORTED_RELATIONSHIP` |
| evidence insufficient (any of the above unavailable, or analyzer fails closed) | runner fail-closed | `UNKNOWN` |

### 4. Baseline protocol and claim policy

- Baseline is measured on a **pinned analyzer version + pinned corpus commit**,
  recorded in `report.json` (`analyzer_version`, `corpus_commit`, `date`,
  `host`), mirroring RFC-0021's provenance discipline.
- E0–E3: internal numbers only, no public competitive wording.
- E4: the only admissible public sentence is the exact bounded form —
  `VCSR = X/Y (Z%) on the pre-registered NO1-010B corpus vN at analyzer
  commit <sha>` — and only when: corpus pre-registered before the run,
  zero UNKNOWNs, CI reproduced the run on the Linux coverage axis.
- The report fails closed (exit non-zero) if any task could not be evaluated
  (missing oracle, repo drift, analyzer crash) — a partially-evaluated corpus
  never yields a claim.

### 5. Seed corpus (implementation deliverable)

The first corpus ships with **10 pre-registered tasks**, all green-repo
fixtures:

- 4 bugfix (missing-else / off-by-one / null-deref / wrong-constant),
- 2 refactor (rename with reference updates; extract-function with call-site
  updates),
- 2 migration (API rename across a package; import-path relocation),
- 2 test-selection (a change that must run exactly the affected subset).

Every oracle is verified **red-on-baseline** in CI (a fixture whose oracle
passes before the change fails the corpus contract test), and every task has
a pinned allowed-path set. The corpus manifest itself is guarded by exact
contract tests (`tests/unit/task/test_no1_010b_corpus.py`): schema, oracle
red-ness, allowed-path validity, no duplicate ids.

### 6. Interaction with existing seams

- The runner drives the task layer through `task_harness.McpPrimitiveExecutor`
  (the same same-process bridge NO1-010A pins); it never imports analyzer
  internals — the `task/` import boundary is preserved.
- The staleness/unsupported checks reuse `task/edge_evidence.py` + the
  RFC-0022 truth-table rejection family (already covered by
  `test_edge_evidence.py` and `test_task_truth_table.py`).
- The harness stdin route (`load_corpus("-")`) is the corpus feed; the 8 MiB
  bound and strict JSON are unchanged.

## Phases with visible exit artifacts

| Phase | Scope | Verifiable exit artifact |
|---|---|---|
| **B0** | RFC accepted; corpus schema + 10-task seed + runner skeleton | `benchmarks/no1_010b/` with 10 tasks; corpus contract tests green (oracle red-ness enforced) |
| **B1** | Runner complete (paths/oracle/verification/staleness/unsupported) + `report.json` | 10/10 tasks evaluate to PASS/FAIL/UNKNOWN with exact reason codes on the seed corpus; CI reproduces |
| **B2** | VCSR baseline measurement on pinned versions | `report.json` with VCSR + provenance; baseline recorded in STATE.md; E0–E3 internal only |
| **B3** | (gated) E4 bounded admission | only when zero UNKNOWNs + CI reproduction + pre-registration, per §4 |

## Alternatives considered

1. **Benchmark the analyzer, not the agent** (compare tool answers on fixed
   prompts): simpler, but measures retrieval, not whether a *change* succeeds —
   the north star is change-outcome. NO1-010B complements RFC-0021, which
   keeps the competitive answer-quality role.
2. **Agent-in-the-loop benchmark** (drive a real LLM agent): closest to
   production, but provider/model variance and cost make it non-reproducible
   in CI. Rejected for the primary endpoint; a future E4-adjacent arm may run
   a pinned model under the same protocol.
3. **No pre-registration** (run tasks, then decide oracles): invalid — the
   north star's evidence level requires oracles decided before the run.
   Rejected.

## Open questions

1. Whether the first 10-task corpus should pin one language (Python) or span
   three (Python + JS + Go) — propose Python-only for B0, expand after B1.
2. Verification-command timeout and isolation (propose: 60 s, subprocess with
   `setsid`, workspace copy — mirroring the strace certification discipline).
3. Whether `report.json` should include a machine-readable per-criterion
   breakdown for the future E4 sentence (propose: yes, always).
