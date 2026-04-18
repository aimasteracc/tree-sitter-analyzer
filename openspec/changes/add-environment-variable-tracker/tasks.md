# Environment Variable Tracker

## Goal

列出项目中所有使用的环境变量及其位置，帮助开发者理解配置需求和避免遗漏部署配置。

一句话定义: "让开发者在部署前知道需要配置哪些环境变量"

## MVP Scope

### Sprint 1: Core Detection Engine (Python)

**目标**: 创建环境变量检测引擎，支持 Python

**文件**:
- `tree_sitter_analyzer/analysis/env_tracker.py` (~200 lines)

**功能**:
- `EnvVarReference` dataclass: 变量名、文件路径、行号、上下文代码
- `EnvVarUsage` dataclass: 变量名、引用列表、使用计数
- `EnvVarTracker` class:
  - `track_env_vars(file_path: str) -> list[EnvVarReference]`
  - `group_by_var_name(references: list[EnvVarReference]) -> dict[str, EnvVarUsage]`
  - `find_unused_declarations(declarations: set[str], usages: dict[str, EnvVarUsage]) -> set[str]`

**Python 支持的语法模式**:
- `os.getenv("VAR_NAME")`
- `os.environ["VAR_NAME"]`
- `os.environ.get("VAR_NAME")`
- `os.getenv("VAR_NAME", "default")`

**测试**:
- `tests/unit/test_env_tracker.py` (15+ tests)
  - 测试简单 os.getenv 调用
  - 测试 os.environ 索引访问
  - 测试带默认值的 os.getenv
  - 测试嵌套表达式
  - 测试分组功能
  - 测试未使用声明检测

**CI 检查**:
- `uv run ruff check tree_sitter_analyzer/analysis/env_tracker.py --fix`
- `uv run mypy tree_sitter_analyzer/analysis/env_tracker.py --strict`

### Sprint 2: Multi-Language Support

**目标**: 支持 JavaScript/TypeScript, Java, Go

**文件修改**:
- 扩展 `tree_sitter_analyzer/analysis/env_tracker.py` (~150 additional lines)

**功能**:
- JavaScript/TypeScript 支持:
  - `process.env.VAR_NAME`
  - `process.env["VAR_NAME"]`
- Java 支持:
  - `System.getenv("VAR_NAME")`
  - `System.getProperty("var.name")`
- Go 支持:
  - `os.Getenv("VAR_NAME")`

**测试**:
- 扩展 `tests/unit/test_env_tracker.py` (20+ tests)
  - 每种语言 5+ 个测试用例
  - 测试跨语言项目

**CI 检查**:
- 所有语言测试通过
- Ruff + MyPy 严格模式

### Sprint 3: CLI + MCP Tool Integration

**目标**: 创建 CLI 命令和 MCP 工具

**文件**:
- `tree_sitter_analyzer/mcp/tools/env_tracker_tool.py` (~250 lines)
- `tree_sitter_analyzer/cli/commands/env_command.py` (~150 lines)

**MCP 工具功能**:
- 工具名: `env_tracker`
- Toolset: `analysis`
- 参数:
  - `paths`: 文件/目录列表 (可选，默认项目根目录)
  - `group_by_var`: 是否按变量名分组 (默认 true)
  - `include_defaults`: 是否包含带默认值的调用 (默认 true)
- 输出格式:
  - TOON: 结构化输出
  - JSON: 程序化使用

**CLI 命令**:
- 命令: `tree-sitter env`
- 参数:
  - `--format`: text | json | toon
  - `--group`: 按变量名分组
  - `--unused`: 检测未使用的环境变量声明

**测试**:
- `tests/unit/test_env_tracker_tool.py` (15+ tests)
- `tests/integration/test_env_tracker_cli.py` (10+ tests)

**CI 检查**:
- 所有测试通过
- Ruff + MyPy + pytest

## Technical Approach

### 模块架构

```
env_tracker.py (分析引擎)
  ├── EnvVarReference (单个引用)
  ├── EnvVarUsage (聚合使用信息)
  └── EnvVarTracker (检测器)
      ├── track_env_vars() - 检测单个文件
      ├── group_by_var_name() - 分组
      └── find_unused_declarations() - 检测未使用

env_tracker_tool.py (MCP 工具)
  ├── EnvTrackerTool (MCP tool wrapper)
  └── TOON formatting

env_command.py (CLI 命令)
  ├── EnvCommand (CLI command)
  └── Text/JSON/TOON output
```

### 依赖模块

- `tree_sitter_analyzer.core`: 语言插件管理
- `tree_sitter_analyzer.plugins`: 语言特定提取器
- `tree_sitter_analyzer.formatters`: TOON 编码器

### Tree-sitter 查询模式

**Python**:
```scheme
(call
  function: (attribute
    object: (identifier) @obj (#eq? @obj "os")
    attribute: (identifier) @attr (#match? @attr "getenv|environ"))
  arguments: (argument_list
    (string (string_content) @var_name)))
```

**JavaScript/TypeScript**:
```scheme
(member_expression
  object: (member_expression
    object: (identifier) @obj (#eq? @obj "process")
    property: (property_identifier) @prop (#eq? @prop "env"))
  property: (property_identifier) @var_name)
```

## Success Criteria

1. **功能完整性**:
   - 支持 4 种语言 (Python, JavaScript/TypeScript, Java, Go)
   - 准确检测环境变量引用
   - 正确分组和计数

2. **代码质量**:
   - 测试覆盖率 ≥ 80%
   - MyPy --strict 通过
   - Ruff linting 通过

3. **集成测试**:
   - 真实项目验证 (4 个项目，每个语言 1 个)
   - MCP 工具集成测试
   - CLI 命令集成测试

## Open Questions

1. 是否需要检测环境变量声明 (如 .env 文件)?
   - MVP 范围: 只检测使用，不检测声明
   - 未来扩展: 可添加 .env 文件解析

2. 是否需要检测配置文件 (如 config.py, config.json)?
   - MVP 范围: 只检测代码中的环境变量引用
   - 未来扩展: 可添加配置文件解析

3. 是否需要支持更多语言 (Ruby, PHP, C#, etc.)?
   - MVP 范围: 4 种主流语言
   - 未来扩展: 根据需求添加
