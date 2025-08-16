## 02 架构与代码地图

这是一张“从入口到结果”的最小闭环地图，覆盖控制流、数据流与关键模块职责。阅读后应能追踪一次 CLI 调用或 MCP 请求的全链路。

### 顶层视图

- 运行入口：
  - CLI：`tree_sitter_analyzer/__main__.py` → `cli_main.main()`
  - MCP：`tree_sitter_analyzer/mcp/server.py`（脚本入口在 `pyproject.toml` 中配置脚本 `tree-sitter-analyzer-mcp`）

- 核心能力：
  - 语言检测：`language_detector.py`
  - 解析/引擎：`core/parser.py`、`core/analysis_engine.py`、`core/engine.py`
  - 查询系统：`core/query_service.py`（统一查询服务）、`core/query_filter.py`（结果过滤）、`core/query.py`、`queries/` 库
  - 输出格式化：`table_formatter.py` 与 `formatters/*`
  - 安全边界：`security/*`（边界管理、正则校验、验证器）

### 控制流（CLI）

1) `cli_main.create_argument_parser()` 定义参数
2) `cli_main.handle_special_commands()` 处理无需文件的查询与校验
3) `CLICommandFactory.create_command()` 根据参数选择 `cli/commands/*` 的命令类
4) `command.execute()` 内部调用核心引擎与格式化输出

常见命令：
- `--table` → `cli/commands/table_command.py` → `table_formatter.py`
- `--partial-read` → `cli/commands/partial_read_command.py`
- `--query-key`/`--query-string` → `cli/commands/query_command.py` → `core/query_service.py`
- `--filter` → 查询结果过滤（与query命令配合使用）
- `--summary`/`--structure` → 结构化 JSON 输出

### 控制流（MCP）

- `mcp/server.py` 初始化工具：
  - `tools/analyze_scale_tool.py`（规模/复杂度）
  - `tools/analyze_scale_tool_cli_compatible.py`（CLI 兼容）
  - `tools/universal_analyze_tool.py`（结构分析）
  - `tools/read_partial_tool.py`（精确片段提取）
  - `tools/table_format_tool.py`（表格化）
  - `tools/query_tool.py`（智能查询与过滤）
- 请求经 `utils/error_handler.py` 统一错误处理，严格遵循项目边界与参数校验

### 数据流

输入：`file_path`、范围参数、查询键/字符串、过滤表达式、输出选项
→ 语言检测（扩展名/显式指定）
→ Tree-sitter 解析（语言插件适配）
→ 查询执行（`core/query_service.py` + `queries/*`）
→ 结果过滤（`core/query_filter.py`，支持name/params/modifier匹配）
→ 结构构建与格式化（表格/JSON/文本）
→ 输出（CLI stdout 或 MCP 响应 JSON）

### 语言插件模型

- 入口注册：`pyproject.toml` 的 `project.entry-points."tree_sitter_analyzer.plugins"`
- 插件文件：`languages/{language}_plugin.py`，提供统一提取接口（类、方法、字段、导入等）
- 查询库：`queries/{language}.py`

### 质量与安全

- 类型与规范：`pyproject.toml`（mypy/ruff/black/isort 配置）
- 测试：`tests/`（覆盖 CLI、核心、MCP、工具、语言）
- 安全：`security/*` + 项目根边界检测（`PROJECT_ROOT_CONFIG.md`）

### 架构改进：统一查询服务

**问题**：CLI和MCP之间查询功能存在重复实现的风险。

**解决方案**：引入`QueryService`作为统一的查询服务层：
- `core/query_service.py`：统一的查询执行逻辑
- `core/query_filter.py`：通用的结果过滤器
- `cli/commands/query_command.py`：CLI查询命令（使用QueryService）
- `mcp/tools/query_tool.py`：MCP查询工具（使用QueryService）

**优势**：
- 消除代码重复
- 保证CLI和MCP功能一致性
- 易于维护和扩展
- 统一的过滤语法

### 如何进一步阅读代码

建议顺序：
1. `cli_main.py`（参数与分发）
2. `cli/commands/*`（命令与输出）
3. `core/*`（引擎/查询/缓存）
4. `languages/*` 与 `queries/*`（语言适配）
5. `mcp/*`（工具与服务）

**新功能重点关注**：
- `core/query_service.py` 和 `core/query_filter.py`（查询与过滤核心）
- `cli/commands/query_command.py`（CLI查询命令实现）
- `mcp/tools/query_tool.py`（MCP查询工具实现）
