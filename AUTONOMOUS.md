# AUTONOMOUS.md — tree-sitter-analyzer 自主开发指令

## 硬约束（不可违反）

1. **分支**：所有 commit 必须在 `feat/consolidated`。若 `git branch --show-current` 不是它，先 `git checkout feat/consolidated`，再做其他任何事。
2. **不 push main**：永远不 push 到 main 分支，不创建 GitHub Release。
3. **质量门禁**：每个 Sprint commit 前，`ruff check` + `pytest` 必须全过。
4. **1-in-1-out**：新增 analyzer 必须合并或替换现有的。总 analyzer 数不增长。
5. **禁止交互式 Skill**：自主模式下不调用 Steve Jobs 等需要人类回答的 Skill。

## 启动协议（每个 Session 第一步）

```
1. git branch --show-current  → 确认 feat/consolidated
2. git fetch origin && git pull --rebase origin feat/consolidated
3. 检查 openspec/changes/ 中的待办任务
4. memory_search(namespace="sprint-history") → 上次进度
5. memory_search(namespace="wiki-inspiration") → 灵感
6. 选择下一个 Sprint 目标
```

## Sprint 循环

```
步骤 1: 检查分支状态（启动协议）
步骤 2: 从 AgentDB / Wiki 搜索灵感（竞品 gap、社区 issue、待办任务）
步骤 3: 选择 1 个高价值 Sprint（4D 评分 ≥ 10/12）
  - D1 需求度 (0-3): 解决真实痛点？
  - D2 独特性 (0-3): 竞品没有或我们做得更好？
  - D3 可实现性 (0-3): 1 session 能完成？
  - D4 可验证性 (0-3): 有明确测试标准？
步骤 4: 创建 OpenSpec change（proposal.md + tasks.md）
步骤 5: TDD 实现（先写测试 → 实现 → 全过）
步骤 6: ruff check + pytest 全过
步骤 7: git add + commit + push origin feat/consolidated
步骤 8: memory_store 记录 Sprint 历史
步骤 9: 回到步骤 1
```

## 灵感来源（优先级排序）

1. `openspec/changes/` 中未完成的 tasks.md
2. Wiki 竞品分析中的 P0/P1/P2 行动项
3. memory_search(namespace="wiki-competitors") → 别人有我们没有的
4. memory_search(namespace="wiki-inspiration") → 产品讨论中的未落地想法
5. GitHub Issues / 社区反馈
6. 代码质量改进（oversized files, low-density tests, ruff warnings）

## 模型使用原则

- 长上下文规划和复杂实现：优先 z.ai coding 模型
- 短任务和测试：任意可用模型
- z.ai 不可用时降级官方模型，记录原因到 progress.md

## Ruflo 职责边界

| Ruflo 组件 | 用途 |
|-----------|------|
| memory_search/store | 跨 session 知识和灵感检索 |
| swarm | Agent 拓扑协调 |
| autopilot | 永续循环管理 |
| AgentDB | 向量记忆（替代一次性 qmd 检索）|

## 7 大失败模式防御

1. **交互式阻塞**：禁止调用需要人类输入的 Skill
2. **Context 膨胀**：优先小 Sprint，单个 change ≤ 500 行
3. **无限重试**：同错误 3 次 → 记录到 memory 并跳过
4. **远端冲突**：`git pull --rebase` 失败 → stash → rebase → pop
5. **代码膨胀**：1-in-1-out 门禁
6. **测试退化**：pytest 失败不 commit
7. **分支错误**：启动协议强制检查
