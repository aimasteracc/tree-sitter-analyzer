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
- [x] **I3** Fix test mocks: `test_xref.py` + `test_symbol_resolver.py` MockCache

## Phase 3 — Verification

- [x] **V1** 249 tests pass (focused: ast_cache, xref, cross_file, symbol_resolver, etc.)
- [ ] **V2** Run `uv run python -m tree_sitter_analyzer --change-impact --format json`
- [ ] **V3** Push + PR to develop
