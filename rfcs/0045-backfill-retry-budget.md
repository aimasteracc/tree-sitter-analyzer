# RFC-0045: Retry budget for the self-healing backfill pass

- **Status**: draft
- **Author(s)**: agent dogfood round 2026-11-09/10
- **Created**: 2026-11-10
- **Last updated**: 2026-11-10
- **Tracking issue**: TBD
- **Affected source paths**:
  - `tree_sitter_analyzer/cache/indexer.py` (`post_index_backfill`, `_post_index_backfill`)
  - `tree_sitter_analyzer/cache/unresolved.py` (convergence marker)
  - `tests/unit/test_ast_cache_projection_state.py`, `tests/unit/test_ast_cache_index_project.py`

## Summary

A repository whose call graph can never be certified (an optional grammar is not
installed) re-runs the whole backfill pass on **every** `index` invocation, even
when no source changed. This RFC adds a persisted retry budget to that self-healing
pass: after an attempt that could not certify anything, the next no-op invocation
skips the pass until the budget expires, while any change, any recorded failure and
any explicit force still run it immediately.

## Motivation

Measured on this repository (2026-11-09/10, macOS, 10 cores, 2917 files, 82k symbols):

| state | cost | what dominates |
|---|---|---|
| no-op `--ast-cache --ast-cache-mode index` | **7.3–8.1 s** | `run_synapse_backfill` re-resolving ~49k–94k unknown edges, then `backfill_cross_file_edges` |
| a 6-file edit, same command | 9.85 s | the same backfills plus 6 parsed files |

The re-resolution produces no new information: it re-derives the same unresolved
edges because the input index did not change. The reason the pass cannot simply be
skipped is #1253: `test_fully_cached_missing_marker_reruns_every_backfill` and
`test_fully_cached_failed_retry_keeps_marker_clear` encode that a cached answer with
a missing call-graph marker must retry the pass, because retrying is how the marker
comes back after a failed run.

Both statements are true at once, and the resolution is to separate **how often**
from **whether**: retrying is required, retrying on *every* invocation is not.

A first attempt to skip when `changed == 0 and resolution_converged` cut the no-op
cost to 2.6–3.2 s here but was reverted because it bypassed #1253. A second, safe
slice has landed already: when the call graph **is** certified and the resolve state
converged, the pass is skipped (`backfill_skipped: CERTIFIED_CONVERGED`). That helps
healthy installs; it cannot help this repository, whose `call_graph_built()` is
permanently `False` (missing `lua`/`swift` grammars).

## Detailed design

### Persisted state

Two keys in the existing `ast_cache_metadata` table (no schema migration):

| key | value |
|---|---|
| `backfill_last_attempt_at` | epoch seconds of the last pass that actually ran |
| `backfill_last_attempt_ok` | `"1"` when that pass recorded no backfill errors, else `"0"` |

### Decision

```python
def should_skip_backfill(changed, cache, conn, now=None) -> str | None:
    """返回跳过原因；None 表示照旧回填。"""
    if changed:
        return None                       # 输入变了：必须回填
    if _resolution_is_certified(cache, conn):
        return "CERTIFIED_CONVERGED"      # 已认证：回填只会重算同样的边
    last = _read_attempt(conn)
    if last is None or last.ok is False:
        return None                       # 上次失败/从未尝试：立刻重试
    if (now or time.time()) - last.at < RETRY_BUDGET_SECONDS:
        return "RETRY_BUDGET"
    return None
```

`RETRY_BUDGET_SECONDS = 3600` (module constant, overridable through the existing
config mechanism for tests). The pass writes both keys on every real attempt.

### Invariants this keeps

1. A changed file always runs the pass.
2. A pass that recorded `backfill_errors` forces the next invocation to run it again
   (the #1253 failure-retry contract).
3. A cache with no attempt record runs the pass (first run, and any cache predating
   this RFC).
4. Force (`--ast-cache-force`, full rebuild) ignores the budget.

### MCP / CLI surface

No new flag, no new action, no new parameter. The only observable difference is
`backfill_skipped: "RETRY_BUDGET"` in the index response (the same field the
certified skip already uses), plus a one-line `next_step` when the budget is active.

## Three-Surface impact (CLI ↔ MCP parity)

Unchanged: the decision is internal to the index runner. CLI and MCP index routes
already share it, and the response field is additive.

## Drawbacks

- A repository that becomes certifiable *because* a grammar was installed at second
  3599 of the budget waits up to one hour for the marker. Mitigation: the budget is
  reset by any change, any failure, and by `--ast-cache-force`.
- One more piece of persisted state that can be stale; it must be pruned together
  with the index generation (the existing generation GC covers metadata rows).
- The default (one hour) is a judgement call; it is configurable, and the RFC's
  test pins the decision function, not a wall-clock wait.

## Alternatives

- **Alternative A: skip unconditionally when `changed == 0` and converged.**
  Measured 2.6–3.2 s, but it deletes the #1253 retry path. Rejected.
- **Alternative B: new `ast_backfill_state` table.** Cleaner typing, but a schema
  version bump for two scalar values. Rejected for now.
- **Alternative C: make the synapse backfill itself incremental (input
  fingerprint per edge).** The best long-term answer (no retry semantics at all),
  but a much larger change; this RFC is deliberately the small step that stops the
  repeat cost without touching the resolver.

## Test plan (RED-first)

1. `test_fully_cached_missing_marker_reruns_every_backfill` — unchanged: no attempt
   record ⇒ the pass runs.
2. `test_a_failed_pass_forces_the_next_attempt` — record `ok=0`, then a no-op index
   must run the pass again (even inside the budget).
3. `test_a_recent_successful_uncertifiable_pass_is_skipped` — record `ok=1` at
   `now-60`, a no-op index returns `backfill_skipped == "RETRY_BUDGET"` and no
   `synapse_backfill` block.
4. `test_an_expired_budget_reruns_the_pass` — `ok=1` at `now-3700` ⇒ the pass runs.
5. `test_a_changed_file_ignores_the_budget` — `changed > 0` ⇒ the pass runs.
6. Dogfood: this repository's no-op index must drop from 7.3–8.1 s to <1.5 s with an
   active budget, and the first index after the budget expires must still report the
   same backfill numbers as today.

## Acceptance criteria

- [ ] `backfill_skipped: RETRY_BUDGET` appears only for an unchanged, uncertified,
      recently-attempted cache
- [ ] The three #1253 invariants above hold, each with its own test
- [ ] Force and full rebuild ignore the budget
- [ ] `docs/dev/dogfood-trust-2026-11-09.md` §11 numbers replaced with the measured
      after-state (same machine, same corpus, both cold and no-op stated)
- [ ] No new CLI flag, no new MCP action

## What this RFC does NOT do (deferred)

- It does not make the backfill incremental (Alternative C).
- It does not change what "certified" means; the certified skip is already merged.
- It does not change the response shape beyond the existing `backfill_skipped` field.

## Open questions

1. Is one hour the right default, or should it be derived from the last index
   duration (e.g. `max(600, 10 * duration)`)?
2. Should the budget be per generation (reset when the generation changes) in
   addition to being reset by a change?
3. Should the response surface the remaining budget so an agent can decide whether
   to force a retry?
