#!/bin/bash
# autonomous-loop.sh — 持续自主开发循环
# 用法: ./scripts/autonomous-loop.sh [max-sessions]
#
# 自动重复启动自主开发 session。
# 每个 session 结束后检查 task_plan.md：
# - 如果还有未完成 Phase → 启动新 session
# - 如果所有 Phase 完成 → 停止
# - 按 Ctrl+C 手动停止
#
# 默认最多 100 个 session（约 24-72 小时）

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

MAX_SESSIONS=${1:-100}
SESSION=0
START_TIME=$(date +%s)

echo "======================================================="
echo "  Tree-sitter-analyzer 持续自主开发"
echo "  最大 session 数: $MAX_SESSIONS"
echo "  开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  按 Ctrl+C 停止"
echo "======================================================="
echo ""

cleanup() {
    echo ""
    echo "======================================================="
    echo "  收到停止信号，保存进度..."
    ELAPSED=$(( $(date +%s) - START_TIME ))
    HOURS=$(( ELAPSED / 3600 ))
    MINS=$(( (ELAPSED % 3600) / 60 ))
    echo "  运行时间: ${HOURS}h ${MINS}m"
    echo "  完成 session: $SESSION"
    echo "======================================================="
    exit 0
}

trap cleanup SIGINT SIGTERM

all_phases_complete() {
    # 检查是否有未完成的 OpenSpec change
    for dir in openspec/changes/*/; do
        if [ -f "$dir/tasks.md" ] && [ ! -d "${dir}archive" ]; then
            return 1  # 有未完成的 change，继续
        fi
    done

    # 检查最近 5 个提交是否有实质性代码变更
    # 获取最近 5 个提交中修改的 .py 文件数量
    recent_py_files=$(git log -5 --oneline --name-only --pretty=format: | grep "\.py$" | wc -l | tr -d ' ')

    # 如果最近 5 个提交中 .py 文件变更少于 10 个，认为已经稳定
    if [ "$recent_py_files" -lt 10 ]; then
        echo ""
        echo "🎉 开发目标已达成！"
        echo "   - 所有 OpenSpec changes 已完成"
        echo "   - 最近 5 个提交中只有 $recent_py_files 个 .py 文件变更"
        echo "   - 项目已进入稳定维护阶段"
        return 0  # 完成
    fi

    return 1  # 还有实质性工作，继续
}

while [ $SESSION -lt $MAX_SESSIONS ]; do
    SESSION=$((SESSION + 1))

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Session $SESSION / $MAX_SESSIONS"
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 检查是否所有 Phase 完成
    if all_phases_complete; then
        echo ""
        echo "🎉 所有 Phase 完成！自主开发结束。"
        break
    fi

    # 确认在正确分支
    BRANCH=$(git branch --show-current)
    if [ "$BRANCH" != "feat/autonomous-dev" ]; then
        echo "⚠️  分支不对 ($BRANCH)，切换到 feat/autonomous-dev"
        git checkout feat/autonomous-dev
    fi

    # 拉取最新（如果用户在其他地方有操作）
    git pull --rebase origin feat/autonomous-dev 2>/dev/null || true

    # 启动 session
    # --print 非交互模式 + 完整权限通过 settings.local.json
    claude --print "读取 AUTONOMOUS.md，然后继续 task_plan.md 中当前 Phase 的下一个未完成的 OpenSpec change。不需要人类确认，直接开始。每完成一个 Sprint 就 commit + push，然后继续下一个。当 context 快满时更新三文件并停止。" 2>&1 | tee -a "autonomous-loop-$(date '+%Y%m%d').log"

    # session 间短暂等待
    echo ""
    echo "Session $SESSION 完成。5 秒后启动下一个..."
    sleep 5
done

ELAPSED=$(( $(date +%s) - START_TIME ))
HOURS=$(( ELAPSED / 3600 ))
MINS=$(( (ELAPSED % 3600) / 60 ))

echo ""
echo "======================================================="
echo "  自主开发结束"
echo "  总运行时间: ${HOURS}h ${MINS}m"
echo "  完成 session: $SESSION"
echo "======================================================="
