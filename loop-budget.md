# Loop Budget — tree-sitter-analyzer No.1 programme

> Hard ceiling: automated loop work may consume at most **50 percentage
> points of the user's visible Codex Max weekly plan**.

Codex Max does not expose a stable token-to-plan conversion to this repository.
The loop records `tokens_estimate` and the UI's `weekly_plan_used_pct` as
different facts. If the percentage is unknown, only L1 triage and already-red
CI recovery may start; speculative L2/L3 work waits for a fresh reading.

## Weekly allocation

| Workstream | Max percentage points | Purpose |
|---|---:|---|
| No.1 product delivery | 20 | One measurable product wedge at a time |
| Reliability and CI | 10 | Red `develop`, runtime, install and Windows reliability |
| Competitive evidence | 8 | Reproducible benchmark and outside baselines |
| PR and review closure | 7 | CI, Codex threads, patch coverage and cleanup |
| Incident reserve | 5 | Security, release or severe regression only |
| **Total** | **50** | Hard weekly automation ceiling |

Unused allocation is not permission to manufacture work. Moving points between
workstreams requires a run-log entry; the total may never exceed 50.

## Per-loop limits

| Loop | Cadence | Maturity | Max action/run | Token ceiling |
|---|---|---|---:|---:|
| CI Sweeper | event-driven when red | L2 | 1 root-cause fix | 250k |
| PR Babysitter | state change; max 4/day | L1→L2 | 1 review cluster | 250k |
| No.1 Delivery | max 1/day, 3/week | L2 | 1 finished PR | 500k |
| Daily Triage | weekday, max 1/day | L1 | report/queue only | 100k |
| Competitive Evidence | max 2/week | L1→L2 | 1 reproducible claim | 300k |
| Post-merge Cleanup | once per merge | L2 | branch/worktree/artifacts | 100k |

## Throttle ladder

| Visible weekly usage | Automatic behaviour |
|---:|---|
| `< 35%` | Normal bounded L1/L2 execution |
| `35–40%` | One implementation only; no speculative expansion |
| `40–45%` | L1-only except red `develop`, security, or active PR closure |
| `45–50%` | Finish current PR only; do not start a new branch |
| `>= 50%` | Set `loop-pause-all`; stop every implementation loop |

## Run-level gates

1. Estimate with `loop-cost` before L2/L3 and append actuals after it.
2. CI Sweeper outranks every other loop; no feature starts while `develop` is red.
3. One owner per branch/hour, one fix/run, maximum three failed attempts.
4. Tests, benchmark setup and review closure share the same allocation.
5. A benchmark claim requires manifest, setup evidence, raw result and CI invariant.

## Kill switch

- State flag: `loop-pause-all` under `STATE.md` High Priority.
- Resume only after the user clears it and a fresh usage percentage is recorded.
- Exhaustion is report-only; never auto-merge, force-push or weaken a gate.
