# Error Handling Pattern Analyzer

## Goal
检测项目中的错误处理反模式，按严重程度分类并提供改进建议。

## MVP Scope
- Sprint 1: Core Detection Engine (Python) — bare except, swallowed errors, broad exceptions
- Sprint 2: Multi-Language Support (JS/TS, Java, Go)
- Sprint 3: MCP Tool Integration

## Technical Approach
- 独立 analysis 模块: `tree_sitter_analyzer/analysis/error_handling.py`
- MCP 工具: `tree_sitter_analyzer/mcp/tools/error_handling_tool.py`
- 基于 tree-sitter AST 查询
- 支持 Python, JS/TS, Java, Go
- TOON + JSON 输出格式

## Status
- [x] Sprint 1: Core Detection Engine ✅ COMPLETE
- [x] Sprint 2: Multi-Language Support (JS/TS, Java, Go) ✅ COMPLETE
- [x] Sprint 3: MCP Tool Integration ✅ COMPLETE

## Completion Summary
- analysis/error_handling.py (~600 lines, 4 languages)
- mcp/tools/error_handling_tool.py (~220 lines)
- 36 tests passing
- MCP tool registered in analysis toolset
- Commit: 5a80cedb
