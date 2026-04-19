# Dead Code Path Analyzer

## Goal
Detect code that can never execute: statements after return/raise/break/continue, dead branches (if False, if True...else), and other unreachable paths within functions.

## MVP Scope
- Detect code after terminal statements (return, raise, break, continue, throw, panic)
- Detect dead branches: if False body, if True else branch
- Report line numbers and issue types: unreachable_code, dead_branch
- Severity: high (after return/raise), medium (dead branch)
- 4 languages: Python, JS/TS, Java, Go
- 30+ tests

## Technical Approach
- Pure AST pattern matching (no CFG)
- Single-pass function body traversal
- Per-language terminal statement node types
- Data classes: DeadCodePathIssue, DeadCodePathResult
- MCP tool wrapping follows existing pattern
- Reuse _LANGUAGE_MODULES, _LANGUAGE_FUNCS pattern from other analyzers

## Test Standard
- 30+ tests (analysis + MCP tool)
- Test fixtures for each language
- Edge cases: conditional returns, try/finally, nested functions, code in else after return in if
