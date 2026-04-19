# Unclosed File Detector

## Goal
Detect open() calls not wrapped in a with statement, which can cause file handle leaks.

## MVP Scope
- Detect `f = open(...)` without enclosing `with` statement
- Python-only
- Report variable name, line number, severity

## Technical Approach
- BaseAnalyzer pattern, pure AST
- Walk tree, skip with_statement subtrees
- Find assignment nodes where right side is open() call

## Status
DONE - 14 tests, committed
