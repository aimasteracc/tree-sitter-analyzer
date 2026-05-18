#!/bin/bash
# =============================================================================
# DeepSeek TUI autonomous development — 状态检查命令（对标 24x7 监控手册）
# =============================================================================

PROJECT_DIR="${1:-/Users/aisheng.yu/git-private/tree-sitter-analyzer}"
cd "${PROJECT_DIR}"

RUNTIME_DIR="${PROJECT_DIR}/.autonomous-runtime"
LOOP_SCRIPT="${RUNTIME_DIR}/loop.sh"
LOCK_FILE="${RUNTIME_DIR}/loop.lock"
TICK_STATE="${RUNTIME_DIR}/last-tick.json"
HEARTBEAT_MAX_AGE_SECONDS="${TS_AUTONOMY_HEARTBEAT_MAX_AGE_SECONDS:-600}"

get_loop_pids() {
    local lock_pid
    if [ -r "${LOCK_FILE}" ]; then
        lock_pid="$(tr -cd '0-9' < "${LOCK_FILE}" 2>/dev/null || true)"
        if [ -n "${lock_pid}" ] && ps -p "${lock_pid}" -o pid= >/dev/null 2>&1; then
            echo "${lock_pid}"
        fi
    fi

    # Match the concrete runtime script path, then exclude common probe commands.
    pgrep -f "${LOOP_SCRIPT}" 2>/dev/null | while IFS= read -r pid; do
        [ -z "${pid}" ] && continue
        ps -p "${pid}" -o command= 2>/dev/null \
            | grep -F "${LOOP_SCRIPT}" \
            | grep -Ev 'pgrep|grep|status\.sh|tick\.sh' >/dev/null || continue
        echo "${pid}"
    done
}

is_loop_running() {
    local pid

    while IFS= read -r pid; do
        [ -z "${pid}" ] && continue
        if ps -p "${pid}" -o pid= >/dev/null 2>&1; then
            return 0
        fi
    done < <(get_loop_pids)

    if [ -f "${LOCK_FILE}" ]; then
        # 清理死 pid 的残留 lock
        rm -f "${LOCK_FILE}"
    fi
    return 1
}

file_mtime_epoch() {
    local path="$1"
    stat -f %m "${path}" 2>/dev/null || stat -c %Y "${path}" 2>/dev/null || echo 0
}

heartbeat_age_seconds() {
    if [ ! -f "${TICK_STATE}" ]; then
        echo 999999
        return 0
    fi

    local now mtime
    now="$(date +%s)"
    mtime="$(file_mtime_epoch "${TICK_STATE}")"
    echo $((now - mtime))
}

is_heartbeat_recent() {
    local age
    age="$(heartbeat_age_seconds)"
    [ "${age}" -le "${HEARTBEAT_MAX_AGE_SECONDS}" ]
}

echo "📊 tree-sitter-analyzer 自主开发状态 @ $(date)"
echo ""

# 1. 进程检查
echo "── 1. loop.sh 进程 ──"
if is_loop_running; then
    loop_pids="$(get_loop_pids | sort -u | tr '\n' ' ')"
    echo "✅ 运行中: ${loop_pids}"
else
    echo "❌ 未运行"
fi

if [ -f "${LOCK_FILE}" ] && [ -r "${LOCK_FILE}" ]; then
    echo "🔐 lock 文件: $(wc -c < "${LOCK_FILE}") bytes"
fi
if [ -f ".autonomous-runtime/autonomous-loop.log" ]; then
    echo "🧾 最新日志: "
    tail -n 5 .autonomous-runtime/autonomous-loop.log
fi

echo ""
echo "── 1b. Codex heartbeat ──"
if [ -f "${TICK_STATE}" ]; then
    tick_age="$(heartbeat_age_seconds)"
    echo "最近 tick: ${tick_age}s ago"
    echo "状态文件: ${TICK_STATE}"
else
    tick_age=999999
    echo "最近 tick: 不存在"
fi

# 2. Git 提交
echo ""
echo "── 2. 最近提交 ──"
git log -5 --oneline --pretty=format:"%h %s (%ar)" 2>/dev/null || echo "无提交"

# 3. .py 变更
echo ""
echo "── 3. .py 文件变更 ──"
py_count=$(git log -5 --oneline --name-only --pretty=format: 2>/dev/null | grep "\.py$" | wc -l | tr -d ' ')
echo "最近5提交: ${py_count} 个 .py 文件"

# 4. OpenSpec
echo ""
echo "── 4. OpenSpec changes ──"
pending=0
for dir in openspec/changes/*/; do
    if [ -f "${dir}tasks.md" ] 2>/dev/null; then
        pending=$((pending + 1))
        echo "  📋 $(basename ${dir})"
    fi
done
[ "${pending}" -eq 0 ] && echo "  全部完成"

# 5. 自主状态
echo ""
echo "── 5. 自主状态 ──"
if [ -f ".autonomous-runtime/autonomous-state.json" ]; then
    cat .autonomous-runtime/autonomous-state.json 2>/dev/null
else
    echo "  状态文件不存在"
fi

# 6. 结论
echo ""
if is_loop_running && [ "${py_count}" -ge 3 ]; then
    echo "✅ 健康运行 — loop 探针在线且有实质性开发活动"
elif is_loop_running; then
    echo "⚠️  loop 探针在线 — .py 变更较少，需看 Codex heartbeat 是否在推进"
elif is_heartbeat_recent; then
    echo "✅ 健康运行 — Codex 5分钟 heartbeat 最近在线，loop.sh 只是辅助探针"
else
    echo "❌ 已停止 — 运行: .autonomous-runtime/tick.sh 或检查 Codex heartbeat 自动化"
fi
