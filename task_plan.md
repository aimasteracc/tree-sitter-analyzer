# Tree-sitter-analyzer 自主开发计划

## Goal
将 ts-analyzer 从 "CLI + MCP 工具" 提升为 "完整的代码上下文平台"

## Phases
- [ ] Phase 1: Skill 层开发（参考 Fireworks TG + 金谷园 Skill）
  - [ ] 1.1 创建 Claude Code Skill SKILL.md
  - [ ] 1.2 自然语言查询代码结构
  - [ ] 1.3 Skill vs MCP token 成本验证
  - [ ] 1.4 Skill 层测试（含 CJK 查询）
- [ ] Phase 2: MCP Server 升级（参考 qmd + MCP 进阶课程）
  - [ ] 2.1 StreamableHTTP 传输层
  - [ ] 2.2 SDK 嵌入模式（参考 qmd createStore）
  - [ ] 2.3 MCP 工具 schema 优化
- [ ] Phase 3: 项目级可视化（参考 CodeFlow）
  - [ ] 3.1 依赖图算法
  - [ ] 3.2 健康评分（A-F）
  - [ ] 3.3 爆炸半径分析
- [ ] Phase 4: 多语言深度优化
  - [ ] 4.1 Java 查询谓词修复
  - [ ] 4.2 C# 新语言支持
  - [ ] 4.3 多语言 AST 分块优化
- [ ] Phase 5: 性能与可靠性
  - [ ] 5.1 TOON 压缩率优化
  - [ ] 5.2 错误恢复机制
  - [ ] 5.3 语言插件懒加载

## Decisions Made
| 决策 | 理由 | 日期 |
|------|------|------|
| 用 OpenSpec 管理 Sprint | 项目已深度集成，15 个归档 change | 2026-04-17 |
| Planning-with-Files 三文件 | 跨 context window 保持连续性 | 2026-04-17 |
| 3-Agent GAN 循环 | 防止自评放水，确保质量 | 2026-04-17 |
| 分支 feat/autonomous-dev | 与 main 隔离，每个 change 可独立 PR | 2026-04-17 |

## Errors Encountered
| 错误 | 原因 | 解决方案 | 状态 |
|------|------|---------|------|
