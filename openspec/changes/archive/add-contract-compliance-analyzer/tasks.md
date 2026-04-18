# Contract Compliance Analyzer

## Goal
Detect functions whose implementations violate their declared contracts -- return type mismatches, boolean traps, and type contradictions.

## MVP Scope
- Detection types: return_type_violation, boolean_trap, type_contradiction, signature_divergence
- Languages: Python, JS/TS, Java, Go
- Test standard: 40+ tests (30 analysis + 10 MCP tool)

## Technical Approach
- Independent module: tree_sitter_analyzer/analysis/contract_compliance.py
- MCP tool: tree_sitter_analyzer/mcp/tools/contract_compliance_tool.py
- Follows existing analyzer pattern (45 analyzers)
- Pure tree-sitter AST analysis
