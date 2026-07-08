# SVCD: TSA Self-Verification & Continuous Dogfood System

**Status:** draft  
**Date:** 2026-07-08  
**Author:** Brainstorming session (Claude Opus 4.8 commander)  
**RFC candidate:** Yes — touches CI, claim invariants, and multi-model agent workflow  

---

## Problem Statement

Tree-sitter Analyzer makes several quantitative claims in its README:

- **390× fewer cross-language mis-wires** than name-only resolvers
- **TOON ≤ JSON** token cost on bulk output (~50% smaller)
- **96.3%** call edge classification rate
- **–46%** index speed improvement on large repos
- **5 layers of safety** (safe/guard/constraints/impact/verdicts)
- **13 languages** with full call-graph indexing
- **BM25 ranked** symbol search with relevance scores
- **Reactive push** (RFC-0001) as a differentiator

**The core problem:** Many of these claims exist only as prose in README.md or in one-off benchmark reports. They are _beliefs_, not _executable invariants_ (per CLAUDE.md §11). The TOON "50-70% more efficient" claim was the most recent example of this failure mode — the format was actually 1.96× _larger_ than JSON for decision-tool responses, and 62 conformance tests kept it green throughout.

**Secondary problem:** The project lacks a systematic way to use its own tools to find its own issues. TSA can analyze call graphs, detect dead code, score project health, and gate edits — but this capability is not applied to itself on a scheduled basis.

**Goal:** Become demonstrably the top-1 code intelligence tool for AI agents by ensuring every claim is verifiable and by continuously using TSA to improve TSA.

---

## Design: Three-Layer SVCD System

### Layer 1: Claim Invariant Suite

Every README claim must have a corresponding CI-gated test in `tests/benchmarks/claims/`.

#### Claims and their invariants

| README Claim | Invariant File | Type | CI Axis |
|---|---|---|---|
| 390× fewer mis-wires | `test_390x_miswire_claim.py` | benchmark | `full_language` Linux only |
| TOON ≤ JSON on bulk output | `test_output_cost_invariants.py` (extend existing) | unit | every PR |
| 96.3% call edge classification | `test_96pct_classification.py` | benchmark | `full_language` Linux only |
| –46% index speed (django cold) | `test_index_speed_claim.py` | benchmark | manual / scheduled |
| 8 MCP facade tools | `test_readme_counts_match_registry` (existing ✅) | unit | every PR |
| 321 CLI flags | `test_readme_counts_match_registry` (existing ✅) | unit | every PR |
| 13 curated skills | existing ✅ | unit | every PR |
| 5 layers of safety | `test_safety_layers_smoke.py` | smoke | every PR |
| 13 languages full call-graph | `@pytest.mark.full_language` corpus tests (extend) | golden | `full_language` Linux only |
| BM25 ranked search | `test_bm25_ranking_invariant.py` | unit | every PR |
| Reactive push (RFC-0001) | `test_reactive_push_e2e.py` | integration | every PR |

#### Invariant contract rules

1. **Exact values, not bounds.** Every count/measurement asserts `== N`, never `>= N`. If an upstream change shifts the number, the test goes red and forces a conscious re-pin (per CLAUDE.md §11 / Test Quality Rule T-2).
2. **strict=True xfail for known-failing claims.** Claims that are currently not met (e.g., TOON decision-tool size) must use `@pytest.mark.xfail(strict=True, reason="RFC-0018 in progress — tracked")`. Fixing the claim must un-xfail the test.
3. **measured_value in output.** Every benchmark test emits its measured value so CI history provides regression visibility.
4. **New benchmark tests go in `tests/benchmarks/claims/`, marked `@pytest.mark.claims_benchmark`.** They run in a dedicated CI job, never mixed into the main xdist suite.

#### Claim validation measurement commands

```bash
# 390× mis-wire claim (requires CodeGraph comparison baseline)
uv run pytest tests/benchmarks/claims/test_390x_miswire_claim.py -v

# TOON cost invariant
uv run pytest tests/unit/mcp/test_output_cost_invariants.py -v

# 96.3% classification rate
uv run pytest tests/benchmarks/claims/test_96pct_classification.py -v

# Index speed
uv run pytest tests/benchmarks/claims/test_index_speed_claim.py -v --benchmark-enable
```

---

### Layer 2: Multi-Model Dogfood Pipeline

Three models with complementary roles and structural checks on each other.

#### Model roles

| Model | Role | Rationale |
|---|---|---|
| **Claude Opus 4.8** | Commander / Strategist | Strongest reasoning; used for global priority decisions, dogfood orchestration, and writing task briefs. Not used for repetitive dev work. |
| **Claude Sonnet 4.6** | Developer × N (parallel) | Fast, cost-effective, sufficient for implementation. Spawned in parallel per the AGENTS.md memory-as-bus pattern. |
| **GPT-5.5** | Adversarial Reviewer | Different company = different blind spots. Reviews every dogfood-sprint PR. Cannot be overridden by Claude's reasoning. |

#### Cross-model check protocol

```
Opus writes task brief
    ↓ includes: "which claim invariant will this fix?"
Sonnet implements + writes tests
    ↓ must make ≥1 claim invariant pass (xfail → pass, or pin a new value)
GPT-5.5 reviews PR
    ↓ primary question: "does this PR produce a verifiable invariant improvement?"
    if no → requests invariant test before merge
    if yes → approves with P1/P2/P3 badge (same format as existing Codex review)
```

**No model can approve its own work.** Sonnet dev PRs are reviewed by GPT-5.5. Opus's strategic decisions are validated by GPT-5.5 on the sprint summary PR.

#### Dogfood tool sequence (Opus uses these TSA tools on TSA itself)

```bash
# 1. Overall project health grade
uv run python -m tree_sitter_analyzer --project-health --format json

# 2. Dead code (functions no one calls)
uv run python -m tree_sitter_analyzer --dead-code --format json

# 3. Change impact on recent commits
uv run python -m tree_sitter_analyzer --change-impact --format json

# 4. Architectural constraint violations
uv run python -m tree_sitter_analyzer --check-constraints

# 5. Claim invariant status (which claims are xfail?)
uv run pytest tests/benchmarks/claims/ -v --tb=no 2>&1 | grep -E "PASSED|FAILED|xfail|xpass"

# 6. README numbers still match reality
uv run pytest tests/ -k "readme_counts" -v
```

Opus reads all six outputs and produces a prioritized work list: `P0` (claim falsehood, blocks release), `P1` (correctness bug), `P2` (measurable improvement), `P3` (developer experience).

---

### Layer 3: CI Automation

Two new GitHub Actions workflows, both following existing CI patterns (AGENTS.md §CI Contract).

#### `dogfood-pr-check.yml` (auto, every PR)

Trigger: `pull_request` → `develop`

Steps:
1. Run `--change-impact` on changed files → extract `verification_command`
2. Run `verification_command` (the targeted test subset)
3. Run claim invariant suite (unit-only subset — no benchmarks)
4. Opus 4.8 reads the three outputs, generates a `dogfood-report` comment on the PR
5. Does **not** block merge — provides signal, not gate (the claim invariants are the gate)

Cost: ~1 Opus call per PR (~$0.02–0.05). The analysis is read-only.

#### `dogfood-sprint.yml` (manual, `workflow_dispatch`)

Trigger: Manual only (scheduled weekly via repository dispatch from a cron job, or run on demand)

Steps:
1. Full dogfood sequence (6 commands above)
2. Opus 4.8 writes a prioritized task list (JSON output to `$GITHUB_STEP_SUMMARY`)
3. For each P0/P1 task: spawn a Sonnet 4.6 agent, write a `feature/dogfood-YYYY-WW-<task>` branch, open a PR to `develop`
4. All dogfood-sprint PRs are auto-labeled `dogfood-sprint` and auto-assigned to GPT-5.5 reviewer
5. Sprint summary posted to GitHub Discussions `dogfood-sprints` category

**GitFlow compliance:** All branches are `feature/dogfood-YYYY-WW-*` cut from `develop`. Normal PR + review + merge process applies. No direct pushes.

**Develop freeze rule:** During an active `release/*` PR, dogfood-sprint PRs queue (same freeze rule as all other feature PRs, per AGENTS.md §Release Gate).

---

## Competitive Gap Closure Plan

The strategic roadmap (rfcs/ROADMAP-beyond-codegraph.md) has four remaining gaps. SVCD directly addresses them:

| Gap | Current state | SVCD action |
|---|---|---|
| **P0: Token cost vs CodeGraph** | Benchmark harness bug fixed; re-run not done | `test_token_cost_claim.py` forces the re-run as part of CI invariant setup |
| **P1: Multi-language correctness moat** | 13 languages active; measurement is manual | `test_96pct_classification.py` runs per-language breakdown automatically |
| **P3: Reactive push under-demoed** | RFC-0001 implemented, no E2E test | `test_reactive_push_e2e.py` is a new E2E that also serves as a live demo artifact |
| **P4: Resolution confidence signal** | Not exposed | Opus dogfood sprint will surface as P2 task |

---

## Acceptance Criteria

- [ ] `tests/benchmarks/claims/` directory exists with ≥4 new claim invariant tests
- [ ] All existing README number claims are gated by a CI test (exact value, not bound)
- [ ] Known-failing claims use `strict=True xfail` with tracking reference
- [ ] `dogfood-pr-check.yml` runs on every PR to develop and posts a report comment
- [ ] `dogfood-sprint.yml` is a manual workflow that produces ≥1 actionable PR per run
- [ ] GPT-5.5 reviews all dogfood-sprint PRs (configured as required reviewer for `dogfood-sprint` label)
- [ ] After first full sprint: at least one `strict xfail` claim converts to a passing test
- [ ] README's "TOON ≤ JSON" claim is either confirmed by invariant or corrected

---

## Three-Surface (CLI ↔ MCP) Parity

New claim invariant tests use CLI commands (not MCP calls) for measurement — this is intentional. The invariants measure end-to-end behavior and CLI is the stable, human-verifiable interface. MCP-specific behavior (e.g. TOON output size) is tested in the existing `test_output_cost_invariants.py`.

No new MCP tools or CLI flags are introduced by SVCD itself. The CI workflows invoke existing tools.

---

## RED-First Test Plan

Implementation order enforces RED → GREEN:

1. Write `test_390x_miswire_claim.py` with the correct assertion — it will **fail** until the measurement infrastructure is wired. This is the RED state.
2. Wire the measurement (use existing `miswire_audit.py`) → test passes (GREEN).
3. Repeat for each claim in the table above, one claim at a time.
4. Write `dogfood-pr-check.yml` — test the workflow locally with `act` before pushing.
5. Write `dogfood-sprint.yml` — validate with a single manual trigger before scheduling.

No speculative features. No "we'll add this later" stubs. Each acceptance criterion has a corresponding test that starts RED.

---

## Out of Scope

- Changes to TSA's core analysis logic (SVCD is an observability + verification layer, not a feature layer)
- New language plugins (handled by existing RFC process)
- Changes to TOON format or MCP tool signatures (gated by existing RFC process)
- Any changes to `BaseMCPTool`, `SecurityValidator`, or `PathResolver` (per CLAUDE.md §2)
