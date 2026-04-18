# Call Graph Analyzer

## Goal
Build function-level call graphs from AST, showing which functions call which other functions. Detect island functions (never called) and god functions (call 20+ others).

## MVP Scope
- Sprint 1: Core Detection Engine (Python) - call expression extraction, graph building, island/god detection
- Sprint 2: Multi-Language Support (JS/TS, Java, Go)
- Sprint 3: MCP Tool Integration

## Technical Approach
- Independent module: `analysis/call_graph.py` + `mcp/tools/call_graph_tool.py`
- Tree-sitter queries for call expression extraction per language
- Directed graph with callers/callees mapping
- TOON + JSON output formats
- Limitations: method dispatch, dynamic calls documented as unsupported

## Status
- [x] Sprint 1: Core Detection Engine (Python) — 29 tests ✅
- [x] Sprint 2: Multi-Language Support (JS/TS, Java, Go) — 17 tests ✅
- [x] Sprint 3: MCP Tool Integration — 9 tests ✅

## Completion Summary
- analysis/call_graph.py (~320 lines, 4 languages)
- mcp/tools/call_graph_tool.py (~180 lines)
- Total: 55 tests (29 Python + 17 multilang + 9 MCP tool)
- MCP tool registered in analysis toolset
- Features: function extraction, call graph, island detection, god function detection
- CI: ruff + mypy --strict passing
