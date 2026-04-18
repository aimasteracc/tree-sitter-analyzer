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
- [ ] Sprint 1: Core Detection Engine
- [ ] Sprint 2: Multi-Language Support
- [ ] Sprint 3: MCP Tool Integration
