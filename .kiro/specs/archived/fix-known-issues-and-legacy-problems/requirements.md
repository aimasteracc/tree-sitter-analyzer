# Requirements - Fix Known Issues and Legacy Problems

## 现状分析 (Current State Analysis)
根据 `CLAUDE.md` 和项目文档，Tree-sitter Analyzer 目前存在以下已知问题：
1. **查询引擎缺陷 (Test 13-15)**: `fields` 查询键和某些过滤器 (filters) 无法按预期工作。
2. **MCP 工具缺失功能 (Test 25-26)**: `list_files` 工具缺少 `sort` 参数实现。
3. **类型安全问题**: 项目尚未达到 100% 的 `mypy` 合规性。

## 问题识别 (Problem Identification)
- `tree_sitter_analyzer/core/query.py` 中的查询逻辑可能未能正确处理 `fields` 提取或过滤器匹配。
- `tree_sitter_analyzer/mcp/tools/list_files_tool.py` 中虽然定义了 `sort` 参数，但实际执行逻辑中未被应用。
- 存在一些 legacy 代码或新代码未严格遵守类型注解。

## 目标定义 (Goals & Objectives)
- 修复 `query_code` 工具中的 `fields` 和 `filter` 功能，确保回归测试通过。
- 为 `list_files` 工具实现有效的 `sort` 参数（支持按名称、修改时间等排序）。
- 提高项目的 `mypy` 检查通过率，消除核心模块的类型错误。

## 验收点 (Acceptance Criteria)
- [ ] 运行回归测试，Test 13-15 状态变为成功。
- [ ] 运行回归测试，Test 25-26 状态变为成功。
- [ ] `uv run mypy tree_sitter_analyzer/` 报错减少或清零。
