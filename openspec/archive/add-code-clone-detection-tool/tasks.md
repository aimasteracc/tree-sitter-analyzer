# Code Clone Detection MCP Tool

## Goal
将现有的 code_clones.py 分析模块集成到 MCP 工具层，提供代码重复检测功能。

## MVP Scope
- MCP 工具包装 code_clones.py
- TOON + JSON 输出格式
- 注册到 analysis toolset
- 15+ 测试

## Technical Approach
- 模块: `tree_sitter_analyzer/analysis/code_clones.py` (已有，47 tests)
- 新建: `mcp/tools/code_clones_tool.py`
- 复用: ToolRegistry, TOON formatter
- 依赖: 无（纯 AST 分析）

## Sprint 1: MCP Tool Creation ✅
- [x] 创建 `mcp/tools/code_clone_detection_tool.py` ✅ 已存在
- [x] 实现 `detect_code_clones()` MCP 工具函数 ✅ 已完成
- [x] 添加 JSON 输出格式 ✅ 已完成
- [x] 编写工具测试 ✅ 24 tests passing

## Sprint 2: Registration + Documentation
- [x] 注册到 ToolRegistry (analysis toolset) ✅ 已注册
- [ ] 更新 README.md (工具数量 31 → 38)
- [x] 更新 CHANGELOG.md ✅ 已记录
- [ ] 添加使用示例到 ARCHITECTURE.md (可选)

## Success Criteria
- [x] 15+ MCP tool tests passing ✅ 24 tests
- [x] CI checks: ruff + mypy + pytest ✅
- [x] 工具可通过 MCP 调用 ✅ 已注册
- [ ] 文档更新完成 ⚠️ README 需要更新工具数量

## Summary
**Status**: 已完成 ✅

code_clone_detection 工具在之前会话中已完整实现：
- MCP tool: `tree_sitter_analyzer/mcp/tools/code_clone_detection_tool.py` (267 lines)
- Analysis engine: `tree_sitter_analyzer/analysis/code_clones.py` (完整)
- Tests: 24 MCP tool tests + 47 analysis tests passing
- Registration: 已注册到 analysis toolset
- CHANGELOG: 已记录

**仅剩**: README 工具数量更新 (31 → 38)

## Notes
- 原型完成于 Loop 18 (23 tests → 47 tests after improvements)
- 支持类型: Type 1 (exact), Type 2 (structural), Type 3 (functional)
- 严重程度: info, warning, critical
