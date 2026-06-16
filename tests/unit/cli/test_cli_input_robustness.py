#!/usr/bin/env python3
"""CLI input-robustness regression tests (#1002, #1003).

These tests pin the *failure presentation* contract for three CLI input
paths that previously mishandled bad input:

* ``--batch-search`` with a missing / malformed ``--batch-search-queries-json``
  used to leak a raw Python traceback instead of a structured error envelope
  (#1003).
* ``--safe-to-edit <dir>`` used to silently analyze a directory as a file and
  exit 0 (#1002, finding 1).
* ``--agent-workflow <dir>`` returned the right error message but exited 0
  (#1002, finding 3).

All cases must now: emit a structured ``{success: false, ...}`` envelope on
``--format json``, never leak a traceback, and return a non-zero exit code.

Run end-to-end via subprocess so the assertions cover the real process exit
code and the real stdout/stderr split (a traceback only surfaces at process
level, not when calling handlers in-process).
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
        timeout=180,
    )


def _assert_no_traceback(proc: subprocess.CompletedProcess[str]) -> None:
    assert "Traceback (most recent call last)" not in proc.stdout
    assert "Traceback (most recent call last)" not in proc.stderr


class TestBatchSearchInputRobustness:
    """#1003 — no raw traceback for bad --batch-search-queries-json."""

    def test_batch_search_missing_queries_json_returns_structured_error(self) -> None:
        proc = _run_cli(
            "--batch-search",
            "--batch-search-queries-json",
            "/nonexistent/path/does/not/exist.json",
            "--format",
            "json",
        )
        _assert_no_traceback(proc)
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["success"] is False
        assert payload["verdict"] == "ERROR"
        assert isinstance(payload["error"], str)

    def test_batch_search_malformed_json_returns_structured_error(
        self, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not-json{]", encoding="utf-8")
        proc = _run_cli(
            "--batch-search",
            "--batch-search-queries-json",
            str(bad),
            "--format",
            "json",
        )
        _assert_no_traceback(proc)
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["success"] is False
        assert payload["verdict"] == "ERROR"
        assert isinstance(payload["error"], str)


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
