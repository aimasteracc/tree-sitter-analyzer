# Documentation Coverage Analyzer

## Goal

检测代码中缺少文档的函数/类/方法，输出覆盖率百分比和缺失列表。帮助开发者确保代码文档完整性。

一句话定义: "告诉你哪些代码没有文档"

## MVP Scope

### Sprint 1: Core Detection Engine (Python) ✅ COMPLETE

**文件**:
- `tree_sitter_analyzer/analysis/doc_coverage.py` (~400 lines)

**完成内容**:
- `DocElement` dataclass: 元素名、类型、文件路径、行号、有文档、文档内容
- `DocCoverageResult` dataclass: 总元素数、已文档化数、覆盖率百分比、缺失列表
- `DocCoverageAnalyzer` class:
  - `analyze_file(file_path)` → 检测单文件文档覆盖
  - `analyze_directory(dir_path)` → 检测目录
  - `get_missing_docs()` → 返回缺失文档的元素列表
- Python 检测:
  - 函数/异步函数 docstring
  - 类 docstring
  - 方法 docstring (含 @staticmethod/@classmethod)
  - 模块级 docstring
  - decorated_definition 处理

**测试**: 16 tests passing

### Sprint 2: Multi-Language Support ✅ COMPLETE (integrated with Sprint 1)

**完成内容**:
- JavaScript/TypeScript: JSDoc (`/** ... */`) for functions, classes, methods
- Java: JavaDoc (`/** ... */`) for classes, interfaces, methods
- Go: Go doc comments (`// comment`) for functions, types
- 每种语言的文档格式规则

**测试**: 14 tests passing (JS: 5, Java: 4, Go: 3, Directory: 2)

### Sprint 3: MCP Tool Integration ✅ COMPLETE

**文件**:
- `tree_sitter_analyzer/mcp/tools/doc_coverage_tool.py` (~220 lines)
- 注册到 analysis toolset

**完成内容**:
- MCP tool: `doc_coverage` (analysis toolset)
- 参数: file_path, project_root, element_types, min_coverage, format
- 输出: TOON + JSON
- 9 MCP tool tests passing

**测试**: 9 tests passing

## Technical Approach

- 使用 tree-sitter AST 遍历解析代码结构（函数、类、方法定义）
- 文档检测: 检查目标节点前的兄弟节点是否为注释/文档字符串
- Python: 检查 expression_statement(string) 作为函数体第一条语句
- JavaScript/TypeScript: 检查 JSDoc 注释块作为前兄弟节点
- Java: 检查 block_comment 作为前兄弟节点
- Go: 检查 comment 作为前兄弟节点
- decorated_definition 处理 (@staticmethod, @classmethod 等装饰器)
- 方法检测: 在 class_definition 的 block 内识别 function_definition 为 method
- 与 env_tracker/import_sanitizer 架构模式一致

## Summary

- **总测试**: 41 tests (32 analysis + 9 MCP tool)
- **总代码**: ~620 lines (400 analysis + 220 MCP tool)
- **支持语言**: Python, JavaScript, TypeScript, Java, Go
- **MCP 工具注册**: analysis toolset
- **CI 状态**: ruff ✅, mypy --strict ✅, pytest ✅
