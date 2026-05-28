# Tasks: Expose ASTCache._get_conn() as Public API

## Background

`ASTCache._get_conn()` is accessed from 20+ files (31 call sites) across the codebase.
Making it public removes SLF001 violations and establishes the SQLite connection accessor
as an intentional API surface.

## Phase 1 — ASTCache public alias (ast_cache.py)

- [x] **P1** Add `ASTCache.get_conn()` → `sqlite3.Connection` public alias for `_get_conn()`

## Phase 2 — Fix all callers

- [x] **F1** Replace all `cache._get_conn()` / `self._cache._get_conn()` / `self.cache._get_conn()` with `get_conn()`
  - Files: call_path.py, class_hierarchy.py, code_similarity.py, codegraph_query_backend.py,
    cross_file_resolver.py, incremental_sync.py, mcp/tools/* (8 files)

## Phase 3 — Tests + Verification

- [x] **T1** Tests for `get_conn()` public alias
- [x] **V1** Run full test suite — 18053 passed, 0 failed
- [x] **V2** Re-run SLF001 scan — eliminated 31 occurrences (144→113)
- [x] **V3** Commit — feature/code-intelligence-architecture
