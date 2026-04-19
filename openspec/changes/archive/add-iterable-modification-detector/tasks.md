# Iterable Modification in Loop Detector

## Goal
Detect collection modification while iterating over it, which causes RuntimeError or silent bugs.

## MVP Scope
- Detect modifying methods (append, remove, pop, insert, extend, add, discard, update, del) on the iterated collection
- Python-only, for_statement loops
- Report variable, method, severity

## Technical Approach
- BaseAnalyzer pattern, pure AST
- Walk for_statement nodes, extract iteration target
- Scan loop body for method calls on the iterated variable
- Skip nested loops (separate scope)

## Status
DONE - 20 tests, committed
