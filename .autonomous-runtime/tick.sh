#!/bin/bash
# Idempotent 5-minute heartbeat entrypoint for the autonomous runtime.

set -euo pipefail

PROJECT_DIR="${1:-/Users/aisheng.yu/git-private/tree-sitter-analyzer}"
RUNTIME_DIR="${PROJECT_DIR}/.autonomous-runtime"
STATUS_SCRIPT="${RUNTIME_DIR}/status.sh"
LOOP_SCRIPT="${RUNTIME_DIR}/loop.sh"
TICK_STATE="${RUNTIME_DIR}/last-tick.json"
LOOP_STDOUT_LOG="/tmp/ts-analyzer-autonomous-loop.log"
SLEEP_SECONDS="${TS_AUTONOMY_SLEEP_SECONDS:-300}"

cd "${PROJECT_DIR}"

get_lock_pid() {
    local lock_file="${RUNTIME_DIR}/loop.lock"
    [ -r "${lock_file}" ] || return 0
    tr -cd '0-9' < "${lock_file}" 2>/dev/null || true
}

get_loop_pids() {
    local lock_pid
    lock_pid="$(get_lock_pid)"
    if [ -n "${lock_pid}" ] && ps -p "${lock_pid}" -o pid= >/dev/null 2>&1; then
        echo "${lock_pid}"
        return 0
    fi

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
    return 1
}

write_tick_state() {
    local action="$1"
    local loop_status="$2"
    local pids="$3"

    cat > "${TICK_STATE}" << JSON
{
  "last_tick": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "action": "${action}",
  "heartbeat_status": "recorded",
  "loop_probe_status": "${loop_status}",
  "loop_pids": "${pids}",
  "branch": "$(git branch --show-current 2>/dev/null || true)",
  "head": "$(git rev-parse --short HEAD 2>/dev/null || true)"
}
JSON
}

start_loop() {
    nohup env TS_AUTONOMY_SLEEP_SECONDS="${SLEEP_SECONDS}" "${LOOP_SCRIPT}" "${PROJECT_DIR}" >"${LOOP_STDOUT_LOG}" 2>&1 &
}

main() {
    local action="ready"
    local loop_status="running"
    local pids

    if ! is_loop_running; then
        action="start_attempted"
        start_loop
        sleep 1
    fi

    if is_loop_running; then
        pids="$(get_loop_pids | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
        write_tick_state "${action}" "${loop_status}" "${pids}"
        echo "AUTONOMY_TICK ${action} heartbeat=recorded loop_probe=${loop_status} pids=${pids}"
        exit 0
    fi

    action="start_failed"
    loop_status="stopped"
    pids=""
    write_tick_state "${action}" "${loop_status}" "${pids}"
    echo "AUTONOMY_TICK ${action} heartbeat=recorded loop_probe=${loop_status}"
    "${STATUS_SCRIPT}" || true
    exit 1
}

main "$@"
