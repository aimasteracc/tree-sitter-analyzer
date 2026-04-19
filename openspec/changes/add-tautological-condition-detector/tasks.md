# Tautological Condition Detector

## Goal
Detect conditions that always evaluate to the same value due to contradictory or redundant comparisons.

## MVP Scope
- 3 detection patterns: contradictory_condition, subsumed_condition, tautological_comparison
- 4 languages: Python, JS/TS, Java, Go
- 30+ tests
- MCP tool wrapper

## Technical Approach
- Independent analysis module: tree_sitter_analyzer/analysis/tautological_condition.py
- MCP tool: tree_sitter_analyzer/mcp/tools/tautological_condition_tool.py
- Pure AST analysis of boolean expressions and comparison operators
- Pattern matching on operator + operand pairs within compound conditions

## Detection Patterns
1. contradictory_condition: x == 5 and x == 10 (always false)
2. subsumed_condition: x > 3 and x > 5 (first subsumed by second)
3. tautological_comparison: x == x, x != x, if True/False
