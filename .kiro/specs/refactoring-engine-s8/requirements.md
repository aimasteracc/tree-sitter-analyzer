# S8: Refactoring Engine Enhancement — Requirements

## Current State
- `refactoring.py`: 3 rules (remove_dead_code, reduce_coupling, split_module)
- `smell.py`: 3 rules (circular_dependency, god_class, deep_inheritance)
- `risk.py`: Change risk with blast radius scoring
- All exposed via `code_intelligence` MCP tool

## Problem
The refactoring engine lacks detection for the most common code quality issues:
- Long methods (extract method opportunity)
- Too many parameters (parameter object opportunity)
- Unused imports (dead import cleanup)
- Complexity estimation (simplification opportunity)

## Goals
1. Add 4 new refactoring suggestion types
2. Add 2 new code smell types
3. Maintain 0 test failures
4. Keep analyzer functions pure (functional core)

## New Rules

### Refactoring Suggestions (refactoring.py)
| Rule | Threshold | Suggestion |
|------|-----------|------------|
| long_method | >50 lines | "Consider extracting smaller methods" |
| too_many_params | >5 params | "Consider introducing parameter object" |
| complex_method | >30 lines + >3 params | "High complexity; simplify" |

### Code Smells (smell.py)
| Rule | Detection | Severity |
|------|-----------|----------|
| unused_import | Import names not in any symbol/call_site | info |
| long_parameter_list | Functions with >5 params | warning |

## Acceptance Criteria
- [ ] `suggest_refactorings()` returns long_method, too_many_params, complex_method
- [ ] `detect_code_smells()` returns unused_import, long_parameter_list
- [ ] All existing tests pass
- [ ] ≥15 new tests for new rules
- [ ] TOON output correct for all new types
