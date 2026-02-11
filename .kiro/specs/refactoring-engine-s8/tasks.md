# S8: Refactoring Engine — Tasks

| Task | Status | Files | Acceptance |
|------|--------|-------|------------|
| T1: Enhance refactoring.py with long_method, too_many_params, complex_method | **completed** | `analyzers/refactoring.py` | 3 new suggestion types |
| T2: Enhance smell.py with unused_import, long_parameter_list | **completed** | `analyzers/smell.py` | 2 new smell types |
| T3: TDD tests for new refactoring rules | **completed** | `tests/unit/test_refactoring_suggestions.py` | 31 tests (21 new) |
| T4: TDD tests for new smell rules | **completed** | `tests/unit/test_code_smells.py` | 21 tests (10 new) |
| T5: Fix GenericLanguageParser thread-local cloning bug | **completed** | `core/code_map/parallel.py` | No more "Skipping" warnings |
| T6: Full regression | **completed** | `tests/` | 1277 passed, 0 failures |
| T7: Commit and push | **in_progress** | - | - |

## Summary

### New Refactoring Rules (refactoring.py)
| Rule | Threshold | Severity | Description |
|------|-----------|----------|-------------|
| long_method | >50 lines | warning | Extract smaller methods |
| too_many_params | >5 params | info | Introduce parameter object |
| complex_method | >30 lines + >3 params | warning | High complexity, simplify |

### New Code Smells (smell.py)
| Smell | Detection | Severity |
|-------|-----------|----------|
| long_parameter_list | Functions >5 params | warning |
| unused_import | Import names not in symbol/call_site index | info |

### Bug Fix
- Fixed `GenericLanguageParser` thread-local cloning in `parallel.py`
- `type(parser)()` failed for profile-driven parsers; now handles `_profile` attribute

### Test Count
- Before: 1242 passed
- After: 1277 passed (+35 new tests)
- Failures: 0
