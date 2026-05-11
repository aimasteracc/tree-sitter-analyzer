#!/bin/bash
# =============================================================================
# tree-sitter-analyzer 全自动开发 — DeepSeek TUI 版本
# 
# 基于 Claude Code 版本的 5 层架构 + 永续循环 + 7 防御模式
# 适配为 DeepSeek TUI 原生调度系统
# =============================================================================

set -euo pipefail

PROJECT_DIR="${1:-/Users/aisheng.yu/git-private/tree-sitter-analyzer}"
DS_DIR="${HOME}/.deepseek"
RUNTIME_DIR="${PROJECT_DIR}/.autonomous-runtime"
STATE_FILE="${RUNTIME_DIR}/autonomous-state.json"

mkdir -p "${RUNTIME_DIR}"

# ── 停止条件检测 ──────────────────────────────────────────────
check_stop_conditions() {
    cd "${PROJECT_DIR}"
    
    # 条件1: OpenSpec changes 全部完成
    local pending=0
    for dir in openspec/changes/*/; do
        if [ -f "${dir}tasks.md" ] && [ ! -d "${dir}archive" ] 2>/dev/null; then
            pending=$((pending + 1))
        fi
    done
    
    # 条件2: 最近5个提交中 .py 变更 < 3
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
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║  tree-sitter-analyzer 自主开发 — DeepSeek TUI 版本  ║"
    echo "╚══════════════════════════════════════════════════════╝"
    
    local iteration=0
    
    while true; do
        iteration=$((iteration + 1))
        echo ""
        echo "━━━ Iteration ${iteration} @ $(date) ━━━"
        
        # 1. 停止检测
        if check_stop_conditions; then
            break
        fi
        
        # 2. 同步状态
        sync_state
        
        # 3. 轮询 — 给 DS TUI schedule 时间工作
        echo "[$(date)] 等待 30 分钟进行下一轮检查..."
        sleep 1800
    done
    
    echo "[$(date)] 自主开发循环结束"
}

main
