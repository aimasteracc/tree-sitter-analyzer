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
- [x] Remove test_javascript_plugin_coverage_boost.py (already rewritten with 905 lines on remote)

### 2. test_conftest_query.py — add test functions
- [x] Already fixed on remote (8 tests, 14 asserts, density 1.74)

### 3. test_tree_sitter_compat_coverage_boost.py — add assertions
- [x] Add 2+ assert calls to existing test methods → density ≥ 1.0

### 4. test_logging.py — add assertions
- [x] Add 12+ assert calls across existing test methods

### 5. test_logging_coverage.py — add assertions
- [x] Add 7+ assert calls across existing test methods

## Gates
- [x] ruff check passes
- [x] pytest 134/134 passes
