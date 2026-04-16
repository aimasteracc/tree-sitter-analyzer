#!/bin/bash
# autonomous-parallel.sh — 并行自主开发
# 用法: ./scripts/autonomous-parallel.sh [workers]
#
# 同时启动多个 claude --print worker，每个处理不同的任务。
# 通过 task_plan.md 中的 [ ] 标记做任务分配（每个 worker 抢不同的任务）。
# 默认 3 个 worker。

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

WORKERS=${1:-3}
START_TIME=$(date +%s)
LOG_DIR="autonomous-logs"

mkdir -p "$LOG_DIR"

echo "======================================================="
echo "  Tree-sitter-analyzer 并行自主开发"
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

PIDS=()

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
    echo "运行时间: ${HOURS}h ${MINS}m"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 每个 worker 用不同的 prompt 偏好，让它们倾向于选不同的任务
WORKER_PROMPTS=(
    "读取 AUTONOMOUS.md，然后从 task_plan.md 中选择第一个未完成的任务（Phase 1-2 优先）。专注 Skill 层和 MCP Server 相关工作。写完代码后必须跑 ruff check + mypy + pytest，通过后 commit + push，然后继续下一个任务。不停迭代。"
    "读取 AUTONOMOUS.md，然后从 task_plan.md 中选择中间的未完成任务（Phase 3-4 优先）。专注代码分析引擎和多语言优化。写完代码后必须跑 ruff check + mypy + pytest，通过后 commit + push，然后继续下一个任务。不停迭代。"
    "读取 AUTONOMOUS.md，然后从 task_plan.md 中选择最后的未完成任务（Phase 5-7 优先）。专注性能优化、测试覆盖率和代码质量。写完代码后必须跑 ruff check + mypy + pytest，通过后 commit + push，然后继续下一个任务。不停迭代。"
    "读取 AUTONOMOUS.md，从 task_plan.md 中选择任何未完成任务。优先做测试覆盖和文档完善。写完代码后必须跑 ruff check + mypy + pytest，通过后 commit + push，然后继续下一个任务。不停迭代。"
    "读取 AUTONOMOUS.md，从 task_plan.md 中选择任何未完成任务。优先做性能基准测试和优化。写完代码后必须跑 ruff check + mypy + pytest，通过后 commit + push，然后继续下一个任务。不停迭代。"
)

# 启动 worker
for i in $(seq 1 $WORKERS); do
    IDX=$(( (i - 1) % ${#WORKER_PROMPTS[@]} ))
    PROMPT="${WORKER_PROMPTS[$IDX]}"
    LOG="$LOG_DIR/worker-$i-$(date '+%Y%m%d-%H%M%S').log"

    echo "启动 Worker $i (PID 将记录到 $LOG)"
    nohup claude --print "$PROMPT" > "$LOG" 2>&1 &
    PID=$!
    PIDS+=($PID)
    echo "  Worker $i → PID $PID"
    sleep 2
done

echo ""
echo "所有 $WORKERS 个 worker 已启动"
echo "监控命令："
echo "  tail -f $LOG_DIR/worker-1-*.log   # Worker 1 日志"
echo "  git log --oneline -10             # 查看 commit"
echo "  ps aux | grep 'claude --print'    # 查看进程"
echo "  kill ${PIDS[*]}                    # 停止所有"
echo ""
echo "等待 worker 完成（或按 Ctrl+C 停止）..."

# 等待所有 worker
wait
