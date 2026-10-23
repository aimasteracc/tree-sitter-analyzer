# RFC-0040: Proof-carrying completeness for `nav action=callers`

- **Status**: draft — implemented in the PR that introduces it; awaiting owner review
- **Author(s)**: @aimasteracc
- **Created**: 2026-10-24
- **Tracking issue**: the wrong-`complete` class #1740, #1758, #1759, #1772, #1644 (all fixed individually)
- **Affected source paths**:
  - new `tree_sitter_analyzer/mcp/tools/callers_outcomes.py` (`Checked` / `NotChecked`)
  - new `tree_sitter_analyzer/mcp/tools/callers_checks.py` (`REQUIRED_CHECKS`, `Ledger`, `prove`)
  - new `tree_sitter_analyzer/mcp/tools/callers_target_set.py` (`TargetSet`, graph-path module-level count)
  - `tree_sitter_analyzer/mcp/tools/callers_tool.py`, `callers_absence.py`, `callers_reasons.py`
  - `docs/agent-envelope-contract.md` (reason table, `completeness_checks`)

## Summary

`nav action=callers` derives `complete` from the **absence of failure flags**. Before this RFC,
`edge_completeness()` returned `complete` whenever no reason applied. Four of its six inputs
were plain counts, so they could not say "this check did not run". Any code path that skipped a
check therefore produced 0, and 0 meant `complete`.

This RFC inverts the derivation:

- Every required check reports a typed outcome, either `Checked(scope, problems)` or
  `NotChecked(reason)`.
- `complete` is constructed in one place, `callers_checks.prove()`. It is returned only when
  **every** check in the closed registry `REQUIRED_CHECKS` reports `Checked` over the queried
  target set, with no problems.
- A check that is missing from the ledger, did not run, or ran over a different target set gives
  `unknown`, or `incomplete` when callers are listed. Its reason code names that check.
- Failing closed is the default by construction, not a review rule.

The principle is borrowed from REA (`docs/tool-design.md`: "derive facet completeness from
examined records … rather than … an empty failure list"; "missing coverage is unknown, not
absence").

## Motivation

Each recent wrong-`complete` bug was a path where a gate did not run, or ran on too narrow a
scope, so its count defaulted to 0:

| Issue | Path that skipped a check | Result |
|---|---|---|
| #1740 | The bare name skipped the name-only check | `complete` (gson 7/40, rich 4/40) |
| #1759 | The qualified name looked up the declaring files by `Class.method`, found none, and skipped the guard ("skipped the guard entirely" comment in `callers_tool.py`) | `complete, 0` |
| #1758 | An early return in `_inferred_targets` never ran the global tier | `complete` |
| #1772 | A nearer Protocol stub hid the real target | `complete` |
| #1644 | An index-missing reply carried no completeness at all | no claim |

All of these are fixed individually. While designing this RFC, reading the code found four more
paths of the same class that were still open on `develop`. Each is now closed and has a test:

1. `assess_completeness` returned the edge-level `complete` unchanged, without running any review
   gate, when `project_root` was falsy.
2. `_is_accessor` silently skipped a declaration it could not read, so an unreadable file meant
   "not an accessor".
3. `_sibling_methods` swallowed graph exceptions and returned `[]`. The bare union then skipped
   the same-file methods' callers and name-only edges.
4. The cache-built call graph drops module-level edges that have no call line
   (`_edge_caller_ref`). The graph path, which serves every qualified query, therefore fixed
   `unattributed_call_sites = 0` without counting anything. That check never ran on that path.

Also, the index-rebuilding reply carried no completeness (#1644 class), and
`stale_reference_files() is None` (index stamps unreadable) was read as "no stale files".

## Design

### 1. Typed outcomes (`callers_outcomes.py`)

```python
@dataclass(frozen=True)
class Checked:      scope: Scope; problems: tuple[str, ...] = ()   # ran over scope
@dataclass(frozen=True)
class NotChecked:   reason: str                                  # could not run
CheckOutcome = Checked | NotChecked
```

A plain count cannot distinguish "ran and found 0" from "did not run". Every required check now
returns one of these two values.

### 2. Closed registry and the single constructor of `complete` (`callers_checks.py`)

`REQUIRED_CHECKS` lists 12 checks in reason-priority order. The `unchecked` code is what the
check reports when it did not run.

| # | Check | Layer | Problem code(s) | `unchecked` code |
|---|---|---|---|---|
| 1 | `unresolved_inbound` | edge | `UNRESOLVED_INBOUND` | `UNRESOLVED_INBOUND_UNCHECKED` |
| 2 | `declaring_file` | edge | `UNRESOLVED_IN_DECLARING_FILE` | `UNRESOLVED_INBOUND_UNCHECKED` |
| 3 | `name_only` | edge | `NAME_ONLY_INBOUND` | **`NAME_ONLY_INBOUND_UNCHECKED`** (new) |
| 4 | `unattributed` | edge | `UNATTRIBUTED_CALL_SITES` | **`UNATTRIBUTED_CALL_SITES_UNCHECKED`** (new) |
| 5 | `evidence_base` | edge | `EMPTY_EVIDENCE_BASE` | `UNRESOLVED_INBOUND_UNCHECKED` |
| 6 | `freshness` | review | `SOURCE_INDEX_MISMATCH` | the evidence reason (`SOURCE_SCOPE_UNKNOWN`, …) |
| 7 | `target_defined` | review | `SYMBOL_NOT_DEFINED`, `SYMBOL_IN_EXCLUDED_FILE` | `SYMBOL_DEFINITION_UNCHECKED` |
| 8 | `unindexed_sources` | review | `UNINDEXED_SOURCE_FILES` | `UNINDEXED_SOURCE_UNCHECKED` |
| 9 | `reference_freshness` | review | `SOURCE_INDEX_MISMATCH` (+ #1672 `also`) | `SOURCE_SCOPE_UNKNOWN` |
| 10 | `accessor` | review | `ACCESSOR_NOT_CALL_EDGES` | **`ACCESSOR_UNCHECKED`** (new) |
| 11 | `non_call_references` | review | `NON_CALL_REFERENCES` | `NON_CALL_REFERENCES_UNCHECKED` |
| 12 | `registering_decorator` | review | `DECORATOR_MAY_REGISTER` | `DECORATOR_MAY_REGISTER` |

**Reason-code changes.**
- Codes are reused wherever one already meant "could not run".
- Three codes are new: `NAME_ONLY_INBOUND_UNCHECKED`, `UNATTRIBUTED_CALL_SITES_UNCHECKED` and
  `ACCESSOR_UNCHECKED`. Each is `<existing problem code>_UNCHECKED`, or the closest equivalent,
  for a check that had no way to say "not run".
- No code was removed or renamed.

**How `prove(ledger, total_callers)` decides.**
- **Edge layer:** this layer keeps the #1632 semantics.
  - Reasons combine: not-checked codes come first in registry order, then problems in registry
    order.
  - Any not-checked edge check gives `unknown`.
  - A gated primary problem (unresolved, declaring file, name-only) gives `incomplete` when
    callers are listed, and `unknown` otherwise.
  - Unattributed gives `incomplete`. An empty evidence base gives `unknown`.
- **Review layer:** this runs only when the edge layer is clean. Gates are taken in order, and the
  first one that is not clean decides.
  - The result is `incomplete` when callers are listed, and `unknown` otherwise.
  - The reason is that gate's own problem codes or its not-checked code, exactly the existing
    reason contract.
- **`complete`** is returned only after all 12 checks pass.

**Fail closed by construction.** `Ledger.outcome(spec)` returns `NotChecked(spec.unchecked_reason)`
in three cases:
- the check is missing from the ledger;
- its recorded scope differs from the ledger's target-set scope;
- it is a check added to the registry that no code path records yet.

`Ledger.record` rejects names outside the registry. Nothing else in the package constructs
`complete` for `nav callers`. The review gates still compute their own provisional verdict for
hints, and the final `completeness` field is `prove(...)`'s output.

### 3. One target set, resolved before any check (`callers_target_set.py`)

The #1759 rewrite runs first: a bare name with exactly one method definition in the named file
becomes `Class.method`. Then `target_set(name, file_path)` yields the canonical name, the
qualification, `count_name` (the bare member name used by the name-keyed checks, #1559/#1759) and
`scope = (name, file_path)`.

Every check reads this object, and every `Checked` must carry its `scope`. Bare and qualified
queries for one method are therefore checked identically: same scope, same 12 checks, same proof.
A test asserts that their reason and checks payloads are equal.

### 4. Payload (compatible)

The `completeness`, `completeness_reason` and `completeness_reasons` fields keep their meaning
and order. There is one additive, bounded field:

```json
"completeness_checks": {"required": 12, "checked": 12}
"completeness_checks": {"required": 12, "checked": 7, "not_checked": {"accessor": "ACCESSOR_UNCHECKED"}, "not_run": 4}
```

- `not_checked` names the checks the proof reached that did not run, with their codes. It has at
  most 12 entries.
- `not_run` is the number of review gates that were short-circuited because an earlier gate had
  already decided the answer.
- The field is about 35 bytes on a `complete` answer.
- When callers are listed and the primary reason is a new not-checked code, `next_step` names the
  check that did not run. With 0 callers, the `NOT_FOUND` hint does the same.

### 5. Closing the remaining skip paths

- **No `project_root`:** the freshness check runs; the source checks cannot. The answer is
  `unknown` (or `incomplete`) with `SYMBOL_DEFINITION_UNCHECKED`.
- **`_is_accessor`:** it returns `None` when any declaration is unreadable or its line is outside
  the file and no other declaration is an accessor. The result is `ACCESSOR_UNCHECKED`.
- **`_sibling_methods`:** it returns `None` on an unreadable graph. The result is
  `NAME_ONLY_INBOUND_UNCHECKED`.
- **Graph path `unattributed`:** module-level edges with no call line are now counted from the
  call edges, with the same rule as the SQL path (`module_caller_entry(edge) is None`). A
  qualified query counts by the bare member name, which can only be more conservative. An
  unreadable count gives `UNATTRIBUTED_CALL_SITES_UNCHECKED`.
- **Unreadable reference stamps:** the comparison did not run, so the answer is
  `SOURCE_SCOPE_UNKNOWN`. Before, this was treated as "no stale files".
- **No declaration rows** (unreadable or empty): the reference review cannot run. The answer is
  `NON_CALL_REFERENCES_UNCHECKED`, as before for the unreadable case.
- **Index-rebuilding reply:** it now carries `unknown` / `MISSING_INDEX`. The
  `INDEX_MISSING` refusal already did this.

## Compatibility

- **Payload:** no field is removed or renamed and no reason code changes meaning. The three new
  codes and `completeness_checks` are additive. The closed-set doc table and its drift test are
  updated.
- **Answers whose checks all ran:** these are unchanged (see Measurement).
- **Answers that change:** only answers where a check genuinely did not run. They move from
  `complete` to `unknown`/`incomplete`, which is the intended direction.
- **One deliberate precedence change in a failure-only path:** when the non-call reference scan
  times out and the target is also an accessor, the reason is now
  `NON_CALL_REFERENCES_UNCHECKED`, the check that did not run, instead of
  `ACCESSOR_NOT_CALL_EDGES`. The answer is non-`complete` either way.
- **Persistence:** nothing persisted changes. The extractor version stays 54 and no reindex is
  needed.
- **Internal API:** `EdgeEvidence`, `edge_completeness` and `final_reasons` are removed. They are
  superseded by `callers_checks`, and their tests now exercise `prove_edges` / `prove`.

## Test plan

New `tests/unit/mcp/tools/test_callers_proof_carrying_completeness.py`:

- **Registry, parametrised over every `REQUIRED_CHECKS` entry:**
  - for a missing, not-checked or wrong-scope check, `complete` is impossible, and the reason is
    that check's unchecked code;
  - a newly registered but unwired check fails closed;
  - an unregistered name is rejected;
  - the edge-layer order and severity follow the #1632 contract.
- **Real indexed project, in both modes:**
  - a census carries `{"required": 12, "checked": 12}`;
  - bare and qualified queries carry the same proof;
  - a review gate that claims `complete` without recording checks is not `complete`;
  - an edge check left out of the ledger is not `complete`;
  - the graph-path module-level count reporting "not run" gives
    `UNATTRIBUTED_CALL_SITES_UNCHECKED`;
  - unreadable sibling methods give `NAME_ONLY_INBOUND_UNCHECKED`, named in `next_step`;
  - an unreadable accessor check gives `ACCESSOR_UNCHECKED`;
  - unreadable reference stamps give `SOURCE_SCOPE_UNKNOWN`;
  - the index-rebuilding reply declares `unknown` / `MISSING_INDEX`.
- **Updated existing tests:**
  - `_is_accessor` returns `None` when unreadable;
  - `_sibling_methods` returns `None` on an unreadable graph;
  - the edge and absence reason tests are ported to `prove_edges` / `prove`;
  - the closed reason set.
- **RED evidence:** the same scenarios run against `develop` (`f582c2d5`):
  - the forgetful review gate gives `complete` in both modes;
  - unreadable siblings give `complete`;
  - no `project_root` gives `complete`;
  - the rebuild reply has no `completeness` field.

## Measurement

The dogfood batteries of r12b were rerun on the same repo commits: the rich, pydantic and fastapi
samples plus three sweeps; the axios and gson manual truth plus sweeps; the zod and hono GT plus
sweeps. Both modes were run with `develop` (before) and this branch (after). The table, together
with every answer that moved from `complete` to non-`complete` and the check responsible, is in
the PR description.

## Residual risks and out of scope

- `ASTCache.query_callers` returns `[]` on `sqlite3.OperationalError`, and `count_unresolved_callers`
  has its own fallbacks. A failed read inside the cache layer can still look like a successful 0.
  Typing those readers as `Checked | NotChecked` belongs in the cache layer and is left for a
  follow-up, to avoid colliding with the ongoing `index_source_snapshot` and
  `call_graph_incremental` work.
- `Checked.scope` proves that a check ran over the same target-set identity. It does not prove
  that the check's own internal lookup was correct. A check that runs but looks in the wrong place
  (the #1772 shape) is still caught by the oracle work (REA comparison #2), not by this RFC.
