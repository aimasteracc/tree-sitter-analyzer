# Dead Store Detector

## Goal
Detect variables that are assigned but whose value is never read before reassignment or scope exit, indicating dead code, incomplete refactoring, or hidden bugs.

## MVP Scope
- [x] Core analyzer: dead_store.py (inherits BaseAnalyzer)
- [x] Detect: dead_store, self_assignment, immediate_reassignment
- [x] Languages: Python, JavaScript/TypeScript, Java, Go
- [x] MCP tool: dead_store_tool.py registered in tool_registration.py
- [x] Tests: 35+ tests covering all issue types and languages

## Technical Approach
- Pure AST traversal (no type inference needed)
- For each function/method scope: track assignments and reads
- Flag: assigned value never read before next assignment or scope exit
- Flag: self-assignment (`x = x`)
- Flag: immediate reassignment (`x = a; x = b` with no read of first value)
- Node type mapping per language (same pattern as variable_shadowing.py)

## Dependencies
- BaseAnalyzer (analysis/base.py)
- LanguageLoader (language_loader.py)
- tool_registration.py for MCP registration
