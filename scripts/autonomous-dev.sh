#!/bin/bash
# autonomous-dev.sh — 自主开发启动脚本
# 用法: ./scripts/autonomous-dev.sh [session-number]
#
# 启动 Claude Code 的自主开发会话。
# 每个 session 自动：
# 1. 确认在 feat/autonomous-dev 分支
# 2. 读取 task_plan.md 和 progress.md
# 3. 继续未完成的 OpenSpec change
# 4. 完成后自动 commit + push

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# 确认分支
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "feat/autonomous-dev" ]; then
    echo "⚠️  当前分支: $BRANCH"
    echo "切换到 feat/autonomous-dev..."
    git checkout feat/autonomous-dev
fi

echo "========================================="
echo "  Tree-sitter-analyzer 自主开发系统"
echo "  分支: feat/autonomous-dev"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="
echo ""

# 显示当前进度
if [ -f task_plan.md ]; then
    echo "--- task_plan.md (前 30 行) ---"
    head -30 task_plan.md
    echo ""
fi

if [ -f progress.md ]; then
    echo "--- progress.md (最后 20 行) ---"
    tail -20 progress.md
    echo ""
fi

# 显示未完成的 OpenSpec changes
echo "--- 未完成的 OpenSpec Changes ---"
for dir in openspec/changes/*/; do
    if [ -f "$dir/tasks.md" ] && [ ! -d "${dir}archive" ]; then
        echo "  📋 $(basename "$dir")"
    fi
done
echo ""

echo "启动 Claude Code 自主开发会话..."
echo "指令：读取 AUTONOMOUS.md，然后继续 task_plan.md 中当前 Phase 的下一个 Sprint。"
echo ""

# 启动 Claude Code
# --dangerously-skip-permissions 标志已通过 settings.local.json 的 permissions.allow 实现
# 不需要额外的 flag，settings.local.json 已经允许所有必要操作
exec claude --print "读取 AUTONOMOUS.md 的完整内容，然后按照其中的工作流继续开发。从 task_plan.md 的当前 Phase 开始，执行下一个未完成的 OpenSpec change。不需要等待我的确认，直接开始。" 2>&1 | tee -a "autonomous-$(date '+%Y%m%d-%H%M%S').log"
