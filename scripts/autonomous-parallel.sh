#!/bin/bash
# autonomous-parallel.sh — 并行自主开发（永不停止版）
# 用法: ./scripts/autonomous-parallel.sh [workers]
#
# 同时启动多个 claude --print worker，每个处理不同的任务。
# 所有 worker 完成后自动重启新一轮，永不停止。
# 通过 task_plan.md 中的 [ ] 标记做任务分配。
# 默认 3 个 worker。按 Ctrl+C 停止。

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

WORKERS=${1:-3}
START_TIME=$(date +%s)
LOG_DIR="autonomous-logs"
ROUND=0

mkdir -p "$LOG_DIR"

echo "======================================================="
echo "  Tree-sitter-analyzer 并行自主开发（永不停止）"
echo "  Workers: $WORKERS"
echo "  开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  日志目录: $LOG_DIR/"
echo "  按 Ctrl+C 停止所有 worker"
echo "======================================================="

# 确保在正确分支
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "feat/autonomous-dev" ]; then
    echo "切换到 feat/autonomous-dev..."
    git checkout feat/autonomous-dev
fi

# 每个 worker 用不同的 prompt 偏好，让它们倾向于选不同的任务
WORKER_PROMPTS=(
    "读取 AUTONOMOUS.md，然后从 task_plan.md 中选择第一个未完成的任务（Phase 1-2 优先）。专注 Skill 层和 MCP Server 相关工作。写完代码后必须跑 ruff check + mypy + pytest，通过后 commit + push，然后继续下一个任务。不停迭代。"
    "读取 AUTONOMOUS.md，然后从 task_plan.md 中选择中间的未完成任务（Phase 3-4 优先）。专注代码分析引擎和多语言优化。写完代码后必须跑 ruff check + mypy + pytest，通过后 commit + push，然后继续下一个任务。不停迭代。"
    "读取 AUTONOMOUS.md，然后从 task_plan.md 中选择最后的未完成任务（Phase 5-7 优先）。专注性能优化、测试覆盖率和代码质量。写完代码后必须跑 ruff check + mypy + pytest，通过后 commit + push，然后继续下一个任务。不停迭代。"
    "读取 AUTONOMOUS.md，从 task_plan.md 中选择任何未完成任务。优先做测试覆盖和文档完善。写完代码后必须跑 ruff check + mypy + pytest，通过后 commit + push，然后继续下一个任务。不停迭代。"
    "读取 AUTONOMOUS.md，从 task_plan.md 中选择任何未完成任务。优先做性能基准测试和优化。写完代码后必须跑 ruff check + mypy + pytest，通过后 commit + push，然后继续下一个任务。不停迭代。"
)

cleanup() {
    echo ""
    echo "停止所有 worker..."
    for PID in "${PIDS[@]}"; do
        kill "$PID" 2>/dev/null || true
    done
    wait 2>/dev/null
    ELAPSED=$(( $(date +%s) - START_TIME ))
    HOURS=$(( ELAPSED / 3600 ))
    MINS=$(( (ELAPSED % 3600) / 60 ))
    echo "总运行时间: ${HOURS}h ${MINS}m，完成 $ROUND 轮"
    exit 0
}

trap cleanup SIGINT SIGTERM

# === 永不停止的主循环 ===
while true; do
    ROUND=$((ROUND + 1))
    ROUND_START=$(date +%s)

    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  第 $ROUND 轮开始 — $(date '+%Y-%m-%d %H:%M:%S')"
    echo "═══════════════════════════════════════════════════"

    PIDS=()

    # 启动 worker
    for i in $(seq 1 $WORKERS); do
        IDX=$(( (i - 1) % ${#WORKER_PROMPTS[@]} ))
        PROMPT="${WORKER_PROMPTS[$IDX]}"
        LOG="$LOG_DIR/worker-$i-round-${ROUND}-$(date '+%Y%m%d-%H%M%S').log"

        echo "  启动 Worker $i → $LOG"
        nohup claude --print "$PROMPT" > "$LOG" 2>&1 &
        PID=$!
        PIDS+=($PID)
        echo "  Worker $i → PID $PID"
        sleep 2
    done

    echo ""
    echo "第 $ROUND 轮: $WORKERS 个 worker 已启动"
    echo "  监控: tail -f $LOG_DIR/worker-*-round-${ROUND}-*.log"
    echo "  提交: git log --oneline -10"
    echo "  停止: kill $$"
    echo ""

    # 等待本轮所有 worker 完成
    wait

    ROUND_END=$(date +%s)
    ROUND_ELAPSED=$(( ROUND_END - ROUND_START ))
    ROUND_MINS=$(( ROUND_ELAPSED / 60 ))

    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  第 $ROUND 轮完成（耗时 ${ROUND_MINS} 分钟）"
    echo "═══════════════════════════════════════════════════"

    # 拉取远程变更（如果有的话）
    git pull --rebase origin feat/autonomous-dev 2>/dev/null || true

    # 显示本轮产出
    echo "本轮提交："
    git log --oneline -5
    echo ""

    TOTAL_ELAPSED=$(( ROUND_END - START_TIME ))
    TOTAL_HOURS=$(( TOTAL_ELAPSED / 3600 ))
    TOTAL_MINS=$(( (TOTAL_ELAPSED % 3600) / 60 ))
    echo "累计运行: ${TOTAL_HOURS}h ${TOTAL_MINS}m"

    # 短暂休息避免立即重启（给 API rate limit 缓冲）
    echo "等待 10 秒后启动第 $((ROUND + 1)) 轮..."
    sleep 10
done
