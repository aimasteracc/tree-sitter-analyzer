# Nested Ternary Detector

## Goal
Detect deeply nested ternary/conditional expressions that are hard to read and error-prone.

## MVP Scope
- Detect ternary nesting depth >= 2 (configurable)
- 3 languages: Python, JS/TS, Java (Go has no ternary)
- 25+ tests
- MCP tool wrapper

## Technical Approach
- Independent analysis module: tree_sitter_analyzer/analysis/nested_ternary.py
- MCP tool: tree_sitter_analyzer/mcp/tools/nested_ternary_tool.py
- Inherit BaseAnalyzer
- Pure AST: count nesting of conditional_expression/ternary_expression nodes
