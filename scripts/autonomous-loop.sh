#!/bin/bash
# autonomous-loop.sh — 持续自主开发循环
# 用法: ./scripts/autonomous-loop.sh
#
# 自动重复启动自主开发 session。
# 循环条件：基于任务完成度，不是 session 计数
# - 如果还有未完成的 OpenSpec change → 继续
# - 如果所有 change 完成 → 停止
# - 按 Ctrl+C 手动停止
#
# 无 session 限制，持续运行直到任务完成

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

SESSION=0
START_TIME=$(date +%s)

echo "======================================================="
echo "  Tree-sitter-analyzer 持续自主开发"
echo "  无 session 限制，基于任务完成度判断"
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
        if [ -f "$dir/tasks.md" ]; then
            # 检查 tasks.md 是否标记为完成
            if ! grep -q "## Completion Status" "$dir/tasks.md" 2>/dev/null; then
                return 1  # 有未完成的 change
            fi
        fi
    done

    # 检查最近提交是否为空转
    # 如果最近 5 个提交中 .py 文件变更少于 5 个，认为已完成
    recent_py_files=$(git log -5 --oneline --name-only --pretty=format: 2>/dev/null | grep "\.py$" | wc -l | tr -d ' ')

    if [ "$recent_py_files" -lt 5 ]; then
        echo ""
        echo "🎉 开发目标已达成！"
        echo "   - 所有 OpenSpec changes 已完成或归档"
        echo "   - 最近提交活动较低 ($recent_py_files 个 .py 文件变更)"
        echo "   - 项目已进入稳定维护阶段"
        return 0  # 完成
    fi

    return 1  # 还有工作
}

while true; do
    SESSION=$((SESSION + 1))

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Session $SESSION"
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 检查是否所有任务完成
    if all_phases_complete; then
        echo ""
        echo "🎉 所有任务完成！自主开发结束。"
        break
    fi

    # 确认在正确分支
    BRANCH=$(git branch --show-current)
    if [ "$BRANCH" != "feat/autonomous-dev" ]; then
        echo "⚠️  分支不对 ($BRANCH)，切换到 feat/autonomous-dev"
        git checkout feat/autonomous-dev
    fi

    # 拉取最新
    git pull --rebase origin feat/autonomous-dev 2>/dev/null || true

    # 清理任何残留的标记文件
    rm -f .context-reset-marker .recovery-prompt.txt 2>/dev/null || true

    # 启动 session（非交互模式）
    # 添加提示避免 AskUserQuestion 卡住
    claude --print "读取 AUTONOMOUS.md 的全部内容，严格遵循其中的所有规则进行自主开发。

核心要求：
1. 检查是否有未完成的 OpenSpec change，有就继续实现
2. 如果没有，执行AUTONOMOUS.md中定义的「永续循环机制」
3. 在「永续循环」中：
   - 调用 /steve-jobs-perspective 做产品分析
   - 调用 /plan-eng-review 做架构分析
   - 重要：要求Skill'分析并给出建议'，不要让Skill问问题
4. 每完成一个Sprint就commit + push
5. Context使用率>70%时更新三文件并停止

关键：深度分析必须有，但Skill调用方式要正确——要求分析而非问答。

⚠️  禁止使用 AskUserQuestion！
⚠️  遇到需要确认的情况，直接做决定并继续！
⚠️  不要等待用户输入！

现在开始。" 2>&1 | tee -a "autonomous-loop-$(date '+%Y%m%d').log" || echo "⚠️  Session 失败，继续下一个..."

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
