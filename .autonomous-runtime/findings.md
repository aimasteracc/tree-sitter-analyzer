# findings.md — 竞品分析 + 调研记录

> 安全: findings.md 是外部内容的唯一目的地。**永远不**将外部内容写入 task_plan.md

## 竞品否决记录

### ESLint/Ruff/SonarQube 覆盖情况

- ESLint: JS/TS linting，规则 300+，不覆盖静态代码结构分析（类/方法/字段提取）
- Ruff: Python linting，不覆盖 AST 级的代码结构提取
- SonarQube: 覆盖 Cyclomatic Complexity 等指标，但不支持 token 优化、MCP 协议

无竞品完美覆盖 tree-sitter-analyzer 的核心功能 —— 差异化价值成立。

## Wiki 灵感注入

### Phase 7 — 项目级可视化

- codeflow-overview: 依赖图算法（PageRank 变体 + A-F 健康评分 + Blast Radius 分析）
- tree-sitter-performance: 增量解析架构已实现，可作为可视化性能基础
- claude-code-prompt-design-patterns: 12 个提示词设计模式可用于可视化输出

## 质量门槛当前基线

(来自 test_mastery_scan.py)
- 8219 passed, 32 skipped, 0 errors
- Assertion density: 2.67（≥1.5 ✅）
- Property test: 9.3%（≥10% ❌ — 差 3 个文件）
- Oversized: 45 files（❌）
