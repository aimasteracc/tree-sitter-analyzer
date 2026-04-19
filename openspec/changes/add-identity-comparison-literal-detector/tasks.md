# Identity Comparison with Literals Detector

## Goal
Detect `is`/`is not` used with non-singleton literals — a forward compatibility issue in Python 3.12+

## MVP Scope
- Detect identity comparisons with non-singleton literals (int, float, string, list, dict, set, tuple)
- Allow singleton values: None, True, False, Ellipsis
- Python-only analyzer
- Minimum 30 tests (analysis + MCP tool)

## Technical Approach
- Walk AST for `comparison_operator` nodes
- Check for `is` / `is not` operators
- Check operands for literal types (excluding singletons)
- Standard BaseAnalyzer pattern
