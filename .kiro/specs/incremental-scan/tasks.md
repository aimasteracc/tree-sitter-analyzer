# Sprint 3: Incremental Scan — Tasks

## T1: Design & Requirements [completed]
- Created requirements.md with AC1-AC7
- Created design.md with cache structure and algorithm

## T2: TDD RED — Write failing tests [completed]
- test_file_cache_populated_after_scan
- test_cache_entries_have_mtime_ns_and_module
- test_unchanged_file_not_reparsed
- test_project_switch_clears_file_cache
- 4 tests failed (no _file_cache attribute)

## T3: TDD GREEN — Implement caching [completed]
- Added `_FileCache` dataclass (mtime_ns: int, module: ModuleInfo)
- Added `_file_cache` and `_last_project_dir` to ProjectCodeMap.__init__
- Rewrote `scan()` with cache HIT/MISS logic
- File deletion detection via discovered_rel set difference
- All 11 tests pass

## T4: Elite Critic Review [completed]
- P0: mtime float precision → fixed with st_mtime_ns (integer nanoseconds)
- P1: extensions change detection → verified NOT a bug (discovery mechanism handles it)
- P2: _discover_files still runs rglob → noted for future optimization

## T5: TDD RED #2 — Critic-driven tests [completed]
- test_extension_change_triggers_rescan
- test_extension_shrink_removes_files
- test_mtime_backward_triggers_reparse
- All pass after P0 fix

## T6: Full Regression [completed]
- 1008 passed, 4 skipped, 0 failed
- Zero regressions

## Files Modified
- `tree_sitter_analyzer_v2/core/code_map.py` — Added _FileCache, incremental scan()
- `tests/unit/test_incremental_scan.py` — 14 new tests

## Verification
- [x] AC1: Cached scan returns identical results
- [x] AC2: Second scan with 0 changes is fast (cache HIT path)
- [x] AC3: Changed file is re-parsed
- [x] AC4: Deleted file is removed
- [x] AC5: New file is picked up
- [x] AC6: All 1008 existing tests pass
- [x] AC7: 14 new tests cover all scenarios
