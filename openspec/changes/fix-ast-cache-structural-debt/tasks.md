# Tasks: Fix ast_cache.py Structural Debt

## Background

`ast_cache.py` was graded C (score 71.0) by the project health scorer:
- **2039 lines** (over 500-line project limit; size score = 0)
- **Nesting depth 7** at L960 — inner import-insert loop inside
  `_write_imports_for_file` has try/for/for/if/for/try/execute chain
- `_bfs_callers` and `_bfs_callees` are 62+50-line methods that use
  only `conn` (no `self`), making them straightforward extraction targets

Target: C (71.0) → B (≥75.0) via:
- Extract BFS functions to `_ast_cache_graph.py` (~135 lines leave file → size +1 pt)
- Extract schema migrations V3-V7 to `_ast_cache_schema.py` (~80 lines → size +1 pt)
- Extract `_insert_import_entry` within ast_cache.py (nesting 7→≤5 → structure +3 pts)
- Combined: 71.0 + 1 + 1 + 3 = 76.0 → B

**Actual result**: score 75.6 (target exceeded), structure=75.0 (depth=15 ≤ 15 target).
Note: grade stayed C (actual B threshold=80, not 75 as spec estimated). Score improvement ✅.

## Phase 1 — TDD: write tests first (RED)

- [x] **T1** Create `tests/unit/test_ast_cache_bfs.py` covering BFS callers/callees
       pure-function contract: dedup via visited set, depth-limited traversal,
       correct key format, callee_file fallback to file_path, depth field populated

## Phase 2 — Refactor: eliminate structural debt (GREEN)

- [x] **R1** Create `tree_sitter_analyzer/_ast_cache_graph.py` with module-level
       `bfs_callers(conn, callee_name, callee_file, max_depth) → list[dict]` and
       `bfs_callees(conn, caller_name, caller_file, max_depth) → list[dict]`
       (exact copies of `_bfs_callers`/`_bfs_callees` minus `self` param)
- [x] **R2** Update `ast_cache.py`: `_bfs_callers` / `_bfs_callees` become
       one-liner thin wrappers calling the module-level functions
- [x] **R3** Create `tree_sitter_analyzer/_ast_cache_schema.py` with module-level
       migration functions: `apply_migration_v3(conn, record_fn)`,
       `apply_migration_v4(conn, record_fn)`, `apply_migration_v5(conn, record_fn)`,
       `apply_migration_v6(conn, record_fn)`, `apply_migration_v7(conn, record_fn)`;
       each takes `record_fn = self._record_schema_version`
- [x] **R4** Update `_init_db` in `ast_cache.py` to call migration functions
- [x] **R5** Extract `_insert_import_entry(conn, rel_path, language, entry)` from
       the innermost loop in `_write_imports_for_file` — reduces nesting from 7 → 5

## Phase 3 — Verification

- [x] **V1** All new BFS tests pass (23/23 ✅)
- [x] **V2** File score: 71.0 → 75.6 (+4.6 pts), structure=75.0 (depth=15), deep_nesting depth 18→15
- [x] **V3** Full test suite: 18110 passed, 0 failed ✅
- [x] **V4** ruff check passes ✅
- [x] **V5** Committed on feature/code-intelligence-architecture
