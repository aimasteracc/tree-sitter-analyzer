# Loop Configuration — tree-sitter-analyzer No.1

## Mission and proof standard

Become the most trusted code-intelligence tool for AI coding agents. “No.1” is
not a feature-count claim. Promotion requires four forms of evidence:

1. real agent task success or defect prevention;
2. a reproducible benchmark against named outside baselines;
3. bounded latency, installation and cross-platform reliability;
4. self-dogfood results whose false positives and misses are tracked.

SQLite remains the canonical index and LadybugDB a graph projection. JSON is
not a persistence layer.

## Priority scheduler

Only the first eligible loop runs; lower rows wait for higher actionable work.

| Priority | Pattern | Trigger | Early exit | Action mode |
|---:|---|---|---|---|
| 0 | CI Sweeper | `develop` or active PR red | required checks green | L2, one cause |
| 1 | PR Babysitter | check/review changed | no new failure/thread | L1→L2 |
| 2 | Post-merge Cleanup | PR merged | worktree/artifacts clean | L2 |
| 3 | No.1 Delivery | measurable queue item | throttle or no evidence plan | L2 |
| 4 | Competitive Evidence | claim due/changed | evidence unchanged | L1→L2 |
| 5 | Daily Triage | weekday | no state change | L1 report-only |

## Required protocol

### Before action

1. Read constraints, budget, state and the last run log.
2. Record visible `weekly_plan_used_pct`; otherwise apply the fallback.
3. Fetch `origin/develop`; use GitFlow and an isolated worktree for L2.
4. Run and time TSA health, safe-to-edit and change-impact first. Incorrect
   recommendations are product defects, not unquestioned instructions.
5. State one acceptance criterion and one stop condition.

### During action

- One branch owner, one root cause, one finished PR.
- TDD for behaviour; never lower timeout, performance or coverage gates.
- Verify TSA's file/test routing against the actual subsystem.
- Stop after three failed attempts and append evidence to the run log.

### No-progress circuit breaker

- Fingerprint each failure by command, normalized error and changed-file set.
- The same fingerprint twice forbids repeating the same action; return to L1
  diagnosis and require new evidence or a different bounded intervention.
- Three failed attempts halt that queue item, record it in `STATE.md` and the
  run log, and escalate. A different higher-priority independent item may run;
  the halted action may not silently restart.
- A run with no state, evidence, check or review change is a no-op and exits.

### After action

1. Re-run change-impact and its exact command plus the relevant test.
2. Run patch coverage and `uv run pytest -q` at the queue boundary. Do not
   override `TMP`/`TEMP`; pytest owns its external managed temp root.
3. Create a Draft PR and watch CI plus thread-aware Codex reviews.
4. Never auto-merge. After human merge, run Post-merge Cleanup.
5. Append reusable dogfood evidence to run log and project memory.

## Active queues

| Queue | Current item | Proof of completion |
|---|---|---|
| CI/PR | PR #1161 constraint SQL prefilter | all CI/build + no unresolved Codex thread |
| Agent feedback | wrong same-name test and ~96 s impact | correct test + latency invariant |
| Health trust | `no_data` graded F | unknown separated from measured failure |
| Competitive proof | PR #1160 benchmark manifests | reproducible baselines and dashboard |

## Human gates

- Draft PR first; never auto-merge to `develop` or `main`.
- Human review before moat/schema/RFC/public-surface changes.
- Release/hotfix flows remain governed by `GITFLOW.md`.
- `loop-pause-all` stops every loop immediately.

## State ownership

- Mission/queue: `STATE.md`
- Budget/throttle: `loop-budget.md`
- Append-only evidence: `loop-run-log.md`
- Mutable implementation state stays in its branch/worktree.
