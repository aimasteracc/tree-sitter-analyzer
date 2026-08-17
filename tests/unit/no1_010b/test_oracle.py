"""Contract tests for the NO1-010B oracle wrapper (RFC-0026 §3, C19)."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import Mock

import pytest

from tree_sitter_analyzer.no1_010b.oracle import (
    OracleStatus,
    _kill_process_tree,
    _parse_result_line,
    _reap_process,
    run_oracle,
)

ORACLE_PASS = (
    "#!/usr/bin/env python3\n"
    "print('NO1_010B_ORACLE_REASON: dispatch-returns-none')\n"
    "print('NO1_010B_ORACLE_RESULT: PASS')\n"
)
ORACLE_FAIL = (
    "#!/usr/bin/env python3\n"
    "print('NO1_010B_ORACLE_REASON: dispatch-returns-none')\n"
    "print('NO1_010B_ORACLE_RESULT: FAIL')\n"
)
ORACLE_CRASH = "#!/usr/bin/env python3\nraise ImportError('missing dep')\n"
ORACLE_SYNTAX = "#!/usr/bin/env python3\ndef broken(:\n"
ORACLE_MALFORMED = (
    "#!/usr/bin/env python3\n"
    "print('NO1_010B_ORACLE_REASON: dispatch-returns-none')\n"
    "print('NO1_010B_ORACLE_RESULT: MAYBE')\n"
)
ORACLE_NOMARKER = "#!/usr/bin/env python3\nprint('everything is fine')\n"
ORACLE_HANG = "#!/usr/bin/env python3\nimport time\ntime.sleep(300)\n"


def _write_oracle(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (ORACLE_PASS, OracleStatus.PASS),
        (ORACLE_FAIL, OracleStatus.FAIL),
        # C19: uncaught exceptions and syntax errors are UNKNOWN, never FAIL.
        (ORACLE_CRASH, OracleStatus.UNKNOWN),
        (ORACLE_SYNTAX, OracleStatus.UNKNOWN),
        # Missing/malformed declared result -> UNKNOWN.
        (ORACLE_MALFORMED, OracleStatus.UNKNOWN),
        (ORACLE_NOMARKER, OracleStatus.UNKNOWN),
    ],
)
def test_run_oracle_classifies_declared_results(
    tmp_path: Path, body: str, expected: OracleStatus
) -> None:
    oracle = _write_oracle(tmp_path, "oracle.py", body)
    outcome = run_oracle(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == expected


def test_run_oracle_timeout_is_unknown(tmp_path: Path) -> None:
    oracle = _write_oracle(tmp_path, "hang.py", ORACLE_HANG)
    outcome = run_oracle(
        str(oracle),
        str(tmp_path),
        expected_reason="dispatch-returns-none",
        timeout_s=1.0,
    )
    assert outcome.status == OracleStatus.UNKNOWN
    assert "timed out" in outcome.stdout_tail


def test_run_oracle_missing_file_is_unknown(tmp_path: Path) -> None:
    outcome = run_oracle(
        str(tmp_path / "ghost.py"),
        str(tmp_path),
        expected_reason="dispatch-returns-none",
    )
    assert outcome.status == OracleStatus.UNKNOWN


def test_run_oracle_os_error_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    def boom(*args, **kwargs):
        raise OSError("no such executable")

    monkeypatch.setattr(subprocess, "Popen", boom)
    oracle = _write_oracle(tmp_path, "oracle.py", ORACLE_PASS)
    outcome = run_oracle(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == OracleStatus.UNKNOWN
    assert "could not execute" in outcome.stdout_tail
    monkeypatch.undo()


def test_oracle_command_line_quotes_path() -> None:
    from tree_sitter_analyzer.no1_010b.oracle import oracle_command_line

    assert oracle_command_line("oracles/0001.py") == "oracles/0001.py"
    assert oracle_command_line("my oracle.py") == "'my oracle.py'"


def test_parse_result_line_uses_final_declared_line() -> None:
    assert (
        _parse_result_line(
            "NO1_010B_ORACLE_REASON: dispatch-returns-none\n"
            "NO1_010B_ORACLE_RESULT: FAIL\n",
            "dispatch-returns-none",
        )
        is OracleStatus.FAIL
    )
    assert (
        _parse_result_line(
            "NO1_010B_ORACLE_REASON: dispatch-returns-none\n"
            "NO1_010B_ORACLE_RESULT: pass\n",
            "dispatch-returns-none",
        )
        is OracleStatus.PASS
    )
    assert _parse_result_line("no marker here\n", "reason") is OracleStatus.UNKNOWN
    assert _parse_result_line("", "reason") is OracleStatus.UNKNOWN
    # Blank lines after the marker do not change that it is the final output.
    assert (
        _parse_result_line(
            "NO1_010B_ORACLE_REASON: reason\nNO1_010B_ORACLE_RESULT: PASS\n\n\n",
            "reason",
        )
        is OracleStatus.PASS
    )


def test_parse_result_line_rejects_trailing_diagnostics() -> None:
    # A PASS marker followed by a later diagnostic is NOT final -> UNKNOWN,
    # never a stale PASS (Codex #1307 P2).
    assert (
        _parse_result_line(
            "NO1_010B_ORACLE_REASON: reason\n"
            "NO1_010B_ORACLE_RESULT: PASS\ncleanup warning\n",
            "reason",
        )
        is OracleStatus.UNKNOWN
    )


def test_oracle_env_does_not_inherit_runner_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # C21: the wrapper must not leak the runner's environment into the
    # oracle; a secret present in the parent must be absent in the oracle.
    monkeypatch.setenv("TSA_ORACLE_TEST_SECRET", "leak-me")
    body = (
        "#!/usr/bin/env python3\n"
        "import os\n"
        "ok = 'TSA_ORACLE_TEST_SECRET' not in os.environ\n"
        "print('NO1_010B_ORACLE_REASON: dispatch-returns-none')\n"
        "print('NO1_010B_ORACLE_RESULT: ' + ('PASS' if ok else 'FAIL'))\n"
    )
    oracle = _write_oracle(tmp_path, "env_check.py", body)
    outcome = run_oracle(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == OracleStatus.PASS


def test_run_oracle_undecodable_output_is_unknown(tmp_path: Path) -> None:
    body = (
        "#!/usr/bin/env python3\nimport sys\n"
        "sys.stdout.buffer.write(b'\\xff\\xfe\\nNO1_010B_ORACLE_REASON: "
        "dispatch-returns-none\\nNO1_010B_ORACLE_RESULT: PASS\\n')\n"
    )
    oracle = _write_oracle(tmp_path, "binary.py", body)
    outcome = run_oracle(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == OracleStatus.UNKNOWN


def test_run_oracle_resolves_relative_path_against_cwd(tmp_path: Path) -> None:
    _write_oracle(tmp_path, "relative.py", ORACLE_PASS)
    outcome = run_oracle(
        "relative.py", str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == OracleStatus.PASS


@pytest.mark.parametrize(
    "body",
    [
        "#!/usr/bin/env python3\nprint('NO1_010B_ORACLE_RESULT: FAIL')\n",
        (
            "#!/usr/bin/env python3\n"
            "print('NO1_010B_ORACLE_REASON: stale-reason')\n"
            "print('NO1_010B_ORACLE_RESULT: FAIL')\n"
        ),
        "#!/usr/bin/env python3\nprint('NO1_010B_ORACLE_RESULT: PASS')\n",
        (
            "#!/usr/bin/env python3\n"
            "print('NO1_010B_ORACLE_REASON: stale-reason')\n"
            "print('NO1_010B_ORACLE_RESULT: PASS')\n"
        ),
    ],
)
def test_run_oracle_rejects_invalid_reason_protocol(tmp_path: Path, body: str) -> None:
    oracle = _write_oracle(tmp_path, "reason.py", body)
    outcome = run_oracle(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == OracleStatus.UNKNOWN


def test_run_oracle_bounds_output_while_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tree_sitter_analyzer.no1_010b.oracle as oracle_module

    monkeypatch.setattr(oracle_module, "ORACLE_OUTPUT_MAX_BYTES", 1024)
    body = (
        "#!/usr/bin/env python3\nimport sys\n"
        "sys.stdout.buffer.write(b'x' * 2048)\n"
        "print('NO1_010B_ORACLE_REASON: dispatch-returns-none')\n"
        "print('NO1_010B_ORACLE_RESULT: PASS')\n"
    )
    oracle = _write_oracle(tmp_path, "flood.py", body)
    outcome = run_oracle(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.stdout_tail == "oracle output exceeded limit"


@pytest.mark.parametrize(("returncode", "kill_count"), [(0, 0), (1, 1)])
def test_kill_process_tree_uses_windows_taskkill(
    monkeypatch: pytest.MonkeyPatch, returncode: int, kill_count: int
) -> None:
    import tree_sitter_analyzer.no1_010b.oracle as oracle_module

    proc = Mock(pid=321)
    taskkill = Mock(return_value=CompletedProcess([], returncode))
    monkeypatch.setattr(oracle_module, "_IS_WINDOWS", True)
    monkeypatch.setattr(oracle_module, "_TASKKILL", taskkill)

    _kill_process_tree(proc)

    assert taskkill.call_args.args[0] == ["taskkill", "/PID", "321", "/T", "/F"]
    assert proc.kill.call_count == kill_count


def test_kill_process_tree_falls_back_without_killpg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tree_sitter_analyzer.no1_010b.oracle as oracle_module

    proc = Mock(pid=321)
    monkeypatch.setattr(oracle_module, "_IS_WINDOWS", False)
    monkeypatch.setattr(oracle_module.os, "killpg", None, raising=False)

    _kill_process_tree(proc)

    proc.kill.assert_called_once_with()


def test_kill_process_tree_suppresses_cleanup_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tree_sitter_analyzer.no1_010b.oracle as oracle_module

    proc = Mock(pid=321)
    proc.kill.side_effect = OSError("kill failed")
    monkeypatch.setattr(oracle_module, "_IS_WINDOWS", False)
    monkeypatch.setattr(
        oracle_module.os,
        "killpg",
        Mock(side_effect=OSError("killpg failed")),
        raising=False,
    )

    _kill_process_tree(proc)

    proc.kill.assert_called_once_with()


def test_reap_process_retries_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tree_sitter_analyzer.no1_010b.oracle as oracle_module

    proc = Mock()
    proc.wait.side_effect = [TimeoutExpired("oracle", 1), OSError("still running")]
    kill_tree = Mock()
    monkeypatch.setattr(oracle_module, "_kill_process_tree", kill_tree)

    _reap_process(proc)

    assert proc.wait.call_count == 2
    kill_tree.assert_called_once_with(proc)
