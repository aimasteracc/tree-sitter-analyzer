# Environment Variable Tracker

## Goal

列出项目中所有使用的环境变量及其位置，帮助开发者理解配置需求和避免遗漏部署配置。

一句话定义: "让开发者在部署前知道需要配置哪些环境变量"

## MVP Scope

### Sprint 1: Core Detection Engine (Python) ✅ COMPLETE

**文件**:
- `tree_sitter_analyzer/analysis/env_tracker.py` (~450 lines)

**完成内容**:
- `EnvVarReference` dataclass: 变量名、文件路径、行号、列号、访问类型、上下文、是否有默认值
- `EnvVarUsage` dataclass: 变量名、引用列表、文件计数、总引用数、默认值计数、访问类型
- `EnvTrackingResult` dataclass: 聚合结果
- `EnvVarTracker` class:
  - `track_env_vars(file_path)` → 检测单文件
  - `track_directory(dir_path)` → 检测目录
  - `group_by_var_name()` → 按变量名分组
  - `find_unused_declarations()` → 检测未使用声明
- 4 种 Python 模式:
  - `os.getenv("VAR")`
  - `os.getenv("VAR", "default")`
  - `os.environ["VAR"]`
  - `os.environ.get("VAR")`

**测试**: 17 tests passing

### Sprint 2: Multi-Language Support ✅ COMPLETE (integrated with Sprint 1)

**完成内容**:
- JavaScript/TypeScript: `process.env.VAR`, `process.env["VAR"]`
- Java: `System.getenv("VAR")`, `System.getProperty("var")`
- Go: `os.Getenv("VAR")`
- TypeScript `language_typescript` / `language_tsx` function name override

### Sprint 3: MCP Tool Integration ✅ COMPLETE

**文件**:
- `tree_sitter_analyzer/mcp/tools/env_tracker_tool.py` (~230 lines)
- `tree_sitter_analyzer/mcp/registry.py` (added env_tracker to analysis toolset)
- `tree_sitter_analyzer/mcp/tool_registration.py` (registered env_tracker)

**完成内容**:
- MCP tool: `env_tracker` (analysis toolset)
- 参数: file_path, project_root, group_by_var, include_defaults, format
- 输出: TOON + JSON
- 10 MCP tool tests passing

**测试**: 10 tests passing

## Technical Approach

- 使用 `TreeSitterQueryCompat` 兼容层执行 tree-sitter 查询
- 使用 `.` anchor 确保只匹配第一个字符串参数（避免默认值误识别）
- 通过检查 AST 节点参数数量检测默认值（非 tree-sitter 查询捕获）
- Python `subscript` 使用 `value` 字段（非 `object`）
- Java 使用 `string_fragment`（非 `string_content`）
- Go 使用 `interpreted_string_literal_content`
- JS 使用 `subscript_expression`（非 `subscript`）+ `string_fragment`

## Summary

- **总测试**: 27 tests (17 analysis + 10 MCP tool)
- **总代码**: ~680 lines (450 analysis + 230 MCP tool)
- **支持语言**: Python, JavaScript, TypeScript, Java, Go
- **MCP 工具注册**: analysis toolset (#20 tool)
- **CI 状态**: ruff ✅, mypy --strict ✅, pytest ✅
