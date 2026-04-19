# Primitive Obsession Detector

## Goal
Detect overuse of primitive types (str, int, float, bool) where value objects would be better.

## MVP Scope
- 4 detection patterns: primitive_heavy_params, primitive_soup, anemic_value_object, type_hint_code_smell
- 4 languages: Python, JS/TS, Java, Go
- 30+ tests
- MCP tool wrapper

## Technical Approach
- Independent analysis module: tree_sitter_analyzer/analysis/primitive_obsession.py
- MCP tool: tree_sitter_analyzer/mcp/tools/primitive_obsession_tool.py
- Pure AST analysis, no cross-file dependencies
- Primitive types detected via type annotations + variable name heuristics
