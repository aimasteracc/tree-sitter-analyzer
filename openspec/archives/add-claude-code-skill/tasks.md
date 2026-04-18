# OpenSpec Change: add-claude-code-skill

## Summary
为 tree-sitter-analyzer 新增 Claude Code Skill 层，让用户可以用自然语言查询代码结构，底层通过现有 15 个 MCP 工具执行。

## Motivation
- ts-analyzer 目前只有 MCP 工具（急加载），缺少 Skill 层（懒加载）
- 参考 wiki/ai-tech/mcp-vs-skills-token-cost.md：Skill 比 MCP 节省 10-15 倍 token
- 参考 wiki/ai-tech/fireworks-tech-graph-overview.md 和 wiki/ai-tech/jinguyuan-dumpling-skill-overview.md 的 Skill 实现模式

## Design

### 三层架构
```
主 Skill（代码分析自然语言接口）
  └── 内嵌 Skills（按分析类型）
        └── MCP 工具（底层执行：15 个现有工具）
```

### Sprint Contract

**Generator 提议的完成标准**：
1. 创建 `.claude/skills/tree-sitter-analyzer-v2/SKILL.md`
2. 支持自然语言查询：元素查找、结构分析、影响追踪
3. Skill 懒加载，不增加基础 token 成本
4. 3 个测试用例通过

**Evaluator 补充标准**：
1. 必须包含 CJK 查询测试
2. 必须验证与现有 MCP 工具的兼容性
3. 必须有 token 成本对比（Skill vs 直接 MCP）

## Tasks
- [x] T1: 设计 SKILL.md 结构（参考 Fireworks TG + 金谷园 Skill）
- [x] T2: 实现自然语言 → MCP 工具映射逻辑
- [x] T3: 编写 CJK 查询测试
- [x] T4: token 成本基准测试
- [x] T5: 文档更新

## References
- wiki/ai-tech/fireworks-tech-graph-overview.md — Skill 模板
- wiki/ai-tech/jinguyuan-dumpling-skill-overview.md — 三层嵌套架构
- wiki/ai-tech/mcp-vs-skills-token-cost.md — token 成本分析
- wiki/ai-tech/claude-code-prompt-design-patterns.md — 提示词模式
- docs/skills/ — 项目现有的 10 个 MCP 工具 skill 文档
