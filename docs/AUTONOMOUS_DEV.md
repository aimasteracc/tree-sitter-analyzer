# Autonomous Development Architecture

Single source of truth for the project's "self-driving" pipeline. Updated
when components change, not when sprints land.

## TL;DR

The pipeline has 4 layers. Each layer is a precise commitment about
**which decisions a human still makes**. Today the project sits at
**Level 1.5** with a clear path to Level 2.

```
Level 4 ─ Full unattended       agent writes + CI + auto-merge + canary + auto-rollback
   ↑
Level 3 ─ Auto-merge trivial    agent writes + auto-merge ONLY when risk=trivial classifier agrees
   ↑
Level 2 ─ Cron-scheduled PRs    cron → agent → PR (NEVER merged) → human reviews
   ↑
Level 1.5 ─ One-click brief     scripts/auto_sprint_brief.py prints a paste-ready prompt
   ↑
Level 1 ─ On-demand single      human triggers, agent does one work item, opens PR
   ↑
Level 0 ─ Discover only         agent never writes code; produces a daily backlog issue
```

## What's wired today

| Component | File | Layer it serves |
|---|---|---|
| Self-audit CLI bundle | `scripts/auto_review.py` | L0, L1, L2 |
| Daily backlog cron | `.github/workflows/auto-sprint.yml` | L0 |
| Brief generator | `scripts/auto_sprint_brief.py` | L1.5 |
| Execute workflow | `.github/workflows/auto-sprint-execute.yml` | L1.5 (mode=brief), L2 (mode=claude-code) |
| 18 plugin golden masters | `tests/regression/test_plugin_golden_masters.py` | L2 quality gate |
| Change-impact analyzer | `--change-impact` MCP/CLI tool | L1+ quality gate |
| Project-health grader | `--project-health` MCP/CLI tool | L0 backlog, L2 regression check |
| Code-pattern detector | `--code-patterns` MCP/CLI tool | L0 backlog, L2 regression check |

## The non-negotiable safety contract

Across **every layer**, agents must:

1. **Never** pass `--no-verify`, `--dangerously-skip-permissions`, or any
   flag that bypasses the project's pre-commit hooks. If a hook fails,
   the agent stops and surfaces a diagnosis. Only humans may use
   `--no-verify`, and only with a `Note on --no-verify` commit-message
   section explaining why.
2. **Never** push to `main` or `master`. Only to feature branches.
3. **Never** auto-merge. Even at Level 3 the merge is gated on a
   classifier-confirmed `risk: trivial` label AND on three green gates
   (tests + golden masters + change-impact).
4. **Never** commit secrets (`.env`, credentials, anything matching
   `.secrets.baseline`).
5. **Stay in scope.** The brief specifies which files an agent may edit.
   Scope creep is filed to `docs/AUDIT_FINDINGS_*.md`, not silently
   absorbed.
6. **Bail-out triggers** (the agent must stop and report):
   - same test fails 3 times after edits
   - any file grows past 800 lines as a result of edits
   - mypy on the changed files reports **new** errors (not pre-existing)
   - `--project-health` overall grade drops vs the baseline measured
     before the edit
   - the agent cannot find a green-light path within its time budget

## Level-by-level: what's required to advance

### Level 0 → 1: human-triggered single work item

**Status: ✅ done.** A human runs:
```bash
uv run python scripts/auto_review.py --max-items 5 --out /tmp/plan.json
uv run python scripts/auto_sprint_brief.py --plan /tmp/plan.json --index 0 \
  | pbcopy   # macOS — paste into a fresh Claude Code session
```

### Level 1 → 1.5: one-click brief generator

**Status: ✅ done.** `auto_sprint_brief.py` produces a self-contained,
paste-ready brief with:
- the specific file + grade + signal
- recommended discovery commands
- a baseline-snapshot recipe
- the verification gate (tests + golden masters + mypy on changed files)
- the bail-out triggers

The brief explicitly forbids `--no-verify` and `--dangerously-skip-permissions`.

### Level 1.5 → 2: cron-scheduled PRs (no human prompt needed)

**Status: 🟡 wired but opt-in.**

`.github/workflows/auto-sprint-execute.yml` has two modes:

- **`mode=brief` (default, free).** Workflow uploads the brief as an
  artifact + posts it to the auto-sprint issue. Operator copies into
  Claude Code locally. This is Level 1.5 with a GitHub-resident brief.

- **`mode=claude-code` (needs `ANTHROPIC_API_KEY` repo secret).** Invokes
  `anthropics/claude-code-base-action` with the brief, allowed-tools
  restricted to `Bash(uv run *), Bash(git add/diff), Edit/Write/Read/Grep/Glob`
  (no push, no merge). Successful runs open a PR against the current
  branch with the brief as PR body. **A human merges.** This is Level 2.

To turn on Level 2:

1. Settings → Secrets and variables → Actions → New repository secret
   `ANTHROPIC_API_KEY`.
2. Actions → Auto-Sprint Execute → Run workflow → mode=claude-code.
3. Watch the run. If the PR opens green, merge. If it fails, the artifact
   tells you exactly what the agent saw.

To extend Level 2 from manual dispatch to true cron, add a `schedule:`
block to `auto-sprint-execute.yml` — but only after you've watched
~5 manual runs end-to-end and trust the gate.

### Level 2 → 3: auto-merge trivial work items

**Status: 🔴 not started.** Needs:

1. **A risk classifier.** Either rule-based (e.g. `risk=trivial` when
   diff touches only `tests/`, only docs, only known dead-code files
   identified by `vulture` / `ts-prune`) or learned (an Anthropic call
   that reads the diff and emits a JSON `{risk: trivial|medium|high}`
   with cached results).
2. **A 3-green gate.** Before auto-merge: `pytest -q` clean + golden
   masters clean + `--project-health` grade unchanged.
3. **A 24-hour soak.** Auto-merged PRs land in a `staging` branch that
   merges to `main` daily after CI passes there too.
4. **Comprehensive audit trail.** Every auto-merge writes an entry to
   `docs/AUTO_MERGE_LOG.md` with the diff stats + gate results.

### Level 3 → 4: full unattended

**Status: 🔴 not started.** Adds, on top of L3:

1. **Canary monitoring** of the released PyPI package — error rate, MCP
   tool execute latency. The existing `--project-health` is not enough;
   need post-deploy telemetry from real users.
2. **Auto-rollback.** If canary detects regression within 24 h of an
   auto-merge, the workflow opens a revert PR and marks the original
   commit's audit-log entry as 🔴.
3. **A community-trust threshold.** Stars + active maintainers above
   some bar before unattended makes sense for the public; the cost of a
   bad auto-merge on a 31-star project is community trust, not just code.

For an open-source project, **Level 3 is the realistic ceiling** —
the human review gate is also a community signal and you don't want to
trade that away. Level 4 makes more sense for closed/private projects.

## Operator quick reference

| I want to… | Do this |
|---|---|
| See today's backlog | Look at the `auto-sprint` labeled issue, or run `auto_review.py` |
| Take one work item myself | `auto_sprint_brief.py --index 0 \| pbcopy`, paste into Claude Code |
| Let CI write a paste-ready brief | Actions → Auto-Sprint Execute → mode=brief |
| Let an agent do it end-to-end | Add `ANTHROPIC_API_KEY` secret, Actions → mode=claude-code |
| Stop everything | Actions → disable the workflow, or revoke `ANTHROPIC_API_KEY` |
| Accept a deliberate golden-master change | `TSA_UPDATE_GOLDEN=1 uv run pytest tests/regression/test_plugin_golden_masters.py` |
| Find pre-existing issues to triage | Run `uv run python scripts/auto_review.py --max-items 20` to surface the current backlog. |

## Pattern memory (ruflo)

The audit + sprint history is persisted to ruflo memory and ReasoningBank:

| Namespace | Key | Use |
|---|---|---|
| `project-context` | `tree-sitter-analyzer/audit/2026-05-20` | Overall audit posture |
| `project-context` | `tree-sitter-analyzer/perf-1/route-cache` | PERF-1 implementation notes |
| `project-context` | `tree-sitter-analyzer/audit-pass-2/perf-and-tests` | Pass-2 results |
| ReasoningBank pattern | `audit-workflow` | Reusable dogfood-first audit recipe |
| ReasoningBank pattern | `performance-optimization` | Generic filesystem-walker tuning recipe |

A future session can `memory_search("audit posture")` or
`agentdb_pattern-search("performance optimization")` to recover this
context instantly.
