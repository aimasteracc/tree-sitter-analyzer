# Assignment in Conditional Detector

## Goal
Detect assignments used as conditions (likely `==` vs `=` typo).

## MVP Scope
- Detect `if (x = expr)` patterns in JS/TS, Java, C/C++
- 20+ tests
- MCP tool wrapper

## Technical Approach
- Independent analysis module: tree_sitter_analyzer/analysis/assignment_in_conditional.py
- MCP tool: tree_sitter_analyzer/mcp/tools/assignment_in_conditional_tool.py
- Inherit BaseAnalyzer
- Walk if/while conditions to find assignment_expression nodes
