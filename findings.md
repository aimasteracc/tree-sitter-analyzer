# Findings — 自主开发调研笔记

## Wiki 参考资源（通过 qmd 检索）

### Phase 1 参考：Skill 层开发
- Fireworks Tech Graph：自然语言生成 SVG 技术图的 Claude Code Skill
  - SKILL.md 结构完整，可直接作为模板
  - 位置：wiki/ai-tech/fireworks-tech-graph-overview.md
- 金谷园饺子馆 Skill：三层嵌套 + MCP 混合模式
  - 主 Skill → 内嵌 Skill → MCP 工具
  - 位置：wiki/ai-tech/jinguyuan-dumpling-skill-overview.md
- MCP vs Skills token 成本：急加载 vs 懒加载，10-15 倍差异
  - 位置：wiki/ai-tech/mcp-vs-skills-token-cost.md

### Phase 2 参考：MCP 升级
- qmd MCP Server：stdio + HTTP 双传输、VRAM 缓存、Context 元数据
  - tree-sitter AST chunking 代码可直接参考
  - SDK 嵌入模式：createStore()
  - 位置：wiki/ai-tech/qmd-overview.md
- MCP 进阶课程：StreamableHTTP、Sampling、有状态/无状态
  - 位置：wiki/ai-tech/mcp-advanced-topics-course-notes.md

### Phase 3 参考：可视化
- CodeFlow：浏览器端代码架构可视化，单 HTML 文件
  - 依赖图、爆炸半径、健康评分（A-F）
  - 位置：wiki/ai-tech/codeflow-overview.md

### Agent 架构参考
- 7 大失败模式及防御方案
  - 位置：wiki/ai-tech/agent-failure-modes.md
- 12 个提示词设计模式（约束优先、事件驱动、分层委托）
  - 位置：wiki/ai-tech/claude-code-prompt-design-patterns.md
- Harness 三代演化（V1→V2→简化版）
  - 位置：wiki/ai-tech/long-running-agent-harness.md
