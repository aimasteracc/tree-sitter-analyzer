# Tasks: Expose CallGraph Internal Methods — Phase 2

## Phase 1 — Implementation (add public aliases)

- [x] **A1** `CallGraph.find_enclosing_func()` — public alias for `_find_enclosing_func`
  - File: `tree_sitter_analyzer/call_graph.py`
- [x] **A2** `CallGraph.resolve_callee()` — public alias for `_resolve_callee`
  - File: `tree_sitter_analyzer/call_graph.py`
- [x] **A3** `CallGraph.is_excluded()` — public alias for `_is_excluded`
  - File: `tree_sitter_analyzer/call_graph.py`
- [x] **A4** `CallGraph.iter_source_files()` — public alias for `_iter_source_files`
  - File: `tree_sitter_analyzer/call_graph.py`
- [x] **A5** `CallGraph.is_built` — `@property` exposing `_built` flag
  - File: `tree_sitter_analyzer/call_graph.py`

## Phase 2 — Migrate tests

- [x] **T1** `test_call_graph_integration.py` — replace all `cg._find_enclosing_func` calls
- [x] **T2** `test_call_graph_integration.py` — replace all `cg._resolve_callee` calls
- [x] **T3** `test_call_graph_integration.py` — replace `cg._is_excluded` and `cg._iter_source_files`
- [x] **T4** `test_call_graph_integration.py` — replace `cg._built` reads with `cg.is_built`
- [x] **T5** `test_call_graph_cached.py` — replace `cg._built` reads with `cg.is_built`
- [x] **T6** `test_call_graph_cached.py` — replace `cg.call_edges() is cg._call_edges` with data contract check
- [x] **T7** `test_call_graph_cached.py` — replace `cg.function_refs() is cg._functions` with data contract check
- [x] **T8** `test_call_graph_cached.py` — add comment on write-to-private test setup

## Phase 3 — Verification

- [x] **V1** `uv run pytest tests/unit/test_call_graph_integration.py tests/unit/test_call_graph_cached.py -x -q` → 62 passed
- [x] **V2** Full suite (change-impact scope) → 200 passed
- [x] **V3** Push + PR to develop
