#!/bin/bash
# =============================================================================
# DeepSeek TUI autonomous development — 状态检查命令（对标 24x7 监控手册）
# =============================================================================

PROJECT_DIR="${1:-/Users/aisheng.yu/git-private/tree-sitter-analyzer}"
cd "${PROJECT_DIR}"

echo "📊 tree-sitter-analyzer 自主开发状态 @ $(date)"
echo ""

# 1. 进程检查
echo "── 1. loop.sh 进程 ──"
if pgrep -f "loop.sh" > /dev/null 2>&1; then
    echo "✅ 运行中: $(pgrep -f loop.sh | head -3)"
else
    echo "❌ 未运行"
fi

if [ -f ".autonomous-runtime/loop.lock" ] && [ -r ".autonomous-runtime/loop.lock" ]; then
    echo "🔐 lock 文件: $(wc -c < .autonomous-runtime/loop.lock) bytes"
fi
if [ -f ".autonomous-runtime/autonomous-loop.log" ]; then
    echo "🧾 最新日志: "
    tail -n 5 .autonomous-runtime/autonomous-loop.log
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
if pgrep -f "loop.sh" > /dev/null 2>&1 && [ "${py_count}" -ge 3 ]; then
    echo "✅ 健康运行 — 有实质性开发活动"
elif pgrep -f "loop.sh" > /dev/null 2>&1; then
    echo "⚠️  可能空转 — loop.sh 运行中但 .py 变更较少"
else
    echo "❌ 已停止 — 重启: .autonomous-runtime/loop.sh"
fi
