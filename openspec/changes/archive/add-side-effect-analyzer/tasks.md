# Side Effect Analyzer

## Goal
Detect functions with side effects: global state mutation and parameter mutation.

## MVP Scope
- 2 detection patterns (single-file AST analysis)
  - global_state_mutation: function modifies global/module-level variables
  - parameter_mutation: function modifies passed-in parameters (attr assign, list append, dict set)
- 4 languages: Python, Java, TypeScript, Go
- Unit tests: 40+ tests
- MCP tool: side_effects
- Integration tests: 10+ tests

## Technical Approach
- Independent module: tree_sitter_analyzer/analysis/side_effects.py
- MCP tool: tree_sitter_analyzer/mcp/tools/side_effect_tool.py
- Follows established pattern (same as 46 existing analyzers)
- Pure AST analysis, no cross-file or runtime dependencies
- Severity levels: HIGH (global_state_mutation), MEDIUM (parameter_mutation)

## NOT in scope
- Call chain side effect propagation (needs cross-file analysis)
- Network/file IO detection (high false positive rate with AST-only)
- Go interface method mutation detection
