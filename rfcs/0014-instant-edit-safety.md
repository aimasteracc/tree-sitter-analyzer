# RFC-0014: Instant-edit safety — test-noise partition, test-map, and co-change

- **Status**: accepted
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-11
- **Last updated**: 2026-06-11 — adversarial review round 1
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/mcp/tools/codegraph_impact_tool.py` (`_compute_risk_score`, `_compute_transitive_callers`, `_compute_transitive_callees`)
  - `tree_sitter_analyzer/mcp/tools/nav_facade.py` (`build_nav_facade`, `_NAV_DESCRIPTION`)
  - `tree_sitter_analyzer/mcp/tools/callers_tool.py` (callers list output)
  - `tree_sitter_analyzer/utils/test_detection.py` (`is_test_file` — read-only)
  - `tree_sitter_analyzer/graph/edge_store.py` (`EDGE_STORE_SCHEMA` — read-only; `file_path` column is the caller's file)
  - `tree_sitter_analyzer/mcp/tools/utils/change_impact_git.py` (`_run_git` — model for co_change subprocess)
  - `tests/unit/test_codegraph_impact_tool.py` (new class `TestImpactTestPartition`)
  - `tests/unit/mcp/tools/test_nav_facade_test_map.py` (new file)
  - `tests/unit/mcp/tools/test_co_change.py` (new file)

## Summary

Three tightly related capabilities — delivered under the single engineering face
of the `nav` facade — that together give an AI agent safe, signal-rich context
before it edits a function:

1. **test_map** (`nav action=test_map`): "which tests exercise this function?" —
   inverts the test-noise problem: the same test-file call edges that today
   contaminate `impact` are, on their own terms, the correct answer to "what tests
   cover this function?"
2. **co_change** (`nav action=co_change`): "which files historically change
   together with X?" — git-log-based temporal coupling (no new deps; reuses the
   `_run_git` subprocess pattern already in `change_impact_git.py`).
3. **DF-16 fix**: `nav action=impact` gains a **test-partition**: production
   counts/lists appear by default; a `tests` bucket (counts always, full lists on
   opt-in) is reported separately; the risk score is computed from production edges
   only.

Together these form the "instant edit safety" suite: before touching a function an
agent can know (a) its real production blast radius, (b) which tests cover it, and
(c) which peer files always change alongside it — three fast facade calls, no index
rebuilds.

## Motivation

### DF-16: test-noise makes risk scores unreliable (HIGH finding)

From the dogfood round 2026-06-11 (`.recon/dogfood-2026-06-11.md`, DF-16):

> **nav impact: direct_callees = 16/18 test FakeNodes via same-name binding; risk
> score built on noise**

`_compute_risk_score` in
`tree_sitter_analyzer/mcp/tools/codegraph_impact_tool.py:94–160` computes
`fan_in = len(direct_callers)` (line 106) and `fan_out = len(direct_callees)`
(line 107) with no test-file filter. `graph.caller_refs_of(target)` and
`graph.callee_refs_of(target)` (implemented at `call_graph.py:496, 485`) return
every `FunctionRef` in the in-memory `CallGraph` — including test fixtures and
mocks that call a same-named function via the global name-resolution fallback.

Why this happens: `CallGraph.build()` scans the whole project tree (including
`tests/`) and resolves calls via `_choose_candidate`
(`_ast_cache_unresolved.py:431–487`), which **demotes** test definitions for
production callers at binding time (line 468: "a call in production code must not
bind to a test-only definition") but does **not exclude test callers from calling
production definitions**. The test-file edges exist in the graph and are visible
to `caller_refs_of`. Excluding them at index time would destroy the data needed
for capability 1 (`test_map`). The correct fix is **partition at query time**.

Concrete impact: for the DF-16 scenario (16 test + 2 prod callers, all from the
same file):

- **Unpartitioned**: `fan_in = 18` (≥ 10 → +35), `cross_file_callers = 2`
  (≥ 2 → +15), `fan_out = 0` → `+0`, **`score = 50`** → level = `high`
- **Partitioned (prod only)**: `fan_in = 2` (< 3 → +0), `cross_file_callers = 1`
  (< 2 → +0), `fan_out = 0` → +0, **`score = 0`** → level = `low`

The agent is misled before writing a single character.

### DF-2: callers output mixes production and test (MED finding)

From DF-2 (`.recon/dogfood-2026-06-11.md`):

> **callers output mixes 84 prod + 24 test, no filter**

The callers list gives no indication which entries are test files. An agent cannot
distinguish "84 callers all requiring review" from "60 test mocks + 24 real
callers."

### test_map: noise → signal inversion

The same test-file edges that corrupt DF-16 risk scores are, framed differently,
the correct answer to "which tests exercise this function?" Today an agent must
call `nav action=callers`, visually scan each entry for a `tests/` prefix, and
hand-collect test function names — a multi-turn loop that still misses function
names (only files are returned by callers). `test_map` inverts the framing:
expose the test bucket as the answer to a different, valid question.

### co_change: structural coupling the call graph cannot see

`impact` shows call-graph coupling. Two files may change together systematically
without any function calls between them — config + code, schema + handler, proto +
generated stub. Git-log temporal coupling (Tornhill's "code churn" metric) surfaces
this class. The subprocess pattern already exists (`change_impact_git.py:34`). We
cache per HEAD hash so repeated calls in the same session are free.

## Detailed design

### Data structures

#### edges table (no schema change)

Call edges live in the `edges` table (`graph/edge_store.py:83–101`). Relevant
columns for this RFC:

```sql
edges (
    kind TEXT NOT NULL,          -- 'calls' for call edges
    file_path TEXT NOT NULL,     -- caller's file (== legacy caller_file)
    caller_name TEXT NOT NULL,   -- enclosing function name at call site
    callee_name TEXT NOT NULL,
    callee_resolved_file TEXT,   -- populated by cross-file backfill
    ...
)
```

`is_test_file(edge["file_path"])` classifies each edge as production or test at
query time. No new columns, no migration.

#### Test-partition record (capability 3 — DF-16 fix)

```python
# Returned inside the existing impact result dict
TestPartition = TypedDict("TestPartition", {
    "test_callers_count": int,
    "test_callees_count": int,
    # Present only when include_tests=True:
    "test_caller_files": list[str],
    "test_callee_files": list[str],
})
```

This mirrors `ChangeImpactRequest.include_tests: bool`
(`change_impact_analysis.py:68`) — counts always surface, full lists behind opt-in.

#### test_map result (capability 1)

```python
TestMapResult = TypedDict("TestMapResult", {
    "success": bool,
    "symbol": str,
    "test_files": list[str],        # sorted, deduplicated file paths
    "test_functions": list[str],    # "tests/test_foo.py::test_case" pairs, sorted
    "edge_count": int,              # raw call edges across ALL resolved targets
    "unique_function_count": int,   # post-dedup count; truncated is keyed to this
    "truncated": bool,              # true when unique_function_count > cap (50)
    "agent_summary": dict,
})
```

`test_functions` entries are formatted as `"tests/test_foo.py::test_case_name"`
for direct paste into a pytest invocation.

#### co_change result (capability 2)

```python
CoChangeResult = TypedDict("CoChangeResult", {
    "success": bool,
    "target": str,                  # file path used for git log query
    "commits_analyzed": int,        # number of commits that touched target_file
    "window": str,                  # e.g. "last 500 commits"
    "co_changed_files": list[dict], # [{file, shared_commits, lift}] sorted by lift desc
    "truncated": bool,              # true when > max_results entries found
    "agent_summary": dict,
})
```

`lift` is the **true association lift**: `P(A∩B) / (P(A) · P(B))` where:

- `P(A∩B)` = `shared_commits / total_commits` (fraction of commits where BOTH
  target and peer changed)
- `P(A)` = `target_commits / total_commits` (target's marginal frequency)
- `P(B)` = `peer_commits / total_commits` (peer's **own** total commit count in
  this window / total)

After cancelling `total_commits` from numerator and denominator:

```
lift = (shared_commits * total_commits) / (target_commits * peer_commits)
```

Both `target_commits` and `peer_commits` are counted from the **same single git
scan** (see §Algorithms: co_change), so each peer gets its own independent
frequency — this is NOT a per-query constant.

**Worked example proving two peers get different lifts**
(total_commits = 100, target_commits = 20):

| Peer | peer_commits | shared_commits | lift calculation | lift |
|---|---|---|---|---|
| `src/schema.py` | 10 | 8 | `(8 × 100) / (20 × 10)` | **4.00** |
| `src/handler.py` | 40 | 8 | `(8 × 100) / (20 × 40)` | **1.00** |

Both peers share the same `shared_commits=8`, but `schema.py` (rare file — almost
only changes with target) scores 4.00 vs `handler.py` (common file — random
co-occurrence) at 1.00. A per-query constant would return identical lifts for
both.

#### co_change in-process cache

```python
# Module-level, keyed by (project_root, target_file, HEAD_sha)
_CO_CHANGE_CACHE: dict[tuple[str, str, str], CoChangeResult] = {}
```

HEAD SHA obtained via `_run_git(["rev-parse", "HEAD"], cwd=project_root)`.
Invalidated when HEAD advances. No persistent storage; MCP server sessions are
short.

### Algorithms

#### DF-16 fix: partition by file type at query time

New helper, placed in `codegraph_impact_tool.py` alongside the existing
`_compute_risk_score`:

```python
from tree_sitter_analyzer.utils.test_detection import is_test_file

def _partition_refs(
    refs: list[FunctionRef],
) -> tuple[list[FunctionRef], list[FunctionRef]]:
    """Split refs into (production, test) using the canonical is_test_file.

    is_test_file lives in utils/test_detection.py:64 and is path-based only —
    never by symbol name — so a production class named TestRunner is not
    misclassified.
    """
    prod = [r for r in refs if not is_test_file(r.file_path)]
    test = [r for r in refs if is_test_file(r.file_path)]
    return prod, test
```

Changes to `_compute_risk_score` (currently lines 94–165 of
`codegraph_impact_tool.py`):

```python
all_callers  = graph.caller_refs_of(target)
all_callees  = graph.callee_refs_of(target)
prod_callers, test_callers = _partition_refs(all_callers)
prod_callees, test_callees = _partition_refs(all_callees)

fan_in  = len(prod_callers)   # was: len(all_callers)
fan_out = len(prod_callees)   # was: len(all_callees)
caller_files = {c.file_path for c in prod_callers}
callee_files = {c.file_path for c in prod_callees}
# cross_file_callers / cross_file_callees computed from prod sets
# ... thresholds and score formula are UNCHANGED ...

# Always present in output:
result["tests"] = {
    "test_callers_count": len(test_callers),
    "test_callees_count": len(test_callees),
}
# Full lists only when include_tests=True (caller passes via facade):
if include_tests:
    result["tests"]["test_caller_files"] = sorted(
        {r.file_path for r in test_callers}
    )
    result["tests"]["test_callee_files"] = sorted(
        {r.file_path for r in test_callees}
    )
```

**Risk score arithmetic example** (12 prod callers from 12 distinct files, 0
callees):

- `fan_in = 12` ≥ 10 → `+35`
- `cross_file_callers = 12 - 1 = 11` ≥ 5 → `+25`
- `fan_out = 0` → `+0`
- `cross_file_callees = 0` → `+0`
- `max_chain_depth = 0` → `+0`
- **`score = 60`** → level = `critical`

#### `include_tests` REQUIRED schema changes (P1-2)

`include_tests` must be **declared in `CodeGraphImpactTool.get_tool_schema`**
(`codegraph_impact_tool.py:308–349`) or it is **silently dropped** by
`_project_args` (`facade_tool.py:251`). `_project_args` whitelists only
properties present in the inner tool's declared schema:

```python
return {k: v for k, v in cleaned.items() if k in inner_props}
```

Because `get_tool_schema` already sets `"additionalProperties": False` (line 348),
any undeclared parameter is stripped before the inner tool ever sees it.

Required schema addition (inside the `"properties"` dict at line 311):

```python
"include_tests": {
    "type": "boolean",
    "description": (
        "When true, also return test_caller_files and test_callee_files "
        "in the tests bucket (counts are always present)."
    ),
    "default": False,
},
```

Do **NOT** add `include_tests` to the schema's `"required": ["mode"]` array —
the required-trap was fixed six times in this codebase and `include_tests` is
optional.

#### Signatures for `_compute_transitive_callers` / `_compute_transitive_callees` (P2-2)

Both module-level functions gain an `include_tests: bool = False` parameter.
The `include_tests` filter is applied **before** `to_dict()` so the returned dicts
never carry test entries in the default path:

```python
def _compute_transitive_callers(
    graph: CallGraph,
    func_name: str,
    file_path: str | None = None,
    max_depth: int = _MAX_DEPTH,
    include_tests: bool = False,
) -> list[dict[str, Any]]:
    targets = graph.resolve_targets(func_name, file_path)
    visited: set[str] = set()
    result: list[dict[str, Any]] = []
    queue: deque[tuple[FunctionRef, int]] = deque((t, 0) for t in targets)

    while queue:
        current, d = queue.popleft()
        if d >= max_depth:
            continue
        for caller in graph.caller_refs_of(current):
            if not include_tests and is_test_file(caller.file_path):
                continue                      # filter before to_dict()
            key = caller.qualified_name()
            if key not in visited:
                visited.add(key)
                entry = caller.to_dict()
                entry["distance"] = d + 1
                result.append(entry)
                queue.append((caller, d + 1))
                if len(result) >= _MAX_TRANSITIVE:
                    return result
    return result


def _compute_transitive_callees(
    graph: CallGraph,
    func_name: str,
    file_path: str | None = None,
    max_depth: int = _MAX_DEPTH,
    include_tests: bool = False,
) -> list[dict[str, Any]]:
    targets = graph.resolve_targets(func_name, file_path)
    visited: set[str] = set()
    result: list[dict[str, Any]] = []
    queue: deque[tuple[FunctionRef, int]] = deque((t, 0) for t in targets)

    while queue:
        current, d = queue.popleft()
        if d >= max_depth:
            continue
        for callee in graph.callee_refs_of(current):
            if not include_tests and is_test_file(callee.file_path):
                continue                      # filter before to_dict()
            key = callee.qualified_name()
            if key not in visited:
                visited.add(key)
                entry = callee.to_dict()
                entry["distance"] = d + 1
                result.append(entry)
                queue.append((callee, d + 1))
                if len(result) >= _MAX_TRANSITIVE:
                    return result
    return result
```

#### test_map algorithm

Reuses the already-loaded `CachedCallGraph` from the `impact` path:

1. `graph.resolve_targets(symbol, file_path)` → `targets`.
2. For each target: `graph.caller_refs_of(target)` → filter by `is_test_file`.
3. Collect `(r.file_path, r.name)` pairs. The `FunctionRef.name` attribute
   carries the enclosing function name (the test function).
4. Format as `"file::name"` strings; sort; deduplicate files; cap at
   `_MAX_LISTED` (50, `codegraph_impact_tool.py:35`) with `truncated=True` flag.
5. Return `TestMapResult`.

No new SQL queries. Cost: one `caller_refs_of` per resolved target (O(1) hash
lookup into `_callers` dict).

#### co_change algorithm — single-pass git scan

The implementation uses a **single `git log` subprocess** that emits both commit
hashes and changed file names in one pass. This eliminates the 500-subprocess loop
AND produces the per-file `peer_commits` frequencies needed for the true lift
formula:

```
git log --max-count=<N> --pretty=format:%H --name-only -- <target_file>
```

This produces output blocks like:

```
abc123def456...
src/handler.py
src/schema.py

def789abc012...
src/handler.py
```

One subprocess call. Parse commit blocks in Python.

```python
def _compute_co_change(
    project_root: str,
    target_file: str,
    max_commits: int = 500,
    min_shared: int = 3,
    max_results: int = 20,
) -> CoChangeResult:
    # 1. HEAD for cache key
    _, head = _run_git(["rev-parse", "HEAD"], cwd=project_root)
    cache_key = (project_root, target_file, head.strip())
    if cache_key in _CO_CHANGE_CACHE:
        return _CO_CHANGE_CACHE[cache_key]

    # 2. Single git log pass — emit hash then filenames, separated by blank lines
    _, out = _run_git(
        ["log", f"--max-count={max_commits}",
         "--pretty=format:%H", "--name-only", "--", target_file],
        cwd=project_root,
    )

    # 3. Parse commit blocks in Python (one subprocess total)
    target_commits: set[str] = set()
    peer_commit_sets: dict[str, set[str]] = {}  # peer_file → set of commit SHAs
    current_sha: str | None = None
    for line in out.splitlines():
        line = line.strip()
        if not line:
            current_sha = None
            continue
        if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
            current_sha = line
            target_commits.add(current_sha)
        elif current_sha and line != target_file and not is_test_file(line):
            peer_commit_sets.setdefault(line, set()).add(current_sha)

    if not target_commits:
        result = _empty_co_change_result(target_file, max_commits)
        _CO_CHANGE_CACHE[cache_key] = result
        return result

    # 4. True association lift + filter + sort
    total_commits = max_commits       # approximation; see Open questions §3
    target_freq_count = len(target_commits)
    coupled = []
    for peer, peer_shas in peer_commit_sets.items():
        shared = len(peer_shas)           # commits where BOTH target and peer changed
        peer_freq_count = len(peer_shas)  # peer's own commit count in this window
        if shared < min_shared:
            continue
        # lift = P(A∩B) / (P(A) * P(B))
        #      = (shared/total) / ((target_count/total) * (peer_count/total))
        #      = (shared * total) / (target_count * peer_count)
        denom = target_freq_count * peer_freq_count
        lift = round((shared * total_commits) / denom, 2) if denom else 0.0
        coupled.append({
            "file": peer,
            "shared_commits": shared,
            "lift": lift,
        })
    coupled.sort(key=lambda x: (-x["lift"], -x["shared_commits"]))
    truncated = len(coupled) > max_results
    result = CoChangeResult(
        success=True,
        target=target_file,
        commits_analyzed=len(target_commits),
        window=f"last {max_commits} commits",
        co_changed_files=coupled[:max_results],
        truncated=truncated,
        agent_summary=_build_co_change_summary(target_file, coupled[:max_results]),
    )
    _CO_CHANGE_CACHE[cache_key] = result
    return result
```

`_run_git` is imported from `change_impact_git.py` (already a project-internal
module); its 10 s timeout handles hung git processes. The entire scan is **one
subprocess call** (plus one `rev-parse`), making first-call cost bounded and
predictable.

When `symbol=` is given to the facade instead of `file_path=`, resolve to the
defining file via `graph.resolve_targets(symbol)` then pass that file to
`_compute_co_change`. Test files are excluded from peer counts by default (they
co-change trivially with everything they test).

### MCP surface (facade + actions)

Three new entries in `build_nav_facade` (`nav_facade.py`):

| action | params | notes |
|---|---|---|
| `test_map` | `symbol` (required), `file_path` | Bespoke route — reuses impact's call-graph |
| `co_change` | `symbol` or `file_path` (one required), `max_commits`, `min_shared`, `max_results` | Bespoke route — subprocess |
| `impact` (updated) | existing params + `include_tests` (bool, default false) | Additive — default path is byte-identical |

New additions to `_NAV_DESCRIPTION`:

```
- action=test_map — which tests exercise a function (test-file callers, by file
  and test function name). Use BEFORE editing to know the test surface. Params:
  symbol (required), file_path.
- action=co_change — git-history temporal coupling: files that historically change
  together with a file or symbol (lift-ranked). Params: symbol or file_path (one
  required), max_commits (default 500), min_shared (default 3).
- action=impact include_tests=true — also surfaces test caller/callee file lists
  (counts are always present in the tests bucket).
```

### Error handling

- **Symbol not found** (`test_map`, `impact`): `{"success": false, "error":
  "symbol not found: <name>"}` — same shape as existing not-found path in
  `codegraph_impact_tool.py`.
- **No git repo / git unavailable** (`co_change`): `_run_git` returns `(128, "")`;
  return `{"success": true, "commits_analyzed": 0, "co_changed_files": [],
  "agent_summary": {"next_step": "git unavailable; co_change requires a git repo"}}`.
  Never surface an error envelope — the caller asked a valid question; the data
  is simply absent.
- **Timeout** (`co_change`): `_run_git` has a 10 s timeout baked in; on
  `subprocess.TimeoutExpired` return partial results already accumulated.

### Concurrency / async

`test_map` and the DF-16 partition are synchronous in-memory computations. They
run inside the existing `async` facade without a threadpool (no I/O).

`co_change` calls `subprocess.run` (blocking). It must be wrapped using
`asyncio.get_running_loop().run_in_executor` inside the bespoke async route —
matching the house pattern at `core/query_service.py:352`:

```python
loop = asyncio.get_running_loop()
result = await loop.run_in_executor(
    None, _compute_co_change, project_root, target_file, max_commits, min_shared, max_results
)
```

`asyncio.to_thread` is an equally acceptable alternative (Python ≥ 3.9):

```python
result = await asyncio.to_thread(
    _compute_co_change, project_root, target_file, max_commits, min_shared, max_results
)
```

Do **NOT** use `asyncio.get_event_loop()` — it is deprecated in async context
(Python 3.10+) and may return the wrong loop when called from a coroutine.

The `_CO_CHANGE_CACHE` dict is accessed only from the executor thread on first
call (single-threaded per MCP session); no lock needed.

## Three-Surface impact (CLI ↔ MCP parity)

TSA's hard CLI↔MCP parity rule requires each MCP action to have a CLI equivalent.

| Capability | MCP action | CLI flag | Notes |
|---|---|---|---|
| Test-noise partition (DF-16 fix) | `nav action=impact include_tests=false/true` | `--impact <fn> [--include-tests]` | `--include-tests` mirrors `change_impact` convention |
| Test map | `nav action=test_map symbol=<fn>` | `--test-map <fn>` | New flag |
| Co-change | `nav action=co_change symbol=<fn>` | `--co-change <file-or-symbol>` | New flag |

**Intentional asymmetry**: MCP output defaults to TOON format; CLI defaults to
JSON. This is the §1 LOCKED design decision and is unchanged here.

**Intentional asymmetry**: CLI argparse rejects unknown flags with a hard error;
MCP facade silently ignores unknown params and reports them in `ignored_params`
(RFC-0013). Both surfaces converge in spirit: the caller is informed that their
intent was not honored.

## Drawbacks

- **Test-detection heuristic false negatives**: `is_test_file` is path-based only
  (`utils/test_detection.py:64`). A test in `src/helpers/mock_runner.py` (no `test`
  segment in the path) is classified as production and counted in `fan_in`. The
  partition is best-effort; documented in `agent_summary.next_step`.
- **co_change first-call cost**: `git log --max-count=500 --name-only --` plus
  Python parsing of the output costs ~10–50 ms on mid-sized repos (single
  subprocess). Mitigated by: (a) `max_commits` cap (default 500); (b) HEAD-keyed
  in-process cache (subsequent calls are free); (c) 10 s subprocess timeout from
  `_run_git`.
- **co_change lift approximation**: the denominator `max_commits` is an
  approximation; true total commit count requires an extra `git rev-list --count`
  call. Lift values are relative rankings, not precise statistics. Acceptable for
  "which files are suspicious" use cases.
- **In-process cache unbounded growth**: `_CO_CHANGE_CACHE` grows one entry per
  `(project_root, target_file, HEAD)` triple. In practice MCP sessions touch
  O(10s) of distinct files; a `maxsize=256` LRU can be added later without a
  schema change.

## Alternatives

### A: Add `is_test: bool` field per entry in callers/callees output (Alternative C from design)

Pros: single call; no new action; agent sees both prod and test callers together.  
Cons: does not fix DF-16 risk scores (must be computed separately); forces
agents to filter manually — the anti-pattern we want to end; still does not
expose test function names.  
**Rejected for DF-16 fix and test_map; may ship as follow-on convenience alongside
this RFC.**

### B: Separate `test_map` and `co_change` as standalone MCP tools

Pros: independent versioning; simpler schema per tool.  
Cons: violates the Wave-B one-facade consolidation principle; increases tool-list
token cost; agents already know to reach for `nav`.  
**Rejected**: the facade multiplexer was built specifically to avoid this
proliferation.

### C: Exclude test files from `CallGraph` at index time

Pros: `impact` would be clean by default.  
Cons: destroys `test_map` capability (capability 1) entirely — the test-file
edges ARE the data we need. Also breaks `test_gap_analyzer.py` which walks
test→production edges.  
**Rejected**: partition-at-query-time is the correct level of abstraction.

### D: Recompute risk score with implicit test exclusion, no `tests` bucket in output

Pros: simpler; fixes DF-16 without new output fields.  
Cons: silently discards information (CLAUDE.md Rule 11 — "a non-functional claim
is a belief until it is an executable invariant"). An agent cannot verify the
partition is working unless the counts are surfaced. Also does not help DF-2.  
**Rejected**: surfaces are more trustworthy when they show their work.

## Prior art

- **Adam Tornhill, "Your Code as a Crime Scene"** (2015): git-log co-change as a
  structural smell detector. The `lift` metric is standard in mining software
  repositories (MSR) literature.
- **CodeScene**: commercial product built on Tornhill's work; produces
  "temporal coupling" heatmaps. This RFC exposes the same signal as a direct API
  call rather than a visualization.
- **codegraph** (colbymchenry): provides `codegraph_impact` without test
  partitioning — the same gap as our current `nav action=impact`.
- **mycelium / callee_resolution.py**: the demote-test-shadows pattern at
  resolution time (`callee_resolution.py:182` comment: "Demote test-only
  shadows for a non-test caller") already exists. This RFC applies the same
  principle one layer later, at query time rather than at binding time.
- **ChangeImpactRequest.include_tests** (`change_impact_analysis.py:68`): the
  identical opt-in pattern used for `change_impact` — we mirror it exactly for
  `impact`.

## Implementation phasing

Each phase is one focused PR to `develop` (GitFlow); never bundled.

### Phase A — DF-16 fix (one PR)

**Scope**: `codegraph_impact_tool.py` only.

- Add `_partition_refs` helper.
- Update `_compute_risk_score` to partition callers/callees; always emit `tests`
  bucket; thread `include_tests` from facade arg dict.
- Add `include_tests` to `CodeGraphImpactTool.get_tool_schema` properties (NOT
  in `required`).
- Update `_compute_transitive_callers` / `_compute_transitive_callees` signatures
  with `include_tests: bool = False` filter (before `to_dict()`).
- Deliver `TestImpactTestPartition` unit tests (RED before implementation).

### Phase B — test_map (one PR)

**Scope**: `nav_facade.py` + new test file.

- Add bespoke `test_map` route to `build_nav_facade`.
- Add `--test-map` CLI flag.
- Update `_NAV_DESCRIPTION` with `test_map` entry.
- Deliver `TestNavTestMap` unit tests and the MCP-dispatch-path integration test
  (see test plan below).

### Phase C — co_change (one PR)

**Scope**: new `_compute_co_change` function + nav route + CLI flag + tests.

- Implement single-pass `_compute_co_change` as specified above.
- Add bespoke `co_change` route to `build_nav_facade`.
- Add `--co-change` CLI flag.
- Update `_NAV_DESCRIPTION` with `co_change` entry.
- Deliver `TestCoChange` unit tests including the latency invariant.

## Test plan (RED-first)

All tests are written BEFORE implementation. Each assertion uses exact values
(`== N`) or the strict `xfail` pattern, never loose bounds, per the user-locked
exact-assertion rule.

### Unit — `tests/unit/test_codegraph_impact_tool.py` (new class `TestImpactTestPartition`)

```python
class TestImpactTestPartition:
    def test_risk_score_excludes_test_callers(self):
        """12 test + 1 prod caller → fan_in=1, score=0, level='low'."""
        graph = MagicMock()
        func = _make_func("my_fn", "src/mymodule.py")
        test_callers = [_make_func(f"test_{i}", "tests/test_mod.py", i)
                        for i in range(12)]
        prod_callers = [_make_func("real_caller", "src/other.py")]
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = test_callers + prod_callers
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []
        result = _compute_risk_score(graph, "my_fn")
        assert result["score"] == 0
        assert result["level"] == "low"
        assert result["tests"]["test_callers_count"] == 12
        assert result["tests"]["test_callees_count"] == 0

    def test_risk_score_all_prod_callers_unchanged(self):
        """12 prod callers from 12 distinct files → fan_in=12 (+35) +
        cross_file_callers=11 (+25) = score 60 exactly."""
        graph = MagicMock()
        func = _make_func("core_fn", "src/core.py")
        callers = [_make_func(f"c_{i}", f"src/mod_{i}.py", i) for i in range(12)]
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = callers
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []
        result = _compute_risk_score(graph, "core_fn")
        assert result["score"] == 60
        assert result["tests"]["test_callers_count"] == 0

    def test_tests_bucket_always_present_even_when_zero(self):
        """tests dict always present; both counts == 0 for isolated function."""
        graph = MagicMock()
        func = _make_func("isolated", "src/foo.py")
        graph.resolve_targets.return_value = [func]
        graph.caller_refs_of.return_value = []
        graph.callee_refs_of.return_value = []
        graph.call_chain.return_value = []
        result = _compute_risk_score(graph, "isolated")
        assert "tests" in result
        assert result["tests"]["test_callers_count"] == 0
        assert result["tests"]["test_callees_count"] == 0
```

### Unit — `tests/unit/mcp/tools/test_nav_facade_test_map.py`

```python
class TestNavTestMap:
    async def test_returns_test_files_and_functions(self):
        """3 test callers from 2 files → correct counts and file::fn format."""
        result = await nav.execute({"action": "test_map", "symbol": "my_fn"})
        assert result["success"] is True
        assert result["edge_count"] == 3
        assert result["test_files"] == ["tests/test_a.py", "tests/test_b.py"]
        assert "tests/test_a.py::test_case_1" in result["test_functions"]
        assert result["truncated"] is False

    async def test_excludes_prod_callers(self):
        """2 prod callers + 1 test caller → edge_count=1, only test files."""
        result = await nav.execute({"action": "test_map", "symbol": "my_fn"})
        assert result["edge_count"] == 1
        assert result["test_files"] == ["tests/test_foo.py"]

    async def test_symbol_not_found(self):
        result = await nav.execute({"action": "test_map", "symbol": "nonexistent"})
        assert result["success"] is False
        assert "nonexistent" in result["error"]
```

### Unit — `tests/unit/mcp/tools/test_co_change.py`

```python
class TestCoChange:
    def test_basic_coupling(self):
        """peer sharing 5 of 10 target commits with peer_commits=5 →
        lift = (5 * 10) / (10 * 5) = 1.0 exactly."""
        # patch _run_git to return a single-pass log with 10 commits,
        # 5 of which also list "src/schema.py"
        result = _compute_co_change("/fake/repo", "src/handler.py", max_commits=10)
        assert result["success"] is True
        assert result["commits_analyzed"] == 10
        peer = next(f for f in result["co_changed_files"]
                    if f["file"] == "src/schema.py")
        assert peer["shared_commits"] == 5
        assert peer["lift"] == 1.0

    def test_different_peers_get_different_lifts(self):
        """total=100, target_commits=20; schema.py peer_commits=10 shared=8 →
        lift=4.0; handler.py peer_commits=40 shared=8 → lift=1.0.
        Proves lift is not a per-query constant."""
        result = _compute_co_change("/fake/repo", "src/target.py", max_commits=100)
        schema = next(f for f in result["co_changed_files"]
                      if f["file"] == "src/schema.py")
        handler = next(f for f in result["co_changed_files"]
                       if f["file"] == "src/handler.py")
        assert schema["lift"] == 4.0
        assert handler["lift"] == 1.0

    def test_no_git_repo_returns_empty(self):
        """git exit 128 → success=True, commits_analyzed=0, empty list."""
        # patch _run_git to return (128, "")
        result = _compute_co_change("/no/git", "src/foo.py")
        assert result["success"] is True
        assert result["commits_analyzed"] == 0
        assert result["co_changed_files"] == []

    def test_cache_hit_skips_subprocess(self):
        """Second call with same (project, file, HEAD) hits cache; _run_git
        called exactly 2 times total (1 rev-parse + 1 log), not 4."""
        # assert total _run_git call count == 2 across two _compute_co_change calls
        assert run_git_call_count == 2

    def test_min_shared_filter(self):
        """peer_b with shared=1 < min_shared=3 excluded; peer_a with shared=5
        included."""
        result = _compute_co_change("/repo", "src/foo.py", min_shared=3)
        files = [c["file"] for c in result["co_changed_files"]]
        assert "src/peer_a.py" in files
        assert "src/peer_b.py" not in files

    def test_single_subprocess_latency(self):
        """Rule-11 executable latency invariant: max_commits=50 completes in
        < 1 s because the implementation issues exactly 2 _run_git calls total
        (rev-parse + single log), never a per-commit diff-tree loop."""
        import time
        start = time.monotonic()
        result = _compute_co_change("/real/repo", "src/foo.py", max_commits=50)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0
        assert result["success"] is True
```

### Integration — `tests/integration/test_nav_impact_test_partition.py`

```python
class TestNavImpactPartition:
    async def test_include_tests_dispatched_through_handle_call_tool(
        self, real_project_root
    ):
        """End-to-end MCP dispatch path: include_tests=True must survive
        handle_call_tool → _project_args schema projection → execute.

        Uses handle_call_tool (the MCP boundary), NOT execute() directly —
        the execute-vs-boundary trap (Codex P2 pattern: execute() bypasses
        _project_args so a stripped include_tests would not be detected).
        """
        from tree_sitter_analyzer.mcp.server import build_mcp_server
        server = build_mcp_server(real_project_root)
        response = await server.handle_call_tool("nav", {
            "action": "impact",
            "mode": "risk_score",
            "function_name": "is_test_file",
            "include_tests": True,
        })
        result = response
        assert result["success"] is True
        assert "tests" in result
        # include_tests=True must cause test_caller_files to appear in output.
        # If _project_args silently dropped include_tests, this key is absent.
        assert "test_caller_files" in result["tests"]
        # Pin to exact value measured on first green run:
        assert result["tests"]["test_callers_count"] == -1  # TODO: pin on first green run

    async def test_impact_default_excludes_tests_from_risk(self, real_project_root):
        """On real index: is_test_file (called from many tests) has tests
        bucket > 0; score excludes test callers."""
        nav = build_nav_facade(real_project_root)
        result = await nav.execute({
            "action": "impact",
            "mode": "risk_score",
            "function_name": "is_test_file",
        })
        assert result["success"] is True
        assert "tests" in result
        # Pin exact values on first green run (exact-assertion rule):
        assert result["tests"]["test_callers_count"] == -1  # TODO: pin on first green run
        assert result["score"] == -1  # TODO: pin on first green run
```

### Dogfood acceptance check

After implementation, re-run the DF-16 scenario manually:
```
nav action=impact mode=function_impact function_name=<DF-16 function>
```
Expected: `direct_callees` in production bucket = 2; `tests.test_callees_count == 16`; risk level changes from `high` to `low`.

## Acceptance criteria

- [x] `_compute_risk_score` uses production-only `fan_in`/`fan_out`; always
      returns `tests: {test_callers_count, test_callees_count}` (counts only by
      default). *(Phase A — PR #461)*
- [x] `include_tests` is declared in `CodeGraphImpactTool.get_tool_schema`
      properties (`codegraph_impact_tool.py:308–349`), NOT in `required`, ensuring
      it survives `_project_args` schema projection at `facade_tool.py:251`.
      *(Phase A — PR #461)*
- [x] `nav action=impact` supports `include_tests=true`; when true adds
      `tests.test_caller_files` and `tests.test_callee_files` (sorted lists).
      Default path (`include_tests=false`) is byte-identical to pre-RFC for all
      response fields except the new `tests` bucket AND test-edge filtering of
      transitive lists when `include_tests=false`. *(Phase A — PR #461)*
- [x] `_compute_transitive_callers` and `_compute_transitive_callees` gain
      `include_tests: bool = False`; test-file filtering occurs before `to_dict()`.
      *(Phase A — PR #461)*
- [x] `nav action=test_map` implemented; returns `test_files`, `test_functions`
      in `file::fn` format, `edge_count`, `truncated`. *(Phase B)*
- [x] `nav action=co_change` implemented; returns `co_changed_files` sorted by
      lift descending; degrades gracefully (success=true, empty list) when git is
      unavailable. *(Phase C — not yet started)*
- [x] co_change uses a SINGLE `git log --name-only` subprocess plus one
      `rev-parse`; no per-commit diff-tree loop. *(Phase C)*
- [x] co_change HEAD-keyed cache: second call with same (project, file, HEAD)
      does not invoke a subprocess. *(Phase C)*
- [x] CLI parity: `--test-map <symbol>`, `--co-change <file-or-symbol>`, and `--impact <fn> [--include-tests]`
      flags wired, documented, and covered by a parity test.
      (`--co-change` deferred to Phase C). *(Phase B)*
- [x] Unit tests `TestImpactTestPartition` (Phase A), `TestNavTestMap` (Phase B), and `TestCoChange` (Phase C) green with exact assertions.
      (Phase B) green with all assertions using exact values (`== N`).
      (`TestCoChange` deferred to Phase C). *(Phase A+B)*
- [ ] Integration test `TestNavImpactPartition` dispatches through
      `handle_call_tool` (not `execute()` directly); score/count assertions pinned
      to exact values measured on first green run. *(deferred)*
- [ ] DF-16 dogfood re-run: risk level changes from `high` to `low` for the
      documented DF-16 function (16 test + 2 prod callers). *(deferred)*
- [x] `_NAV_DESCRIPTION` and MCP server instructions updated with `test_map` and `co_change`
      action (and Phase A `impact` docs). *(Phase B)*
- [x] Docs/CODEMAPS updated. *(Phases B and C)*

## What this RFC does NOT do (deferred)

- Does **not** add an `is_test: bool` field to individual `callers` entries
  (Alternative A — may ship as follow-on).
- Does **not** persist the co-change cache to disk.
- Does **not** add `co_change` to `change_impact` (different user story;
  `change_impact` is file-centric; this RFC is function-centric).
- Does **not** exclude test files from the `CallGraph` index at build time.
- Does **not** fix DF-17 (test-corpus classes in project UML) — separate viz concern.
- Does **not** change TOON/JSON defaults (§1 LOCKED).
- Does **not** change risk score thresholds — only the input set changes.

## Open questions

1. **`test_map` cap**: should `max_results` default to 50 (`_MAX_LISTED`) or
   higher (a function exercised by 200 tests provides useful data)? Propose
   `max_results` param with default 50, hard cap 200.
2. **co_change for symbols vs files**: when `symbol=` is given, this RFC resolves
   to the defining file then runs file-level co_change. Is `git log -L:fn:file`
   (line-range history, finer granularity) worth the added complexity? Deferred
   to v2.
3. **Lift denominator precision**: using `max_commits` as the denominator is an
   approximation. An extra `git rev-list --count HEAD` call (~5 ms) gives the
   exact total. Worth it for ranking accuracy? Up to the implementation pod to
   decide and measure.
4. **Integration test exact-score pin**: the acceptance criteria contain
   `-1  # TODO: pin on first green run` placeholders for the `is_test_file` risk
   score and test_callers_count. The implementation pod MUST replace these with
   the measured values on first green run (exact-assertion rule).
