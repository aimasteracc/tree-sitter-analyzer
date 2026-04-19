# Flag Argument Detector

## Goal
Detect boolean parameters (flag arguments) that indicate SRP violations.

## MVP Scope
- Detection: Find function/method parameters with boolean type
- 4 languages: Python, JS/TS, Java, Go
- 30+ tests
- MCP tool wrapper

## Technical Approach
- Independent analysis module: tree_sitter_analyzer/analysis/flag_argument.py
- MCP tool: tree_sitter_analyzer/mcp/tools/flag_argument_tool.py
- Inherit BaseAnalyzer
- Pure AST analysis: scan function definitions for boolean-typed parameters

## Detection Patterns
1. Python: `def f(x: bool)` or `def f(x=True)` / `def f(x=False)`
2. JS/TS: `function f(x: boolean)` or `function f(x = true/false)`
3. Java: `void f(boolean x)`
4. Go: `func f(x bool)`
