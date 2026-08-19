# Loop State — tree-sitter-analyzer

Last run: 2026-08-16 (P0.4 strace adapter-route certification merged, #1297)

## NO1-010B first VCSR measurement attempt (2026-08-20) — E0, internal only

**Result: VCSR is `NOT_PRODUCED`. There is no first VCSR number, and RFC-0026
says there cannot be one from a model-free run.** Recorded here with full
provenance so the absence is auditable, not re-discovered.

- **Artifact:** `benchmarks/no1_010b/report.json`
  (`schema = no1-010b/report/1`, `run_status = REJECTED_AT_PREFLIGHT`).
- **Reproduce:**
  `uv run python -m tree_sitter_analyzer.no1_010b --corpus benchmarks/no1_010b/corpus.jsonl --report benchmarks/no1_010b/report.json`
- **Provenance:** analyzer commit `9137b39b` (`origin/develop`), analyzer
  version `1.29.0`, Python 3.13.5, Windows-11-10.0.26200-SP0,
  corpus sha256 `2957546f9b42a1b19bc15d7e567381b0c39fd14456800ae65732b05f2d2bdb8c`,
  per-oracle sha256 in the report. **Model calls: 0. Model spend: none.**
- **Measured VCSR:** `state = NOT_PRODUCED`, `value = null`,
  numerator/denominator `0/0`, per-class/per-repo/per-arm all empty.
  `0/0` is deliberately not reported as `0%` — no attempt reached a verdict, so
  the endpoint has no value and a `0.0` would be a fabricated measurement.
- **Reliability metric** (`successful_indexed_trials / all_trials`):
  `0 / 0`, ratio `null`, threshold `0.99`, `gate_status = NOT_EVALUATED`;
  failure classes `product = 0`, `infrastructure = 0` (zero retained attempts).
- **B2 status: BLOCKED — did not complete.** Per C39 a run that does not meet
  the 99% reliability gate per arm and overall cannot advance to baseline; this
  run never reached the gate because preflight rejected it with **0 attempts
  consumed** (RFC-0026 §4).

### Why a model-free VCSR is undefined, not merely unmeasured

The block is at the **spec** level, not the implementation level. RFC-0026 §2
channel 1 designates the supplied-patch route as "the validation channel, **not
the agent measurement**", and channel 2 states that at least three distinct,
non-pooled client/model arms are "a **mandatory B2 completion gate** — a VCSR
baseline produced only from supplied reference patches does not satisfy
NO1-010B". Criterion 5 is additionally `UNKNOWN` for any supplied patch without
a provenance transcript. So even a perfectly executed model-free reference run
would not be a VCSR baseline. **Producing the first VCSR number requires a
human budget decision authorizing model spend** (ROADMAP: model spend and
independent-judge gates are human-controlled; NO1-008A is a precondition and
NO1-003C is NO-GO).

### Gates the report records as `NOT_SATISFIED`

| Gate | Constraint | Why |
|---|---|---|
| `patch_verifier_runner` | RFC-0026 B1 | no patch application, isolated worktree, read-only candidate mount, write journal, stale-row projection comparison, or unsupported-relationship evidence check exists |
| `oracle_red_baseline` | C42/C43 | `oracle.py` returns `UNKNOWN/SANDBOX_FAILURE` for every parsed declaration by design; only B1's trusted wrapper behind a kernel-enforced sandbox may authorize a verdict |
| `fixture_commit_pinning` | RFC-0026 §1 | in-tree fixtures carry the RFC's all-zero placeholder `repo_commit`, so drift cannot fail closed |
| `external_registration_anchor` | C14/C27 | a git-committed file is explicitly insufficient for pre-execution ordering |
| `independent_oracle_signature` | C59 | no reviewer signature over `(task_id, repo_commit, oracle_hash, expected_terminal)` exists |
| `three_non_pooled_agent_arms` | C31 / §2 | mandatory B2 gate; needs authorized model spend |
| `paired_control_arms` | C28/C37/C56 | needs evidence-enabled/disabled arm pairs and a complete matrix |

### What did land (B0 exit artifact, now real committed data)

- **10-task seed corpus** at `benchmarks/no1_010b/corpus.jsonl`, loaded by the
  existing strict `load_corpus_records`: 4 bugfix / 2 refactor / 2 migration /
  2 test_selection, 9 `PASS/null` + 1 `FAIL/VERIFICATION_FAILED`, across 3
  pinned fixture repos (dispatch_app 4, orders_service 4, config_loader 2).
- **10 self-contained oracles** (`benchmarks/no1_010b/oracles/`), each verified
  red on its unmodified fixture with the exact registered
  `oracle_baseline_reason` token; each fixture suite is green
  (3 / 4 / 3 tests).
- **Internal-only entry point** `python -m tree_sitter_analyzer.no1_010b`
  (no MCP facade, no CLI flag, no console script, no codemap surface), guarded
  by `tests/contracts/test_no1_010b_internal_only_contract.py`.
- **Claim policy:** E0. No public wording emitted, no README touched, no badge,
  nothing admitted to the claim registry.
- **Not landed (B1 scope, deliberately):** reference/mutation patches. The
  mutation suite that forces every reason code belongs to B1 per §5, and
  shipping patches that no sandboxed verifier can score would be theatre.

## NO1-010A completion record (2026-08-16)

- **NO1-010A (three-task prototype) implemented and MERGED** (#1290 → develop,
  2026-08-16): `understand` / `plan_change` / `assess_change` execute the
  pinned RFC-0022 route table end-to-end. All 14 first-round Codex review
  findings fixed in-branch (evidence budget, echo validation, real wire
  vocabularies, NO_CONFIG diff-only provenance, truncation propagation,
  ownership degradation, cleanup wall-time exclusion, strict decoder,
  harness one-of, etc.) with regression tests; CI + codecov/patch green.
- **NO1-010A follow-up merged (2026-08-16, three PRs)**: #1291 actionable
  outputs (`next_step` unlock/re-index/budget/review hints + compact
  deterministic `agent_summary`) + adapter-boundary wire contract fixtures
  pinning the real primitive shapes; #1292 harness corpus/request-json
  modes (strict JSON decoding, project-boundary input validation, budget
  ceilings honored, option-presence exclusivity); #1293 **P0.4 zero-write
  source-generation oracle first slice** — `oracle_generation_readonly`
  reproduces the frozen oracle's framing byte-for-byte with zero filesystem
  writes (own bounded zero-write git runner in `git_readonly.py`,
  in-memory index binary parser, assume-unchanged/skip-worktree hint
  semantics, diff.orderFile fail-closed, module split). All Codex review
  findings on all three PRs triaged and fixed with regression tests; CI +
  codecov/patch green.
- **P0.4 materialization half MERGED (#1295 → develop, 2026-08-16)**:
  `capture_payload_readonly` reproduces the frozen P0.2 payload (records,
  old/new bytes, normalized patch) entirely in memory — tracked rows from
  the live index via the zero-write runner, untracked new-file sections via
  the byte-identical `git diff --no-index` format, content-identical
  worktree moves as R100 renames (modified moves stay D+A, documented),
  conversion-active repos (autocrlf/eol/working-tree-encoding/ident) fail
  closed with `DIFF_SNAPSHOT_UNSUPPORTED_CONVERSION`. `edit.impact(
  access_mode="read_existing")` is now the in-memory producer on Linux with
  the exact P0.4 access-evidence fields; other OSes keep the stable
  unsupported result. All 12 Codex findings (5 P1, 7 P2) fixed with
  regression tests — including acquire/validate_publish revalidation via
  the read-only oracle (the frozen runner wrote temp order files on every
  revalidation), extended-flag index parsing (intent-to-add no longer
  misclassified as hinted), C-unquoted patch-section keys, deadline-bounded
  unique exact-rename pairing, gitlink probe boundary validation, and the
  per-test budget fixture fix. Differential golden corpus proves
  byte-equality with the frozen backend across 20+ state classes incl.
  gitlinks; CI + codecov/patch green on all axes.
- **P0.4 remaining work**: the Linux strace axis adapter-route case (the
  monitor infra exists; a case that runs the real read-existing capture is
  the next slice), then the consumers' read_existing backends
  (`ast_diff`/`classify`/`constraints` still return
  `READ_EXISTING_AUTHORITY_UNCERTIFIED`); object-directory-free HEAD
  traversal (loose/pack object reading) is the documented next slice after
  that; macOS authority remains a separate RFC-tracked item.
  - `task/router.py` — fixed route-table executor: sequential primitive calls
    through an injected `PrimitiveExecutor`, budget/deadline admission with
    exact `deadline_overrun_ms` reporting, constraints-slot reservation before
    fan-out, primitive-token echo comparison (`SOURCE_GENERATION_MISMATCH`
    stop), P0.4 access-evidence branching (`access_state`/`access_reason`,
    never `success` alone — verified live on macOS where the read-existing
    authority honestly returns `READ_EXISTING_AUTHORITY_UNCERTIFIED`),
    table-driven plan-steps projection, evidence minting,
    provenance/freshness/unknowns records, `edit.release_snapshot` cleanup in
    an outer `finally` with fixed accounting, stable error codes.
  - `task/truth_table.py` — the full static verification truth table (ordered
    first-match-wins; truncation overrides fresh success; malformed overrides
    freshness; `degrade()`; severity aggregation; zero-contribution WARN;
    partial+SAFE→WARN).
  - `task/projection.py` — table-driven plan_steps (group order, within-group
    `(path, symbol, locator)` sort with nulls first, 1-based ordinals,
    `evidence_ids` contain only that fragment's ID; `assess_change` keeps
    `plan_steps=[]`).
  - `task/models.py` + `task/serializers.py` — full `task-outcome/v1` fixed
    wire (`success/operation/subject/claims/artifacts/provenance/freshness/
    unknowns/errors/budget/truncation/next_step/agent_summary`); serialized
    byte pins re-pinned (JSON 961 / TOON 820). Task text is never frozen
    (`TASK_TEXT_OMITTED` projection + request hashes; secret-canary tests).
  - `task_harness.py` — internal experiment bridge over the real same-process
    MCP adapters + `python -m tree_sitter_analyzer.task_harness` CLI smoke
    entry. Explicitly internal-only: no MCP facade, CLI flag, or codemap
    surface (guarded by `tests/contracts/test_task_internal_only_contract.py`).
  - Verified: quick gate 1992 passed; ruff + mypy clean; patch-coverage gate
    no added executable misses; real CLI smoke on an indexed fixture repo —
    fresh oracle + complete rows on `--full-index`, honest fail-closed
    `ACCESS_UNAVAILABLE` where the P0.4 zero-write authority is not certified
    (macOS). The full impact→constraints→ast_diff→classify happy path runs on
    the Linux CI axis once `feature/rfc0022-linux-write-authority` lands.
  - Follow-ups: NO1-010B (agent change-outcome benchmark RFC) is the next
    ledger task after NO1-010A merges.

## P0.4 strace certification record (2026-08-16, PR #1297)

- **Objective:** certify the P0.4 read-existing adapter route on the pinned
  Linux strace authority so the task layer runs end-to-end.
- **Five root causes fixed in #1297:**
  1. `split_arguments` treated strace's resumption placeholder
     (`restart_syscall(<... resuming interrupted futex ...>)`) as a
     descriptor and died on the embedded angles → opaque `<...`/`>...` skip.
  2. Git subprocesses call `setsid` (via `start_new_session`) → added to the
     policy `safe_syscalls`.
  3. The git runner opens `/dev/null` O_RDWR (`subprocess.DEVNULL`) and the
     classifier flagged all 698 as `write_capable_open`; a char device is
     not a filesystem file → policy `nonfilesystem_device_markers ["<char "]`,
     block devices stay fail-closed; policy digest re-pinned.
  4. `classify_calls` was O(transitions × calls) (~4 min on the 119k-call
     git trace): `reject_ambiguous_state_transition` now scans a start-sorted
     bisect index plus every resumed (interrupted) call — provably equivalent
     to the full scan (locked by a double-scan contract test) — ~12.5s.
  5. Live test debug raw-trace dump removed so the artifact manifest stays
     exact.
- **Verified:** local replay 119,047 calls / 0 violations / 12.5s; strace
  workflow green on every push; pinned stdout hash unchanged (`78474981…`);
  quick gate 1997 passed.
- **Codex review (9 comments) triaged, all fixed:** P1 — the frozen
  constraint route in `read_existing` mode now requires and acquires the
  caller-reserved index capability (`CONSTRAINT_INDEX_CAPABILITY_REQUIRED`
  when absent) instead of minting a fresh lease. P2 — acquired diff
  provenance preserved on every post-acquisition failure; workflow path
  filters include the certified backends; adapter route emits a stable
  3-tuple and releases the route lease in `finally`; read-existing evidence
  attached to raw JSON before TOON formatting so all formats carry
  `access_mode`/`access_state`/`access_reason`/`source_snapshots`; adapter
  evidence stored under the uploaded artifact root; snapshot-route test pins
  exact INFO verdicts.
- **Post-review CI fixes:** wire-owner `action_version` on frozen
  acquire/publish error envelopes (Linux path); `fail()` no longer re-raises
  when the consumer snapshot read itself fails; pre-certification consumer
  test platform-gated; real-git budget tests marked `slow_ok` (pass 2-3s
  locally but brush past the 5s unit budget under 4-way xdist contention).
- **Follow-ups:** harness corpus runs the diff route for real on Linux CI;
  nav.context / edit.safe (P0.1) `read_existing` backends still UNCERTIFIED;
  object-directory-free HEAD traversal is the next slice after the
  consumers; macOS write authority is a separate RFC-tracked item.

## Takeover record (2026-08-15)

- Branch `feature/no1-agent-program` was stale (73 behind origin/develop; its 6
  local commits were superseded by merged PRs) and was reset to origin/develop.
- PR #1269 (RFC-0023 edge-evidence validator, Phase A) merged with 17 Codex P2
  review findings outstanding. A merged PR does not exempt its review: all 17
  were triaged against merged code; 2 were already fixed in the merge (reason
  priority, request floats), 15 were fixed in follow-up PR #1271 (review gates:
  ID recompute, complete snapshot tuple, invocation owners, diagnostic
  projection, stale zero-ID diagnostics, projection closure, truncation object,
  truncated positives, zero-ID classification, provenance linkage, proposed
  source, collection per-item, duplicate identities, locator equality,
  type-safe classifier).
- Codex re-reviewed #1271 and posted 8 more findings (5 P1, 3 P2); all fixed in
  a second commit (bb83a172): diagnostic observation locator, duplicate
  pointers, per-record contradiction IDs, raw-freshness-derived stale state,
  zero-ID truncation, one-to-one invocation bindings, unreferenced provenance,
  missing/partial snapshot precedence.
- **All four follow-up PRs merged to develop on 2026-08-15:** #1271 (review
  gates), #1272 (takeover record), #1270 (CI fast suite — `-q` logging cut the
  coverage axis 608s→511s, per-step timeouts, locked-contract restorations),
  #1273 (removed a T-1 duplicate test file; quick gate unchanged at 1992).
- Dogfood finding: the 8-9 min CI coverage axis is dominated by 25k tests on
  4-vCPU runners (local 10-core equivalent: ~35s), not by test code. 93
  T-1-banned-name test files (`*_coverage*`/`_comprehensive*`/`_edge_cases*`/
  `_extended*`/`_optimized*`, 2015 tests) are real duplication debt from the
  coverage-chasing era but are NOT the time bottleneck (~10s); bulk removal
  was deliberately rejected as high-risk/low-ROI. #1273 is the one-file proof
  of the merge path.
- Known pre-existing CI issue (NOT caused by this work): develop CI has failed
  repeatedly on Windows 3.12/3.13 with the same constraint/snapshot tests
  (test_constraint_check_*, portable_snapshot, index_sync) before and after
  these merges. Ubuntu/macOS/Windows-3.11 axes are green. Separate fix
  required.

## Mission

**Become the most trusted local code-change intelligence layer for AI coding agents.**

North star: **Verified Change Success Rate (VCSR)**. Feature, language, tool,
test, edge, download, and star counts are supporting signals, not the objective.
Public leadership claims remain bounded by the RFC-0021 evidence ladder. E0–E3
emit no public claim, and an operational E0 canary cannot be promoted to E1.

Key pillars:
1. **Trust evidence** — conservative resolution, provenance, freshness, reproducible Agent-change outcomes
2. **Task UX** — understand → plan_change → assess_change over the existing primitives
3. **Runtime reliability** — low-friction install, fast index/query/refresh, multi-agent safety
4. **Independent adoption** — E2/E3/E4 evidence, integrations, external maintainers, real cases

Active roadmap: [`rfcs/ROADMAP-no1-agent-trust.md`](rfcs/ROADMAP-no1-agent-trust.md).

## Active No.1 Sprint

- **NO1-003A (integration condition):** roadmap, team topology, evidence policy, and 90-day ledger are implemented in PR #1238; completion is established only when that PR merges to `develop`
- [x] **NO1-003B:** production-canary operator runbook and offline rehearsal (E0; real canary remains NO-GO)
- [ ] **NO1-003D:** implement and independently qualify the production dispatcher/admission boundary without a model call
- [ ] **NO1-003C:** execute one real bounded E0 Gin production canary only after NO1-003D, model-free NO1-008A setup, signed attestation, human budget, and judge gates pass; it cannot unlock E1/E2 or public wording
- [x] **NO1-006A:** `refs/heads/develop` run `31288611024`, attempt `1`, qualified the exact-wheel package-to-MCP path on native Linux/macOS/Windows plus real outdated-uv fail-closed/manual content-bound recovery on Linux/macOS; Windows recovery remains honestly `NOT_APPLICABLE_NO_NATIVE_INSTALLER`, mutable automatic bootstrap remains unqualified, and durable evidence is preserved under `rfcs/evidence/no1-006a/`
- [ ] **NO1-008A:** after a separate reproducible RFC-0021 E1 qualification, complete the seven-repository model-free setup; any failure blocks NO1-003C and every model-backed phase
- [x] **NO1-004A:** claim registry is the fail-closed control plane; arbitrary wording is schema-invalid, E0–E3 emit nothing, and E4 requires a context-bound benchmark plus independent reproduction whose exact digest is admitted by the code-owned trust root (empty by default) before fixed public wording can be emitted
- [x] **NO1-004B:** the English README has a deterministic claim marker and conservative whole-document policy gate; unsupported quantitative marketing was removed from all three public READMEs, and the blocked E0 seed honestly generates no claim
- [x] **NO1-005A:** generated 10-dimension language pipeline inventory; cross-file E2E remains `verified=0`, with 13 `unknown`
- [x] **NO1-007A:** draft RFC for understand / plan_change / assess_change completed; Phase A internal implementation is gated by read-only snapshot Phase 0, while only public ninth-facade registration is gated by the menu experiment
- [x] **NO1-007B:** RFC-0023 edge evidence/confidence/freshness draft with strict schema, closed golden fixtures, and an E0 denial corpus for a future semantic validator
- [x] **NO1-010A:** three-task prototype (`understand`/`plan_change`/`assess_change`) implemented as the RFC-0022 Phase A internal-only router + harness; explicit internal-only status, exact contract tests, real CLI smoke (see completion record above)
- [ ] **NO1-010B:** RFC-0026 change-outcome benchmark — B0 landed (committed 10-task corpus + oracles + internal `python -m` entry point); B1 patch verifier and B2 VCSR baseline are BLOCKED, and the first VCSR number needs a human model-spend decision (see the 2026-08-20 measurement record above)
- [ ] **NO1-009A:** qualify a second indexed competitor at install/conformance only after NO1-003A; keep an unavailable arm `NOT_EVALUATED`, and require a separately frozen RFC-0021 v2 experiment before comparative inclusion

Execution policy: at most two L2 agents concurrently; implementation agents use
isolated GitFlow worktrees; model spend and independent-judge gates remain human-controlled.

---

## Completed

- [x] **Lua plugin promoted to production** (2026-07-15)
  - `synapse_resolver/languages/lua.py` — moat slot registered (16th resolver)
  - `pyproject.toml` — entry-point + optional dep `tree-sitter-lua>=0.5.0` + all-languages bundle
  - `tests/unit/test_lua_resolver.py` — 13 tests covering moat contract, context gating, registry
  - `lua_plugin/plugin.py` — "Phase 2 extensibility demo" replaced with production docstring
  - `server.json` — "13 languages" updated to "16 languages"

- [x] **RFC-0019: complexity cross-path invariant confirmed GREEN** (2026-07-15)
  - Scalar CC is canonical; `test_complexity_cross_path_invariant.py` passes for Java/JS/TS/Go/Rust
  - Remaining cleanup: `_COMPLEXITY_NODES` table drives `decision_points` breakdown (display-only)

- [x] **Indexing performance uplift** (2026-07-15)
  - `ast_cache.py` `get_conn()`: added PRAGMA cache_size=-65536 (64MB), mmap_size=268435456 (256MB), temp_store=MEMORY
  - `ast_cache.py` `_resolve_worker_count()`: retained the measured 64-file spawn threshold
  - Windows 14-core benchmark (50 files): serial 5.77s vs auto-at-4 9.55s; early spawn was 65% slower and was reverted

- [x] **Degree centrality in KnowledgeGraph** (2026-07-15)
  - `knowledge_graph/builder.py`: `_annotate_centrality()` — degree_in, degree_out, centrality [0,1] per node
  - Every `build()` call annotates nodes; stored in `KnowledgeNode.metadata`
  - Hub nodes are visually larger in the HTML viewer

- [x] **Auto-build KnowledgeGraph after full index** (2026-07-15)
  - `cache/indexer.py` `post_index_backfill()`: keeps SQLite canonical and invalidates stale LadybugDB projections
  - Agents get an up-to-date graph immediately after `tsa index`; no separate `--knowledge-graph-index` step
  - Failure is silently logged (never breaks indexing)

- [x] **Visualization: force-directed HTML viewer** (2026-07-15)
  - `knowledge_graph/html_viewer.py` — full rewrite with spring-electrical force simulation
  - Pre-settles 180 ticks on load; related files cluster together (structural layout)
  - "Physics ON/OFF" toggle; hub nodes glow by centrality; node size = f(kind) + centrality*8
  - Grid-cell approximation for graphs >800 nodes (avoids O(n²) slowdown)

- [x] **Visualization: DOT/Graphviz export** (2026-07-15)
  - `knowledge_graph/exporters.py` `to_dot()` — LOD-aware, focus filter, node colors/shapes by kind
  - MCP `viz` tool: `export_format=dot` → returns DOT string; render with `dot -Tsvg`

- [x] **Visualization: GraphML export** (2026-07-15)
  - `knowledge_graph/exporters.py` `to_graphml()` — Gephi/yEd/Cytoscape compatible XML
  - Nodes carry `degree_in`, `degree_out`, `centrality` attributes
  - MCP `viz` tool: `export_format=graphml` → returns GraphML XML

- [x] **knowledge_graph public API** (2026-07-15)
  - `__init__.py`: `to_dot`, `to_graphml`, `to_graphology`, `to_html_viewer`, `to_mermaid_uml` all exported

---

## Watch List

- [ ] **RFC-0019 decision_points cleanup** (display-only, lower priority)
  - `complexity_heatmap._COMPLEXITY_NODES` drives `decision_points` breakdown (cosmetic only)
  - Next: replace with canonical `decision_node_types(language)` from `languages/shared/`

- [x] **tsa_explore retired** (2026-08-15, RFC-0022 disposition)
  - Prototype deleted from `mcp/`; the umbrella-tool menu experiment
    remains hypothetical (Condition B) per `tool_menu_experiment.py`

- [ ] **CSS/HTML/SQL/YAML/JSON full-index gap** — plugins exist, indexer path not exercised

- [ ] **Pre-existing test failures (not caused by our changes)**
  - `test_introspector.py` — C# grammar node count drift (229 != 239)
  - `test_cli_async.py::test_help_command` — `result.stdout is None`

---

## Historical Comparison Quarantine

The former competitive feature table is removed from active state. Its tool versions,
repository set, date, model/backend, and RFC-0021 evidence level were not recorded, so
its `yes`/`no`/`partial`, language-count, and leadership implications are not admitted
evidence and must not support public wording. Any replacement must be generated from
an artifact admitted by the claim registry under the active roadmap policy.

---
Run log: 2026-07-15 codegraph mission — indexing perf + centrality + auto-KG + force-viz + DOT + GraphML
