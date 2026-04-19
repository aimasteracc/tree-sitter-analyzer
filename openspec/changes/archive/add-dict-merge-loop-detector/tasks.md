# Dict Merge in Loop Detector

## Goal
Detect dict key assignment inside loops that should use dict.update() for better performance.

## MVP Scope
- Detect `d[key] = value` inside for/while loops in Python
- Report dict variable, loop type, severity
- Single Sprint, Python-only

## Technical Approach
- BaseAnalyzer pattern, pure AST
- Find for_statement/while_statement nodes
- Walk loop body for assignment nodes with subscript left-hand side
- Skip nested loops (separate scope)

## Status
DONE - 16 tests, committed
