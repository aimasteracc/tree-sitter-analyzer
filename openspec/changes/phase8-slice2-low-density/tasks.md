# Phase 8 Slice 2: Fix Low Assertion Density

## Goal
Fix 5 test files with assertion density < 1.0 (gate: ≥ 1.0).

Formula: density = asserts / max(tests, 1)

## Current state (2026-05-12)

| File | Lines | Tests | Asserts | Density | Gap |
|------|-------|-------|---------|---------|-----|
| test_logging.py | 746 | 66 | 55 | 0.83 | +11 |
| test_logging_coverage.py | 397 | 46 | 30 | 0.65 | +16 |
| test_tree_sitter_compat_coverage_boost.py | 162 | 22 | 21 | 0.95 | +1 |
| test_conftest_query.py | 73 | 0 | 0 | 0.00 | +5 |
| test_javascript_plugin_coverage_boost.py | 0 | 0 | 0 | 0.00 | delete |

## Tasks

### 1. Delete empty file
- [ ] Remove test_javascript_plugin_coverage_boost.py (0 lines, 0 tests)

### 2. test_conftest_query.py — add test functions
- [ ] Add 5-6 test functions that use existing fixtures (QueryExecutor, QueryService, QueryFilter)
- [ ] Ensure each test has at least 1 assert → density ≥ 1.0

### 3. test_tree_sitter_compat_coverage_boost.py — add assertions
- [ ] Add 2+ assert calls to existing test methods → density ≥ 1.0

### 4. test_logging.py — add assertions
- [ ] Add 11+ assert calls across existing test methods
- [ ] Focus on tests with 0-1 assertions

### 5. test_logging_coverage.py — add assertions
- [ ] Add 16+ assert calls across existing test methods
- [ ] Focus on tests with 0-1 assertions

## Gates
- [ ] test_mastery_scan.py --gates: low-density count = 0
- [ ] ruff check passes
- [ ] pytest tests/unit/utils/test_logging.py tests/unit/utils/test_logging_coverage.py tests/unit/utils/test_tree_sitter_compat_coverage_boost.py tests/unit/core/test_conftest_query.py passes
