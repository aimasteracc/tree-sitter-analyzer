# Roadmap — Trusted Agent Change Intelligence No.1 Program

- **Status:** active
- **Branch:** `docs/no1-roadmap-governance`
- **Mission:** Become the most trusted local code-change intelligence layer for AI coding agents.
- **North star:** Verified Change Success Rate (VCSR), not feature, language, tool, test, or edge count.
- **Claim policy:** Public language is always bounded to named tools, versions, repositories, models, dates, and evidence levels. E0–E3 emit no quantitative competitive wording; E4 permits only the exact admitted bounded sentence, never an unqualified "No.1" claim.

## 1. Strategic position

TSA will win a narrow category before expanding: **local, polyglot, evidence-backed change intelligence for autonomous coding agents**.

The product promise is:

> Understand the relevant code, plan a safe change, and verify the result with fresh, auditable evidence. When evidence is insufficient, say `unknown` rather than guess.

The default user journey becomes three task outcomes:

1. `understand(task)` — entry points, relevant source, relationships, freshness, evidence.
2. `plan_change(task | diff)` — blast radius, constraints, affected tests, unknowns, verification plan.
3. `assess_change(diff)` — static structural/classification/constraint findings with explicit freshness and runtime `not_run`; it does not claim runtime verification.

Existing MCP/CLI primitives remain the implementation substrate and compatibility surface. New top-level UX must compose them rather than duplicate engines.

## 2. Baseline

Baseline captured by dogfooding the current repository. The values below were
measured on 2026-08-08 with
`uv run python -m tree_sitter_analyzer --project-health --format json`. The
executable baseline is bound to `origin/develop` commit
`c0b59748f7b2885b27e9fb810ff9822b9906426f`; this branch changes documentation
only. Re-measure rather than carrying these values forward after that source
commit changes.


| Signal | Current state |
|---|---|
| Project-health scope | 1,985 analyzed files |
| Health | 1,602 A / 347 B / 32 C / 4 D / 0 F; verdict `REVIEW`; weakest dimension `structure` |
| Constraints | `SAFE` |
| Resolver registry xref | `register_language`: 15 callers, 1 callee |
| Main technical moat | conservative language-gated resolution and edit-safety loop |
| Main product risk | broad surface and inconsistent claims/support-language wording |
| Main adoption risk | install/runtime friction and low external validation |
| Main execution risk | benchmark complexity hotspots and maintainer concentration |
| Observed onboarding failure | project requires uv `>=0.11.0`; local uv `0.10.8` blocks normal `uv run` |

## 3. Scorecard and gates

### North star

**Verified Change Success Rate (VCSR)** is the percentage of pre-registered agent tasks that:

- modify only allowed paths;
- satisfy exact behavioral oracles;
- pass the declared verification command;
- leave no stale symbol or edge rows;
- contain no high-confidence unsupported relationship used to justify the change.

### Quality gates

| Dimension | Gate |
|---|---|
| Change outcome | VCSR reported by repository and task class; no weighted score may hide a regression |
| Reliability | successful indexed trials >=99%; all timeouts/product failures remain in denominator |
| Citations | deterministic citation-location validity >=99% |
| Trust | exact stale-row and stale-edge counts = 0 for incremental fixtures |
| Quality | RFC-0021 non-inferiority gate passes before cost/latency claims |
| Efficiency win | paired 95% CI upper bound for cost or latency ratio <=0.80 under RFC-0021 rules |
| Onboarding | fresh-machine install -> first trusted answer succeeds >=95%, then ratchets to >=99% |
| Warm query | publish P50/P95 by repository size; no headline without reproducible artifact |
| Community | at least 3 active external maintainers/reviewers before enterprise-support claims |
| Evidence | E2 internal complete matrix -> E3 second machine -> E4 public independent reproduction |

## 4. Operating rules

### Stop

- Stop treating new flags, actions, scaffolds, languages, diagrams, or test count as strategic progress.
- Stop adding public surfaces when an existing facade can compose the outcome.
- Stop copying measured numbers manually into multiple documents.
- Stop publishing broad leadership wording before the evidence ladder permits it.
- Stop model-backed benchmark spend until model-free setup, provenance, budget, isolation, and replay gates pass.

### Continue

- Continue local-first operation, project-root security, MCP/CLI parity, TOON for MCP, JSON for CLI, and fail-closed benchmarks.
- Continue conservative resolution: a visible `unknown` is safer than a confident unsupported edge.
- Continue dogfooding before edits and following the emitted verification command after edits.
- Continue exact behavioral tests, but prefer realistic corpus failures over coverage-only growth.

### Start

- Start task-outcome APIs, edge evidence/provenance, claim generation, install-funnel qualification, and external reproduction.
- Start deleting or demoting low-use public surface based on explicit compatibility policy.
- Start publishing reproducible SLO curves for install, index, warm query, incremental refresh, and task outcomes.
- Start recruiting independent oracle reviewers and resolver owners.

## 5. Twelve-month roadmap

### Wave 0 — Program control, bounded E0 canary, and E1 qualification (days 0-30)

**Outcome:** one source of truth, a bounded E0 production-canary path, and separately qualified measurable onboarding.

- Land this roadmap, task ledger, ownership model, and claim policy.
- Complete the NO1-002C/002D production-canary operator path without weakening trust gates; its real bounded run remains E0 operational evidence and cannot advance the RFC-0021 ladder.
- Qualify a separate reproducible install/smoke result before assigning E1 or unlocking E2 setup.
- Create a machine-readable claim registry bound to benchmark artifact digests.
- Generate one canonical language support-depth matrix from code/contract evidence.
- Add a clean-machine install qualification that covers an installed-but-outdated uv.
- Freeze the three-task API and edge-evidence contracts as reviewed RFCs.

**Exit gate:** the bounded E0 canary is replayable, a distinct E1 install/smoke qualification is reproducible, claims have one source, install-to-first-answer is measured, and no new unbounded claim is possible.

### Wave 1 — Complete internal evidence and minimum product path (days 31-90)

**Outcome:** RFC-0021 E2 evidence and a usable three-task prototype.

- Finish manifest-bound setup validation for all seven pinned repositories and required arms.
- Run the complete pre-registered warm matrix only after setup and budget gates pass.
- Qualify one second current indexed competitor at the install/conformance boundary; it is not an RFC-0021 v1 matrix arm. Any comparative inclusion requires a separately reviewed v2 experiment with a re-frozen manifest, matrix cardinality, fairness policy, and endpoints; unavailability remains `NOT_EVALUATED`.
- Implement `understand`, `plan_change`, and `assess_change` as orchestration over existing primitives.
- Attach freshness, evidence, resolution kind, and confidence policy to task-level conclusions.
- Split optional heavyweight dependencies from the default install path.
- Publish reproducible cold-start, index, warm-query, incremental, token, and tool-call baselines.

**Exit gate:** complete E2 artifacts; task APIs pass exact contract tests; fresh install succeeds >=95%; no quality regression is hidden by efficiency.

### Wave 2 — Agent change outcomes (months 4-6)

**Outcome:** prove that better graph evidence produces better code changes.

- Add pre-registered bugfix, refactor, API migration, and affected-test tasks.
- Measure VCSR across at least three agent clients/models without pooling backends.
- Make the three-task API the recommended agent path while retaining facade compatibility.
- Harden multi-agent/worktree freshness, concurrent reads, serialized writes, and crash recovery.
- Ship deep integrations for Claude Code, Cursor, and Codex with doctor and lifecycle checks.
- Publish at least three external design-partner case studies, including failures.

**Exit gate:** task-outcome benchmark is reproducible; ten external teams have completed real workflows; retained usage grows for two consecutive cohorts.

### Wave 3 — Independent reproduction and ecosystem (months 7-9)

**Outcome:** E3 evidence and contribution leverage beyond one maintainer.

- Reproduce the complete primary conclusion on a clean independent machine.
- Complete independent blind review and disclose disagreements/adjudications.
- Stabilize the resolver/framework SDK and adversarial conformance suite.
- Certify community plugins only when extraction, resolution, incremental, and miswire gates pass.
- Publish signed artifacts, SBOM/provenance, compatibility policy, and an LTS line.

**Exit gate:** E3 reached; at least three external maintainers/reviewers own defined areas; two external plugins pass certification.

### Wave 4 — Public bounded leadership and team product (months 10-12)

**Outcome:** E4 bounded leadership evidence and a sustainable adoption/business layer.

- Publish raw artifacts, exact commands, checksums, failures, versions, and bounded conclusions.
- Obtain third-party reproduction before using "best among tested tools" wording.
- Ship optional team capabilities: shared index, policy distribution, audit trail, private plugins, RBAC/SSO, and support SLO.
- Keep correctness and evidence protocols open; monetize collaboration, governance, and operations.
- Decide expansion only from task outcomes and retained-user evidence.

**Exit gate:** E4 reached for a named benchmark version, ten public production cases, and a credible multi-maintainer support model.

## 6. Team topology

The program uses role-based agents with isolated worktrees for implementation. Per `LOOP.md`, no more than two L2 agents run concurrently.

| Role | Accountability | Initial owner |
|---|---|---|
| Program Orchestrator | critical path, dependency gates, final integration, GitFlow | parent agent |
| Trust & Benchmark Lead | RFC-0021, NO1-002C/D, provenance, replay, claim ladder | `no1-canary-implementer` (NO1-003B) |
| Product/API Lead | three-task contracts, compatibility, Agent UX | RFC-0022/0023 drafts complete; next NO1-010A through their stated gates |
| Runtime Lead | install, packaging, indexing SLO, concurrency | NO1-006A native qualification complete at protected run `31272226364` |
| Evidence/Claims Lead | claim registry, support matrix, generated docs | NO1-004A/B and NO1-005A merged; future E4 admission remains external |
| Independent Reviewer | oracle signatures, blind review, E3 reproduction | human/external agent; cannot be benchmark author |
| Community/GTM Lead | integrations, design partners, case studies | human-led with research agents |

Agents may prepare artifacts and code, but these gates remain human-controlled: model spend authorization, independent oracle signature, production judge acceptance, public claims, release, and merge.

## 7. First 90-day task ledger

### P0 — active/next

| ID | Task | Owner role | Depends on | Acceptance and verification |
|---|---|---|---|---|
| NO1-003A | Program roadmap and task ledger | Program Orchestrator | none | roadmap reviewed; branch obeys GitFlow; `--change-impact` reports exact verification |
| NO1-003B | Production canary operator runbook and offline rehearsal | Trust Lead | NO1-002D | fixture remains `NOT_EVALUATED`; production callbacks only after signed attestation + judge ACCEPT; focused production-trust tests |
| NO1-003D | Implement and qualify the production dispatcher/admission boundary | Runtime + Trust Leads | NO1-003B | separately reviewed dispatcher consumes the qualified bound spec exactly once, preserves kill switch/budget/attestation/judge gates, and performs no model call during qualification |
| NO1-003C | Execute one real bounded E0 Gin production canary | Human Operator + Trust Lead | NO1-003D, NO1-008A | immutable complete bundle, budget ledger, policy audit, and replay; callbacks remain forbidden until model-free setup, signed attestation, human budget, and judge gates pass; the admitted manifest remains E0 and cannot unlock E1/E2 or public/No.1 wording |
| NO1-004A | Claim registry schema and validator (complete) | Evidence Lead | NO1-003A | every quantitative README marketing claim is registry-generated with names/versions, metric/unit/numerator/denominator, benchmark/date/corpus/repo commit, repository set, model/backend, evidence level, and an independently reproduced digest admitted by the code-owned trust root; stale/mixed/self-attested claims fail closed |
| NO1-004B | Generated claim/support snippets (complete) | Evidence Lead | NO1-004A, NO1-005A | deterministic claim marker plus whole-README coverage rejects manual quantitative marketing; command/version data and the independent language inventory generator are excluded |
| NO1-005A | Canonical language support-depth inventory | Product Lead | none | pipeline registration dimensions derived from executable registries; cross-file E2E remains tri-state and requires positive fixtures |
| NO1-006A | Fresh-install qualification harness (complete) | Runtime Lead | none | one exact wheel passes native macOS/Linux/Windows package-to-MCP-first-answer qualification and independent protected-`develop` attestation |
| NO1-006B | Default dependency split RFC and measured baseline | Runtime Lead | NO1-006A | wheel/download/startup/dependency counts measured before design; no big-bang rewrite |
| NO1-007A | RFC: `understand/plan_change/assess_change` | Product/API Lead | NO1-003A | fixed schemas, compatibility map, evidence fields, no duplicate analysis engine |
| NO1-007B | RFC: edge evidence/confidence/freshness | Product/API + Trust | NO1-007A | confidence semantics calibrated; `unknown` never promoted without evidence |

Integration chronology: NO1-004A/B and NO1-007A/B were implemented against the
program-policy draft and merged before this governance PR. That parallel merge
history does not mark NO1-003A complete; NO1-003A closes only when PR #1238 itself
lands on `develop`.

NO1-004A/004B closure is deliberately a zero-public-claim state: the only
checked-in record is blocked E0 and emits no wording. Unsupported historical
benchmark/performance numbers were removed from the main README. A future
number can appear there only as the exact deterministic E4 sentence generated
from a digest-verified artifact; E0–E3 and blocked records cannot emit text.

### P1 — after P0 gates

| ID | Task | Owner role | Depends on | Acceptance and verification |
|---|---|---|---|---|
| NO1-008A | Seven-repository model-free setup qualification | Benchmark Lead | separately recorded RFC-0021 E1 qualification | exact source partitions, zero unallowed parse errors, pinned tool/repo fingerprints, and no model callbacks; any failure blocks NO1-003C and all model-backed phases |
| NO1-008B | E2 warm confirmatory matrix | Benchmark Lead + Human Operator | NO1-008A | exact expected cells, five repeats, complete evaluations, failures retained |
| NO1-009A | Select and qualify second indexed competitor | Trust Lead + Independent Reviewer | NO1-003A | frozen version/install/conformance path; unavailable arm is `NOT_EVALUATED`, never a TSA win; it is not added to the frozen RFC-0021 v1 matrix without a separately reviewed v2 experiment and recomputed cells |
| NO1-010A | Three-task prototype | Product/API Lead | NO1-007A/B | MCP/CLI parity or explicit internal-only status; exact contract tests; real CLI smoke |
| NO1-010B | Agent change-outcome benchmark RFC | Benchmark + Product | NO1-008B, NO1-010A | bugfix/refactor/migration/test-selection oracles; VCSR primary endpoint |
| NO1-011A | Lightweight default install implementation | Runtime Lead | NO1-006B | compatibility preserved; fresh-install success and startup improve on all axes |
| NO1-012A | Performance/SLO artifact pipeline | Runtime Lead | NO1-006A | byte-stable reports; P50/P95 by repo size; no benchmark-only pytest misuse |
| NO1-013A | Three-client integration qualification | Community/GTM | NO1-010A | Claude Code, Cursor, Codex install/index/query/uninstall scenarios pass |

## 8. Dependency graph

```text
NO1-003A
  ├─ NO1-004A ─ NO1-004B
  ├─ NO1-007A ─ NO1-007B ─ NO1-010A
  ├─ NO1-005A ─ NO1-004B
  └─ NO1-009A

NO1-002D ─ NO1-003B ─ NO1-003D (dispatcher; no model call)
[separate RFC-0021 E1 qualification] ─ NO1-008A (model-free setup) ─ NO1-008B ─ NO1-010B
NO1-003D + NO1-008A ─ NO1-003C (bounded E0 canary; both are required)

NO1-006A ─ NO1-006B ─ NO1-011A
         └─ NO1-012A

NO1-010A ─ NO1-010B
         └─ NO1-013A
```

## 9. Definition of done for every implementation task

1. Run TSA change-impact before edits and record the affected surface.
2. Use focused TSA navigation/health/safety queries instead of blind scanning.
3. Work on a GitFlow-compliant branch/worktree; never push directly to `develop` or `main`.
4. Add exact behavioral tests to existing test files unless the subsystem is genuinely new.
5. Run post-edit change-impact and its reported verification command.
6. For Python changes, run focused coverage and the patch-coverage gate.
7. Update codemaps in the same commit when a guarded registry changes.
8. Preserve locked defaults: MCP TOON, CLI JSON, stderr diagnostics, project-root behavior.
9. Record failures and unfavorable benchmark results; never weaken a gate to create a headline.
10. Produce a concise dogfood feedback record for project memory or the final handoff.

## 10. Current execution order

NO1-006A closed on protected `develop` commit `58bd2b982f48abd4059a646657e7421da658a776` in [workflow run `31272226364`](https://github.com/aimasteracc/tree-sitter-analyzer/actions/runs/31272226364). One wheel (`sha256:c1cb3520542fd14dad60ddec55dfac6afbdaa424e7a4a39d875be1801d98f9e8`) passed native Linux, macOS, and Windows package-to-MCP-first-answer axes; the no-checkout trusted job independently verified the byte-bound aggregate (`sha256:7ecae9be0e0bbc6bd54f319aff2eee97e34774888fb0820abd759eee4f5551e2`) and GitHub attestations for both subjects. This closes only the native-install task: it does not upgrade canary, benchmark, comparison, or public-claim evidence.

1. Establish and record a distinct reproducible RFC-0021 E1 install/smoke qualification, then complete NO1-008A's model-free seven-repository setup; any setup failure blocks every model-backed phase.
2. Implement and independently review NO1-003D's production dispatcher without invoking a model.
3. Only after NO1-003D, NO1-008A, human budget, signed attestation, and judge gates pass, execute NO1-003C as a bounded E0 canary; retain failures and do not relabel it E1.
4. Qualify NO1-009A only at the second competitor's install/conformance boundary; adding it to comparisons requires a separately reviewed RFC-0021 v2 experiment.
5. Proceed with NO1-006B/010A/012A only through their ledger prerequisites and exact native/contract qualification gates; E0–E3 cannot emit public leadership wording.
