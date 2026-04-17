#!/usr/bin/env python3
"""
Context Auto-Reset System for 24x7 Autonomous Development

基于 Hermes Agent 的 session lineage 和 dual compression 系统设计。
支持自动检测 context 使用率，触发 reset，并恢复状态继续工作。

核心概念:
1. Session Lineage: 每个 session 有唯一的 lineage_id，子 session 继承父 session 的状态
2. Dual Compression: 压缩历史消息 + 保留关键状态
3. Persistent State: 使用 JSON 文件存储状态（可扩展为 SQLite）
4. Auto-Reset Detection: 监控 context 使用率，自动触发 reset
5. State Transfer: Reset 前保存状态，Reset 后恢复
"""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any


class ContextAutoReset:
    """
    Context Auto-Reset Manager

    监控 Claude Code session 的 context 使用率，
    当达到阈值时自动触发 /clear 并恢复工作状态。
    """

    def __init__(self, project_root: Path, state_file: str = ".autonomous-state.json"):
        self.project_root = project_root
        self.state_file = project_root / state_file
        self.state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        """Load persistent state from JSON file."""
        if self.state_file.exists():
            with open(self.state_file) as f:
                return json.load(f)
        return {
            "lineage_id": self._generate_lineage_id(),
            "session_count": 0,
            "total_commits": 0,
            "total_tools_added": 0,
            "current_phase": "init",
            "last_task": None,
            "context_resets": 0,
            "created_at": datetime.now().isoformat(),
        }

    def _save_state(self) -> None:
        """Save state to JSON file."""
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def _generate_lineage_id(self) -> str:
        """Generate unique lineage ID for this autonomous development run."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"autonomous_dev_{timestamp}"

    def get_context_usage(self) -> float:
        """
        Get current context usage percentage.

        Returns:
            Context usage as percentage (0-100)
        """
        # 检查最近的提交和文件变更来估算 context 使用
        try:
            result = subprocess.run(
                ["git", "log", "-10", "--oneline", "--name-only"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
            )
            lines = result.stdout.strip().split("\n")
            # 简单估算：每个提交大约消耗一些 context
            # 更准确的方式是读取实际的 Claude Code session 数据
            return min(100, len(lines) * 3)  # 粗略估算
        except Exception:
            return 0

    def should_reset(self, threshold: float = 70.0) -> bool:
        """
        Check if context reset is needed.

        Args:
            threshold: Context usage percentage threshold

        Returns:
            True if reset is needed
        """
        usage = self.get_context_usage()
        return usage >= threshold

    def trigger_reset(self) -> dict[str, Any]:
        """
        Trigger context reset with state preservation.

        1. Save current state to progress.md (summary)
        2. Create reset marker file
        3. Return reset instructions

        Returns:
            Reset information dictionary
        """
        # 更新 lineage（创建子 session）
        self.state["lineage_id"] = f"{self.state['lineage_id']}_child{self.state['context_resets'] + 1}"
        self.state["context_resets"] += 1
        self.state["last_reset_at"] = datetime.now().isoformat()

        # 保存状态
        self._save_state()

        # 创建 reset marker 文件
        reset_marker = self.project_root / ".context-reset-marker"
        with open(reset_marker, "w") as f:
            f.write(f"CONTEXT_RESET_TIMESTAMP={datetime.now().isoformat()}\n")
            f.write(f"LINEAGE_ID={self.state['lineage_id']}\n")
            f.write(f"CONTEXT_RESET_NUMBER={self.state['context_resets']}\n")

        return {
            "action": "reset",
            "lineage_id": self.state["lineage_id"],
            "reset_number": self.state["context_resets"],
            "state_file": str(self.state_file),
            "next_step": "Run /clear and resume from state file",
        }

    def get_recovery_prompt(self) -> str:
        """
        Generate recovery prompt for post-reset continuation.

        Returns:
            Prompt string to resume work
        """
        return f"""
# Context Reset Recovery — Autonomous Development

You are resuming autonomous development after a context reset.

## Lineage Information
- Lineage ID: {self.state['lineage_id']}
- Session Count: {self.state['session_count']}
- Context Resets: {self.state['context_resets']}

## Current State
- Total Commits: {self.state['total_commits']}
- Total Tools Added: {self.state['total_tools_added']}
- Current Phase: {self.state['current_phase']}
- Last Task: {self.state.get('last_task', 'None')}

## Recovery Instructions
1. Read AUTONOMOUS.md for full instructions
2. Read task_plan.md to see current phase
3. Read progress.md to see what was accomplished
4. Read .autonomous-state.json to restore exact state
5. Continue from where you left off — do not repeat completed tasks

## Key Constraint
- NEVER repeat work that was already done
- ALWAYS check task_plan.md for completed phases (marked with [x])
- Continue with the NEXT uncompleted task

Resume autonomous development now.
"""


class ContinuousLoopMonitor:
    """
    Continuous Loop Monitor for 24x7 operation

    在后台持续监控 autonomous-loop.sh 的运行状态，
    检测是否需要 context reset 或进程重启。
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.reset_manager = ContextAutoReset(project_root)
        self.check_interval = 300  # 5 minutes

    def check_loop_status(self) -> dict[str, Any]:
        """Check if autonomous-loop.sh is running and healthy."""
        # 检查进程
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
        )
        is_running = "autonomous-loop.sh" in result.stdout

        # 检查最近的代码变更（是否在空转）
        try:
            result = subprocess.run(
                ["git", "log", "-5", "--oneline", "--name-only", "--pretty=format:"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
            )
            py_files = [line for line in result.stdout.split("\n") if line.endswith(".py")]
            has_code_changes = len(py_files) > 0
        except Exception:
            has_code_changes = False

        # 检查 context 使用率
        context_usage = self.reset_manager.get_context_usage()

        return {
            "is_running": is_running,
            "has_code_changes": has_code_changes,
            "context_usage": context_usage,
            "needs_reset": context_usage >= 70,
            "status": self._get_status_string(is_running, has_code_changes, context_usage),
        }

    def _get_status_string(self, is_running: bool, has_code: bool, usage: float) -> str:
        """Get human-readable status string."""
        if not is_running:
            return "❌ STOPPED"
        if not has_code:
            return "⚠️  IDLE (no code changes)"
        if usage >= 70:
            return "🔄 NEEDS RESET"
        return "✅ HEALTHY"

    def run_monitoring_loop(self, max_iterations: int = 0) -> None:
        """
        Run continuous monitoring loop.

        Args:
            max_iterations: Maximum iterations (0 = infinite)
        """
        iteration = 0
        while max_iterations == 0 or iteration < max_iterations:
            iteration += 1
            status = self.check_loop_status()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            print(f"[{timestamp}] Status: {status['status']}")
            print(f"  - Running: {status['is_running']}")
            print(f"  - Code changes: {status['has_code_changes']}")
            print(f"  - Context usage: {status['context_usage']}%")

            # 处理各种状态
            if not status["is_running"]:
                print("⚠️  autonomous-loop.sh stopped, restarting...")
                self._restart_loop()

            elif status["needs_reset"]:
                print("🔄 Context usage high, triggering reset...")
                reset_info = self.reset_manager.trigger_reset()
                print(f"  Reset info: {reset_info}")

                # 创建 recovery 文件供下次 session 使用
                recovery_file = self.project_root / ".recovery-prompt.txt"
                with open(recovery_file, "w") as f:
                    f.write(self.reset_manager.get_recovery_prompt())
                print(f"  Recovery prompt saved to {recovery_file}")

            elif not status["has_code_changes"]:
                print("⚠️  No code changes detected, checking for idle...")

            # 等待下次检查
            time.sleep(self.check_interval)

    def _restart_loop(self) -> None:
        """Restart autonomous-loop.sh."""
        subprocess.Popen(
            ["./scripts/autonomous-loop.sh"],
            cwd=self.project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main():
    """Main entry point for context auto-reset system."""
    import sys

    project_root = Path(__file__).parent.parent

    if len(sys.argv) > 1 and sys.argv[1] == "monitor":
        # 启动持续监控
        monitor = ContinuousLoopMonitor(project_root)
        print("Starting continuous loop monitor (Ctrl+C to stop)...")
        try:
            monitor.run_monitoring_loop()
        except KeyboardInterrupt:
            print("\nMonitor stopped by user")
    else:
        # 单次检查
        reset_manager = ContextAutoReset(project_root)
        usage = reset_manager.get_context_usage()
        print(f"Context usage: {usage}%")

        if reset_manager.should_reset():
            print("Context reset needed!")
            reset_info = reset_manager.trigger_reset()
            print(json.dumps(reset_info, indent=2))
        else:
            print("Context usage OK, no reset needed.")


if __name__ == "__main__":
    main()
