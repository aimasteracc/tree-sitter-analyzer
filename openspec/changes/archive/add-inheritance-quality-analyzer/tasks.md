# Inheritance Quality Analyzer

## Goal
Detect inheritance anti-patterns: deep hierarchies, missing super calls, diamond problems, empty overrides.

## MVP Scope
- 4 detection patterns (single-file AST analysis)
  - deep_inheritance: inheritance depth > 3
  - missing_super_call: child __init__ without super().__init__()
  - diamond_inheritance: multiple inheritance creating diamond
  - empty_override: override that only calls super with no extra logic
- 4 languages: Python, Java, TypeScript, Go (limited: struct embedding)
- Unit tests: 40+ tests
- MCP tool: inheritance_quality
- Integration tests: 10+ tests

## Technical Approach
- Independent module: tree_sitter_analyzer/analysis/inheritance_quality.py
- MCP tool: tree_sitter_analyzer/mcp/tools/inheritance_quality_tool.py
- Follows established pattern (same as 46 existing analyzers)
- Pure AST analysis, no runtime dependencies
- Severity levels: HIGH (deep_inheritance, diamond), MEDIUM (missing_super), INFO (empty_override)

## NOT in scope
- override_signature_mismatch (needs cross-file type resolution)
- Full method override audit
- Go interface satisfaction checking
