# Unified Project Overview — 统一项目概览报告

## Goal

一条命令揭示代码库的完整健康状况和架构特征。整合现有的 7 个独立分析工具，提供统一的项目健康报告。

## Inspiration

- CodeFlow — 浏览器端代码架构可视化工具（六大核心功能的统一展示）
- tree-sitter-analyzer 已有 7 个独立分析工具，但用户需要运行多条命令才能获得完整洞察

## MVP Scope

1. **Core Aggregator** — 调用现有 7 个分析工具，聚合结果
2. **Unified Reporter** — 生成 Markdown/JSON/TOON 格式的统一报告
3. **CLI + MCP Tool** — `tree-sitter overview` 命令和 MCP tool

## Technical Approach

### 推荐方案：独立 overview 模块

```
tree_sitter_analyzer/overview/
- aggregator.py - 调用现有分析工具，聚合结果
- reporter.py - 生成统一报告（Markdown/JSON/TOON）
- __init__.py - 模块导出

tree_sitter_analyzer/mcp/tools/
- overview_tool.py - MCP 工具包装器

cli/commands/
- overview_command.py - CLI 命令
```

### Sprint Breakdown

**Sprint 1: Core Aggregator (2-3 天)** ✅ 完成
- ✅ 创建 `overview/aggregator.py` 模块
- ✅ 实现 `OverviewAggregator` 类
  - ✅ `generate_overview()` - 主入口
  - ✅ `_run_dependency_analysis()` - 依赖图分析
  - ✅ `_run_health_analysis()` - 健康评分分析
  - ✅ `_run_pattern_analysis()` - 设计模式分析
  - ✅ `_run_security_analysis()` - 安全扫描
  - ✅ `_run_dead_code_analysis()` - 死代码检测
  - ✅ `_run_ownership_analysis()` - 代码所有权分析
  - ✅ `_run_blast_analysis()` - 爆炸半径分析
- ✅ 实现 `OverviewReport` dataclass
- ✅ 支持并行执行（concurrent.futures）
- ✅ 支持部分失败隔离
- ✅ 编写单元测试 (22 tests, 超过 15+ 目标)

**Sprint 2: Reporter + Output Formats (2-3 天)**
- [ ] 创建 `overview/reporter.py` 模块
- [ ] 实现 `OverviewReporter` 类
  - `generate_markdown()` - Markdown 报告
  - `generate_json()` - JSON 输出
  - `generate_toon()` - TOON 格式
- [ ] 实现报告章节排序（概览 → 详细分析 → 建议）
- [ ] 实现可视化元素（进度条、热力图、徽章）
- [ ] 编写单元测试 (10+ tests)

**Sprint 3: CLI + MCP Tool (2-3 天)**
- [ ] 创建 `cli/commands/overview_command.py` 命令
- [ ] 实现 `tree-sitter overview` CLI
  - 支持 `--format` 参数 (markdown/json/toon)
  - 支持 `--include` 参数（选择分析器）
  - 支持 `--parallel` 参数（并行执行）
- [ ] 创建 `mcp/tools/overview_tool.py`
- [ ] 注册到 ToolRegistry (overview toolset)
- [ ] 编写集成测试 (10+ tests)

## Success Criteria

- [ ] CLI 命令 `tree-sitter overview` 可用
- [ ] MCP tool `overview` 可用
- [ ] 支持输出格式: json, markdown, toon
- [ ] 35+ tests passing
- [ ] ruff check passes, mypy --strict passes
- [ ] 复用现有 100% 代码（零新分析算法）

## Dependencies

- tree-sitter-analyzer core (现有)
- 7 个现有分析工具（已实现）
- concurrent.futures (标准库)

## Open Questions

- 是否需要支持远程仓库的 Overview？（MVP 仅支持本地路径）
- 是否需要增量模式（只运行变更的分析器）？（Sprint 1 后评估）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
