#!/usr/bin/env python3
"""CLI 输入健壮性回归测试（#1002）。

这些测试固定两个曾经错误处理非法输入的 CLI 路径的失败呈现契约：

* ``--safe-to-edit <dir>`` 曾把目录当作文件静默分析并返回 0。
* ``--agent-workflow <dir>`` 曾返回正确错误信息，却仍以 0 退出。

所有情形在 ``--format json`` 下都必须输出结构化
``{success: false, ...}`` 信封，不得泄漏回溯，并返回非零退出码。

测试通过子进程端到端执行，以覆盖真实进程退出码以及 stdout/stderr 分流；直接调用
处理器无法发现只在进程层出现的回溯。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _run_cli(*cli_args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the TSA CLI in a subprocess from the project root."""
    return subprocess.run(
        [sys.executable, "-m", "tree_sitter_analyzer", *cli_args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


def _assert_no_traceback(proc: subprocess.CompletedProcess[str]) -> None:
    assert "Traceback (most recent call last)" not in proc.stdout
    assert "Traceback (most recent call last)" not in proc.stderr


class TestSafeToEditDirectoryRejection:
    """#1002 finding 1 — --safe-to-edit must reject a directory."""

    def test_safe_to_edit_directory_returns_structured_error(self) -> None:
        proc = _run_cli(
            "--safe-to-edit",
            "tree_sitter_analyzer/cli",
            "--format",
            "json",
        )
        _assert_no_traceback(proc)
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["success"] is False
        assert payload["verdict"] == "ERROR"
        assert "directory" in payload["error"].lower()


class TestAgentWorkflowDirectoryRejection:
    """#1002 finding 3 — --agent-workflow must exit non-zero for a dir."""

    def test_agent_workflow_directory_returns_nonzero_exit(self) -> None:
        proc = _run_cli(
            "--agent-workflow",
            "tree_sitter_analyzer/cli",
            "--format",
            "json",
        )
        _assert_no_traceback(proc)
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["success"] is False
        assert payload["verdict"] == "ERROR"
        assert "directory" in payload["error"].lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
