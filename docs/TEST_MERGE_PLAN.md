# Test Architecture Phase 2: File Merge Plan

## Baseline Metrics (2026-03-22)

| Metric | Value |
|--------|-------|
| Files in unit/core | 75 |
| Tests in unit/core | 716 passed, 13 failed, 1 skipped |
| Test runtime | 6.10s |
| Failing tests | 13 (file_output related) |

## Merge Groups

### Group 1: Engine Tests (5 files → 1 file)

**Files to merge:**
- `test_engine.py` (8 tests)
- `test_core_engine_comprehensive.py` (21 tests)
- `test_core_engine_extended.py` (15 tests)
- `test_engine_unification.py` (6 tests)
- `test_analysis_engine.py` (39 tests)

**Target:** `tests/unit/core/test_engine.py` (89 tests)

**Merge strategy:**
1. Keep `test_analysis_engine.py` as base (most comprehensive)
2. Move unique tests from other 4 files
3. Remove duplicate initialization tests
4. Organize by test class: Init, Analysis, Cache, Performance, Security

### Group 2: Query Tests (5 files → 1 file)

**Files to merge:**
- `test_query.py`
- `test_core_query_comprehensive.py`
- `test_core_query_coverage.py`
- `test_core_query_extended.py`
- `test_core_query_filter.py`
- `test_core_query_service.py`
- `test_query_service.py`
- `test_query_service_coverage.py`

**Target:** `tests/unit/core/test_query.py`

### Group 3: Language Detection Tests (4 files → 1 file)

**Files to merge:**
- `test_language_detector.py`
- `test_language_detector_extended.py`
- `test_language_detector_html_css.py`
- `test_language_detector_markdown.py`

**Target:** `tests/unit/core/test_language_detector.py`

### Group 4: Parser Tests (2 files → 1 file)

**Files to merge:**
- `test_parser.py`
- `test_tree_sitter_integration.py`
- `test_tree_sitter_compat.py`
- `test_tree_sitter_compat_coverage.py`
- `test_tree_sitter_compat_properties.py`

**Target:** `tests/unit/core/test_parser.py`

### Group 5: Exception Tests (3 files → 1 file)

**Files to merge:**
- `test_exceptions.py`
- `test_exceptions_extended.py`
- `test_exceptions_comprehensive.py`

**Target:** `tests/unit/core/test_exceptions.py`

### Group 6: Cache Tests (3 files → 1 file)

**Files to merge:**
- `test_cache_service.py`
- `test_cache_logic_only.py`
- `test_encoding_cache.py`

**Target:** `tests/unit/core/test_cache.py`

### Group 7: Language-Specific Query Tests (Keep Separate)

**Do NOT merge:** Each language has its own query tests
- `test_queries_python.py`
- `test_queries_javascript.py`
- `test_queries_typescript.py`
- `test_queries_java.py`
- etc.

These test different language grammars and should remain separate.

## Execution Order

1. **Fix failing tests first** - 13 file_output tests are failing
2. **Merge Group 1** (Engine) - highest impact
3. **Merge Group 2** (Query) - high impact
4. **Merge Groups 3-6** (smaller merges)
5. **Verify coverage** after each merge

## Rollback Strategy

Before each merge:
```bash
git checkout -b backup/pre-merge-group-N
git push origin backup/pre-merge-group-N
```

If merge fails:
```bash
git checkout main
git checkout -b refactor/fix-merge-group-N
# Fix issues
```
