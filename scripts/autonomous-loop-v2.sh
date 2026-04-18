#!/bin/bash
# autonomous-loop-v2.sh — 稳定单 worker 永续自主开发循环
#
# v1 的问题：AskUserQuestion 阻塞 + tee 信号穿透 + 无超时 + 内存崩溃
# v2 的方案：setsid 隔离 + 日志 mtime dead-man + flock 防并发 + 指数退避
#
# 用法: ./scripts/autonomous-loop-v2.sh
# 配置: 环境变量覆盖 > .autonomous-runtime/config.env > 默认值
#
# 按 Ctrl+C 优雅停止（会杀掉整个 claude 进程组）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# ─── 配置（环境变量覆盖 > config.env > 默认值）───

RUNTIME_DIR="$PROJECT_DIR/.autonomous-runtime"
LOG_DIR="$PROJECT_DIR/autonomous-logs"

if [ -f "$RUNTIME_DIR/config.env" ]; then
    set -a
    source "$RUNTIME_DIR/config.env"
    set +a
fi

SESSION_TIMEOUT=${SESSION_TIMEOUT:-${AUTONOMOUS_SESSION_TIMEOUT:-1800}}
DEADMAN_TIMEOUT=${DEADMAN_TIMEOUT:-${AUTONOMOUS_DEADMAN_TIMEOUT:-600}}
POLL_INTERVAL=${POLL_INTERVAL:-${AUTONOMOUS_POLL_INTERVAL:-30}}
COOLDOWN_SEC=${COOLDOWN_SEC:-${AUTONOMOUS_COOLDOWN:-30}}
MIN_DISK_GB=${MIN_DISK_GB:-5}
BACKOFF_MAX=${BACKOFF_MAX:-300}
KILL_GRACE_SEC=${KILL_GRACE_SEC:-10}

# ─── 初始化 ───

mkdir -p "$RUNTIME_DIR" "$LOG_DIR"

LOCKFILE="$RUNTIME_DIR/loop.lock"
PIDFILE="$RUNTIME_DIR/loop.pid"

if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "另一个实例在运行 (PID $OLD_PID)"
        echo "如需强制停止: kill $OLD_PID"
        exit 1
    fi
    rm -f "$PIDFILE"
fi
echo $$ > "$PIDFILE"

SESSION=0
START_TIME=$(date +%s)
CLAUDE_PGID=""
BACKOFF=1

echo "======================================================="
echo "  Tree-sitter-analyzer 自主开发 v2（稳定版）"
echo "  Session timeout: ${SESSION_TIMEOUT}s"
echo "  Dead-man timeout: ${DEADMAN_TIMEOUT}s"
echo "  Poll interval: ${POLL_INTERVAL}s"
echo "  开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  按 Ctrl+C 停止"
echo "======================================================="
echo ""

# ─── 信号处理（防重入）───

CLEANING=0
cleanup() {
    [ "$CLEANING" = 1 ] && return
    CLEANING=1

    echo ""
    echo "收到停止信号，清理进程..."

    if [ -n "$CLAUDE_PGID" ]; then
        echo "  发送 SIGTERM 到 claude (PID $CLAUDE_PGID)..."
        kill "$CLAUDE_PGID" 2>/dev/null || true
        # 杀死 claude 的子进程（subagents 等）
        pkill -P "$CLAUDE_PGID" 2>/dev/null || true

        local w=0
        while kill -0 "$CLAUDE_PGID" 2>/dev/null && [ $w -lt "$KILL_GRACE_SEC" ]; do
            sleep 1
            w=$((w + 1))
        done

        if kill -0 "$CLAUDE_PGID" 2>/dev/null; then
            echo "  强制 SIGKILL..."
            kill -9 "$CLAUDE_PGID" 2>/dev/null || true
            pkill -9 -P "$CLAUDE_PGID" 2>/dev/null || true
        fi
    fi

    rm -f "$PIDFILE"

    local elapsed=$(( $(date +%s) - START_TIME ))
    local hours=$(( elapsed / 3600 ))
    local mins=$(( (elapsed % 3600) / 60 ))
    echo "======================================================="
    echo "  已停止"
    echo "  运行时间: ${hours}h ${mins}m"
    echo "  完成 session: $SESSION"
    echo "======================================================="

    exit 0
}
trap cleanup EXIT INT TERM HUP

# ─── 辅助函数 ───

ensure_gstack_configured() {
    mkdir -p ~/.gstack
    touch ~/.gstack/.completeness-intro-seen 2>/dev/null || true
    touch ~/.gstack/.telemetry-prompted 2>/dev/null || true
    touch ~/.gstack/.proactive-prompted 2>/dev/null || true
    touch ~/.gstack/.routing-declined 2>/dev/null || true
}

check_disk() {
    local available_gb
    available_gb=$(df -g . 2>/dev/null | awk 'NR==2{print $4}')
    if [ -z "$available_gb" ] || [ "$available_gb" -lt "$MIN_DISK_GB" ] 2>/dev/null; then
        echo "磁盘空间不足: ${available_gb:-unknown}GB < ${MIN_DISK_GB}GB"
        return 1
    fi
    return 0
}

get_logfile() {
    echo "$LOG_DIR/$(date '+%Y%m%d').log"
}

get_session_prompt() {
    local recovery="$RUNTIME_DIR/recovery-prompt.txt"

    if [ -f "$recovery" ]; then
        echo "读取 AUTONOMOUS.md 恢复上次 session。

上次 session 留下了恢复指令，内容如下：
$(cat "$recovery")

恢复后继续自主开发。严格遵循 AUTONOMOUS.md 的所有规则。
完成后删除 $recovery 文件。

⚠️  禁止使用 AskUserQuestion！
⚠️  遇到需要确认的情况，直接做决定并继续！

现在开始恢复。"
        return
    fi

    echo "读取 AUTONOMOUS.md 的全部内容，严格遵循其中的所有规则进行自主开发。

核心要求：
1. 检查是否有未完成的 OpenSpec change，有就继续实现
2. 如果没有，执行 AUTONOMOUS.md 中定义的「永续循环机制」
3. 在「永续循环」中：
   - 调用 /steve-jobs-perspective 做产品分析
   - 调用 /plan-eng-review 做架构分析
   - 重要：要求 Skill「分析并给出建议」，不要让 Skill 问问题
4. 每完成一个 Sprint 就 commit + push
5. Context 使用率 > 70% 时更新三文件并停止

关键：深度分析必须有，但 Skill 调用方式要正确——要求分析而非问答。

**Self-Hosting 质量门禁（必须执行）**：
每个 Sprint 完成后、commit 之前，用项目自己的工具扫描新增文件：
- type_annotation_coverage → 检查新代码的类型标注率（目标 ≥80%）
- magic_values → 检查新代码中的魔法值
- code_smell_detector → 检查新代码的代码异味
这是 dogfooding：如果工具不能在自己的代码库上发现问题，说明工具不够好。
检查结果记录到 findings.md，严重问题修复后再 commit。

⚠️  禁止使用 AskUserQuestion！
⚠️  遇到需要确认的情况，直接做决定并继续！
⚠️  不要等待用户输入！

现在开始。"
}

# ─── 预配置 ───

ensure_gstack_configured

# ─── 主循环 ───

while true; do
    SESSION=$((SESSION + 1))
    LOGFILE=$(get_logfile)

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Session $SESSION"
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  日志: $LOGFILE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 磁盘检查
    if ! check_disk; then
        echo "等待 60s 后重试..."
        sleep 60
        continue
    fi

    # 确认在正确分支
    BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
    if [ "$BRANCH" != "feat/autonomous-dev" ]; then
        echo "分支不对 ($BRANCH)，切换到 feat/autonomous-dev"
        git checkout feat/autonomous-dev 2>/dev/null || true
    fi

    # 拉取最新（允许失败）
    git pull --rebase origin feat/autonomous-dev 2>/dev/null || true

    # 构造 prompt
    PROMPT=$(get_session_prompt)

    # 启动 claude（重定向到文件，不用 tee）
    # macOS 没有 setsid，claude 与脚本同进程组
    # kill 时用 PID + pkill 子进程
    claude --print "$PROMPT" >> "$LOGFILE" 2>&1 &
    CLAUDE_PID=$!

    # 等 claude 进程启动后获取 PGID
    sleep 1
    CLAUDE_PGID=$(ps -o pgid= -p "$CLAUDE_PID" 2>/dev/null | tr -d ' ' || echo "")

    if [ -z "$CLAUDE_PGID" ]; then
        echo "  ⚠️  无法获取 PGID，使用 PID 作为 fallback"
        CLAUDE_PGID="$CLAUDE_PID"
    fi

    echo "  Claude PID: $CLAUDE_PID, PGID: $CLAUDE_PGID"

    START_OF_ROUND=$(date '+%Y-%m-%d %H:%M:%S')

    # Watchdog 轮询（主进程循环，无孤儿风险）
    # Dead-man 策略: 1) 进程存活检查 2) CPU 活跃检查 3) 日志 mtime（补充）
    WD_ELAPSED=0
    WD_LAST_CPU_SECS=""
    WD_CPU_STALLED=0
    while kill -0 "$CLAUDE_PID" 2>/dev/null; do
        sleep "$POLL_INTERVAL"
        WD_ELAPSED=$((WD_ELAPSED + POLL_INTERVAL))

        # 超时检查（硬上限）
        if [ $WD_ELAPSED -ge "$SESSION_TIMEOUT" ]; then
            echo ""
            echo "⏰ Session 超时 (${SESSION_TIMEOUT}s)，终止 claude (PID $CLAUDE_PID)"
            kill "$CLAUDE_PID" 2>/dev/null || true
            pkill -P "$CLAUDE_PID" 2>/dev/null || true
            sleep "$KILL_GRACE_SEC"
            kill -9 "$CLAUDE_PID" 2>/dev/null || true
            pkill -9 -P "$CLAUDE_PID" 2>/dev/null || true
            break
        fi

        # Dead-man: CPU 时间检查（claude --print stdout 有缓冲，日志 mtime 不可靠）
        # 如果进程 CPU 时间在 DEADMAN_TIMEOUT 内没增长，说明卡了
        WD_CURRENT_CPU=$(ps -o time= -p "$CLAUDE_PID" 2>/dev/null | tr -d ' ' || echo "")
        if [ -n "$WD_CURRENT_CPU" ]; then
            # 转换 HH:MM:SS 为总秒数
            WD_CPU_SECS=$(echo "$WD_CURRENT_CPU" | awk -F: '{if (NF==3) print $1*3600+$2*60+$3; else if (NF==2) print $1*60+$2; else print $1}')
            if [ -n "$WD_LAST_CPU_SECS" ] && [ "$WD_CPU_SECS" = "$WD_LAST_CPU_SECS" ]; then
                WD_CPU_STALLED=$((WD_CPU_STALLED + POLL_INTERVAL))
                if [ "$WD_CPU_STALLED" -gt "$DEADMAN_TIMEOUT" ]; then
                    echo ""
                    echo "💀 CPU 时间 ${DEADMAN_TIMEOUT}s 无增长 (stalled=${WD_CPU_STALLED}s)，终止 claude"
                    kill "$CLAUDE_PID" 2>/dev/null || true
                    pkill -P "$CLAUDE_PID" 2>/dev/null || true
                    sleep "$KILL_GRACE_SEC"
                    kill -9 "$CLAUDE_PID" 2>/dev/null || true
                    pkill -9 -P "$CLAUDE_PID" 2>/dev/null || true
                    break
                fi
            else
                WD_CPU_STALLED=0
            fi
            WD_LAST_CPU_SECS="$WD_CPU_SECS"
        fi
    done

    # 收尸（防 zombie）
    wait "$CLAUDE_PID" 2>/dev/null || true
    EXIT_CODE=$?

    # 清理 recovery prompt（已使用）
    rm -f "$RUNTIME_DIR/recovery-prompt.txt" 2>/dev/null || true

    # 清理 context reset marker
    rm -f .context-reset-marker 2>/dev/null || true

    # 退出码处理 + 退避
    case $EXIT_CODE in
        0)
            echo "  Session $SESSION 正常完成"
            BACKOFF=1
            ;;
        130|143)
            echo "  Session $SESSION 被信号终止 (exit=$EXIT_CODE)"
            BACKOFF=1
            ;;
        *)
            echo "  Session $SESSION 异常退出 (exit=$EXIT_CODE)"
            BACKOFF=$((BACKOFF * 2))
            if [ $BACKOFF -gt "$BACKOFF_MAX" ]; then
                BACKOFF=$BACKOFF_MAX
            fi
            ;;
    esac

    # 打印本轮产出
    RECENT_COMMITS=$(git log --oneline --since="$START_OF_ROUND" 2>/dev/null | wc -l | tr -d ' ')
    echo "  本轮 commit: ${RECENT_COMMITS:-0}"

    # Session 间日志分割
    echo "" >> "$LOGFILE"
    echo "===== Session $SESSION 结束 at $(date '+%Y-%m-%d %H:%M:%S') (exit=$EXIT_CODE) =====" >> "$LOGFILE"

    # Cooldown
    echo "  ${BACKOFF}s 后启动下一个 session..."
    sleep "$BACKOFF"

    # 重置 PGID（已无用）
    CLAUDE_PGID=""
done
