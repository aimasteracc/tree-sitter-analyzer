# Tasks: Expose ASTCache.get_conn() Public API

## Phase 1 — TDD: Write Failing Test

- [x] **T1** Write test: `ASTCache.get_conn()` exists and returns a `sqlite3.Connection`
  - File: `tests/unit/test_ast_cache.py` — `TestASTCacheGetConnPublicAccessor`
  - 3 tests: returns Connection, same as _get_conn, thread-local stable

## Phase 2 — Implementation

- [x] **I1** Add `get_conn()` to `ASTCache` as public method
  - `_get_conn()` now delegates to `get_conn()` for backward compat
- [x] **I2** Migrate call sites in production code (17 files, 31 call sites)
  - sed replace: all external `._get_conn()` → `.get_conn()`
- [x] **I3** Fix test mocks: 8 files missed in I3 batch
  - `test_xref.py`, `test_symbol_resolver.py` (done in original commit)
  - `test_call_path.py`, `test_codegraph_explore_helpers.py`, `test_codegraph_query_backend.py`
  - `test_codegraph_query_tool_advanced.py`, `test_codegraph_query_tool_core.py`, `test_change_impact_cached_graph.py`
  - Fixed in follow-up commit `64015a21`

## Phase 3 — Verification

- [x] **V1** 249 tests pass (focused: ast_cache, xref, cross_file, symbol_resolver, etc.)
- [x] **V2** Run `uv run python -m tree_sitter_analyzer --change-impact --format json` — 0 changed files (clean tree)
- [x] **V3** Push + PR #201 to develop — CI pending (Lint/Type/Security/E2E all pass)
