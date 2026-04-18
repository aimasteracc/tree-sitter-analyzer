# Return Path Analyzer

## Goal
Detect functions with inconsistent return paths: some branches return a value, others fall through to implicit None.

## MVP Scope
- Analyze all return/yield/throw statements within function bodies
- Detect: inconsistent_return (some paths return value, others None), missing_return (all branches lack return), complex_return_path (>5 returns), implicit_none (function ends without return)
- Support 4 languages: Python, JS/TS, Java, Go
- MCP tool with text/json/toon output formats
- 40+ tests

## Technical Approach
- Independent module: analysis/return_path.py + mcp/tools/return_path_tool.py
- Single-function analysis via tree-sitter queries
- Reuse BaseMCPTool, ToonEncoder, existing language plugin infrastructure
- Pattern: iterate function body, collect all return/yield/throw nodes, classify paths

## Detection Details
- Python: return, yield, raise statements in function/method bodies
- JS/TS: return, throw statements in function/method/arrow bodies
- Java: return, throw statements in method bodies
- Go: return statements in func bodies, bare return in deferred
- Classify: has_value (return x), empty (return), implicit (end of function without return)
- Inconsistency: mixed has_value and empty/implicit paths
