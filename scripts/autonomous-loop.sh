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

    # 检查是否需要 context reset
    if [ -f ".recovery-prompt.txt" ]; then
        echo ""
        echo "🔄 检测到 Context Reset 标记，恢复状态..."
        RECOVERY_PROMPT=$(cat .recovery-prompt.txt)
        rm -f .recovery-prompt.txt
        rm -f .context-reset-marker

        # 使用恢复提示启动 session
        claude --print "$RECOVERY_PROMPT

继续自主开发。" 2>&1 | tee -a "autonomous-loop-$(date '+%Y%m%d').log"
    else
        # 检查 context 使用率（简单估算）
        RECENT_COMMITS=$(git log -10 --oneline --name-only --pretty=format: | wc -l | tr -d ' ')
        ESTIMATED_USAGE=$((RECENT_COMMITS * 3))

        if [ "$ESTIMATED_USAGE" -gt 70 ]; then
            echo ""
            echo "🔄 Context 使用率约 ${ESTIMATED_USAGE}%，触发自动 reset..."

            # 运行 context auto-reset 脚本
            python3 scripts/context-auto-reset.py

            # 如果创建了 recovery prompt，使用它；否则正常启动
            if [ -f ".recovery-prompt.txt" ]; then
                echo "检测到 recovery prompt，使用它恢复..."
                RECOVERY_PROMPT=$(cat .recovery-prompt.txt)
                rm -f .recovery-prompt.txt
                rm -f .context-reset-marker
                claude --print "$RECOVERY_PROMPT

继续自主开发。" 2>&1 | tee -a "autonomous-loop-$(date '+%Y%m%d').log"
            else
                # 正常启动
                echo "Context reset 完成，启动新 session..."
                sleep 2
            fi
        fi

        # 正常启动 session
        # --print 非交互模式 + 完整权限通过 settings.local.json
        # 重要：让Claude直接读取AUTONOMOUS.md，不要在命令中重复指令
        claude --print "读取 AUTONOMOUS.md 的全部内容，严格遵循其中的所有规则进行自主开发。

核心要求：
1. 检查是否有未完成的 OpenSpec change，有就继续实现
2. 如果没有，执行AUTONOMOUS.md中定义的「永续循环机制」
3. 严格遵守「停滞预防」章节的决策规则，不要等待任何回答
4. 每完成一个Sprint就commit + push
5. Context使用率>70%时更新三文件并停止

现在开始。" 2>&1 | tee -a "autonomous-loop-$(date '+%Y%m%d').log"
    fi

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
