你正在恢复 tree-sitter-analyzer 全自动开发 session。

# 当前状态
- 项目: /Users/aisheng.yu/git-private/tree-sitter-analyzer
- 分支: $(cd /Users/aisheng.yu/git-private/tree-sitter-analyzer && git branch --show-current)
- 最后 commit: $(cd /Users/aisheng.yu/git-private/tree-sitter-analyzer && git rev-parse --short HEAD)

# 上次进度
读取 .autonomous-runtime/progress.md 最后一条记录
读取 .autonomous-runtime/task_plan.md 当前 Phase (第一个标记为 [ ])

# 你的任务
从上次断点继续。步骤:
1. read_file .autonomous-runtime/task_plan.md
2. 确定当前 Phase
3. 从该 Phase 的步骤 1 开始（见 ds-automation.yaml 中的 8 步流程）
4. 如果以前有部分完成的工作，检查 git log 找最近的 feat: commit

# 约束
- 一次只做一个 OpenSpec change
- TDD: 先测试 → 实现 → 重构
- commit 前跑 ruff + pytest
