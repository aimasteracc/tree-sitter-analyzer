# Tasks - Test Quality Audit and Improvement

## Work Breakdown Structure

| ID | Task | Objective | Files to Modify | Status |
|----|------|-----------|-----------------|--------|
| T1 | Comprehensive Coverage Audit | Map every test file to its target source file | N/A | completed |
| T2 | Consolidate Language Query Tests | Merge shallow key checks into single tests | `tests/unit/core/test_query.py` | completed |
| T3 | Prune Redundant Exception Tests | Merge `test_exceptions.py` and `test_exceptions_comprehensive.py` | `tests/unit/core/test_exceptions.py` | completed |
| T4 | Boost Core Engine Coverage | Add real integration tests for `UnifiedAnalysisEngine` | `tests/integration/core/test_engine_integration.py` | completed |
| T5 | Functional CLI Testing | Add real tests for CLI commands without mocks | `tests/integration/cli/test_cli_functional.py` | completed |
| T6 | Final Cleanup | Delete the identified "Lan Yu Chong Shu" test files | N/A | completed |

## Testing Plan
1. **Regression Check**: Every time a test file is deleted, run `pytest` to ensure coverage % doesn't drop.
2. **Quality Check**: Verify that new tests fail when bugs are introduced (mutation testing principle).
