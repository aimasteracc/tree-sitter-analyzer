# Global State Analyzer

## Goal
Detect module-level mutable state, `global` keyword usage, and `nonlocal` keyword usage that create hidden coupling and testability issues.

## MVP Scope
- Detect module-level variable assignments (Python, JS/TS, Java, Go)
- Detect `global` keyword usage (Python)
- Detect `nonlocal` keyword usage (Python)
- Detect module-level mutable collections (list/dict/set literals at module scope)
- Report findings with severity levels
- 35+ tests

## Technical Approach
- Pure AST pattern matching via BaseAnalyzer
- Module-level = assignment not inside function/class/method
- Python: `global` statement, `nonlocal` statement, module-level assignments
- JS/TS: var/let/const at top-level, assignments outside function scope
- Java: `static` non-final fields
- Go: package-level variables (not constants)
