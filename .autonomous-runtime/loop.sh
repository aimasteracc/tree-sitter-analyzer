#!/bin/bash
# =============================================================================
# tree-sitter-analyzer 全自动开发 — DeepSeek TUI 版本
#
# 基于 Claude Code 版本的 5 层架构 + 永续循环 + 7 防御模式
# 适配为 DeepSeek TUI 原生调度系统
# =============================================================================

set -euo pipefail

PROJECT_DIR="${1:-/Users/aisheng.yu/git-private/tree-sitter-analyzer}"
RUNTIME_DIR="${PROJECT_DIR}/.autonomous-runtime"
STATE_FILE="${RUNTIME_DIR}/autonomous-state.json"
LOCK_FILE="${RUNTIME_DIR}/loop.lock"
LOG_FILE="${RUNTIME_DIR}/autonomous-loop.log"
SLEEP_SECONDS="${TS_AUTONOMY_SLEEP_SECONDS:-1800}"
WIKI_DIR="/Users/aisheng.yu/wiki/wiki"

mkdir -p "${RUNTIME_DIR}"

cleanup_lock() {
    rm -f "${LOCK_FILE}"
}

acquire_lock() {
    if command -v flock >/dev/null 2>&1; then
        exec 9>"${LOCK_FILE}"
        if ! flock -n 9; then
            echo "[$(date)] ⚠️ loop.sh 已有实例运行中（flock），本次启动退出。" >&2
            exit 0
        fi
        trap 'cleanup_lock' EXIT
        echo "[$(date)] ✅ 通过 flock 获取锁" >> "${LOG_FILE}"
        return 0
    fi

    if [ -f "${LOCK_FILE}" ]; then
        local current_pid
        current_pid="$(cat "${LOCK_FILE}" 2>/dev/null || true)"
        if [ -n "${current_pid}" ] && ps -p "${current_pid}" >/dev/null 2>&1; then
            echo "[$(date)] ⚠️ loop.sh 已有实例运行中（pid=${current_pid}），本次启动退出。" >&2
            exit 0
        fi
    fi

    echo "$$" > "${LOCK_FILE}"
    trap 'cleanup_lock' EXIT
    echo "[$(date)] ✅ 通过 pid 锁获取锁: $$" >> "${LOG_FILE}"
}

report_wiki_snapshots() {
    echo "[wiki] check-start: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${LOG_FILE}"
    while IFS= read -r path; do
        [ -f "$path" ] || continue
        echo "[wiki] $(basename "$path")" >> "${LOG_FILE}"
    done < <(printf '%s\n' \
        "${WIKI_DIR}/ts-analyzer-autonomous-dev-design.md" \
        "${WIKI_DIR}/tree-sitter-analyzer-autonomous-dev-capability.md" \
        "${WIKI_DIR}/tree-sitter-analyzer-24x7-autonomous-dev-monitoring.md" \
        "${WIKI_DIR}/tree-sitter-analyzer-test-mastery.md")
}

# ── 停止条件检测 ──────────────────────────────────────────────
check_stop_conditions() {
    cd "${PROJECT_DIR}"

    local pending=0
    for dir in openspec/changes/*/; do
        if [ -f "${dir}tasks.md" ] && [ ! -d "${dir}archive" ] 2>/dev/null; then
            pending=$((pending + 1))
        fi
    done

    local py_changes
    py_changes=$(git log -5 --oneline --name-only --pretty=format: | grep "\.py$" | wc -l | tr -d ' ')

    echo "[$(date)] 停止检测: ${pending} OpenSpec changes 待完成, ${py_changes} 个 .py 变更"

    if [ "${pending}" -eq 0 ] && [ "${py_changes}" -lt 3 ]; then
        echo "[$(date)] 🎉 停止条件触发 — 项目已稳定"
        return 0
    fi
    return 1
}

# ── 状态同步 ──────────────────────────────────────────────────
sync_state() {
    cd "${PROJECT_DIR}"

    local commits tools tests
    commits=$(git rev-list --count HEAD 2>/dev/null || echo 0)
    tools=$(grep -r "def " tree_sitter_analyzer/mcp/tools/ --include="*.py" 2>/dev/null | wc -l | tr -d ' ')
    tests=$(find tests -name "*.py" -not -name "__init__.py" -not -name "conftest.py" 2>/dev/null | wc -l | tr -d ' ')

    cat > "${STATE_FILE}" << STATEJSON
{
    "last_sync": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "project": "tree-sitter-analyzer",
    "branch": "$(git branch --show-current)",
    "head": "$(git rev-parse --short HEAD)",
    "commits": ${commits},
    "tools": ${tools},
    "test_files": ${tests}
}
STATEJSON
    echo "[$(date)] 状态已同步: ${commits} commits, ${tools} MCP tools, ${tests} test files"
}

# ── 主循环 ────────────────────────────────────────────────────
main() {
    acquire_lock

    echo "╔══════════════════════════════════════════════════════╗"
    echo "║  tree-sitter-analyzer 自主开发 — DeepSeek TUI 版本  ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo "[$(date)] process $$ started"

    local iteration=0
    while true; do
        iteration=$((iteration + 1))
        echo ""
        echo "━━━ Iteration ${iteration} @ $(date) ━━━"
        echo "━━━ Iteration ${iteration} @ $(date) ━━━" >> "${LOG_FILE}"

        report_wiki_snapshots

        # 1. 停止条件检测
        if check_stop_conditions; then
            echo "[iteration ${iteration}] stop conditions met" >> "${LOG_FILE}"
            break
        fi

        # 2. 同步状态
        sync_state >> "${LOG_FILE}"

        # 3. 轮询 — 给 DS TUI schedule 时间工作
        echo "[$(date)] 等待 ${SLEEP_SECONDS} 秒进行下一轮检查..."
        echo "[iteration ${iteration}] sleep ${SLEEP_SECONDS}s" >> "${LOG_FILE}"
        sleep "${SLEEP_SECONDS}"
    done

    echo "[$(date)] 自主开发循环结束"
    echo "[$(date)] 自主开发循环结束" >> "${LOG_FILE}"
}

main
