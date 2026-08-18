from __future__ import annotations

import io
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import Mock

import pytest

from tree_sitter_analyzer.no1_010b.oracle import (
    OracleOutcome,
    OracleStatus,
    _drain_bounded,
    _kill_process_tree,
    _parse_result_line,
    _reap_process,
    _run_oracle_process_unisolated_for_tests,
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
ORACLE_IMPORT_ERROR = "#!/usr/bin/env python3\nraise ImportError('missing dep')\n"
ORACLE_RUNTIME_ERROR = "#!/usr/bin/env python3\nraise RuntimeError('broken')\n"
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


def _run_written_oracle(tmp_path: Path, body: str) -> OracleOutcome:
    oracle = _write_oracle(tmp_path, "oracle.py", body)
    return _run_oracle_process_unisolated_for_tests(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )


def test_unisolated_oracle_cannot_forge_completion_from_argv(tmp_path: Path) -> None:
    # PR #1307: candidate code sees no trusted capability in sys.orig_argv,
    # and a forged PASS followed by os._exit(0) never becomes a verdict.
    body = (
        "import os, sys\n"
        "assert 'NO1_010B_TRUSTED_WRAPPER:' not in ' '.join(sys.orig_argv)\n"
        + ORACLE_PASS
        + "os._exit(0)\n"
    )
    outcome = _run_written_oracle(tmp_path, body)
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "SANDBOX_FAILURE"


def test_unisolated_oracle_rejects_declared_fail(tmp_path: Path) -> None:
    outcome = _run_written_oracle(tmp_path, ORACLE_FAIL)
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "SANDBOX_FAILURE"


@pytest.mark.parametrize("body", [ORACLE_IMPORT_ERROR, ORACLE_SYNTAX])
def test_unisolated_oracle_classifies_load_failure_as_execution_error(
    tmp_path: Path, body: str
) -> None:
    outcome = _run_written_oracle(tmp_path, body)
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_EXECUTION_ERROR"


@pytest.mark.parametrize("body", [ORACLE_RUNTIME_ERROR, "raise SystemExit(86)\n"])
def test_run_oracle_classifies_runtime_exit_as_execution_error(
    tmp_path: Path, body: str
) -> None:
    outcome = _run_written_oracle(tmp_path, body)
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_EXECUTION_ERROR"


@pytest.mark.parametrize("body", [ORACLE_MALFORMED, ORACLE_NOMARKER])
def test_run_oracle_classifies_invalid_result_as_protocol_error(
    tmp_path: Path, body: str
) -> None:
    outcome = _run_written_oracle(tmp_path, body)
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_PROTOCOL_ERROR"


def test_dependency_initialization_is_execution_error(tmp_path: Path) -> None:
    _write_oracle(tmp_path, "broken_dep.py", "raise TypeError('broken init')\n")
    outcome = _run_written_oracle(tmp_path, "import broken_dep\n")
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_EXECUTION_ERROR"


def test_run_oracle_timeout_is_unknown(tmp_path: Path) -> None:
    oracle = _write_oracle(tmp_path, "hang.py", ORACLE_HANG)
    outcome = _run_oracle_process_unisolated_for_tests(
        str(oracle),
        str(tmp_path),
        expected_reason="dispatch-returns-none",
        timeout_s=1.0,
    )
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_TIMEOUT"
    assert "timed out" in outcome.stdout_tail


def test_run_oracle_missing_file_is_unknown(tmp_path: Path) -> None:
    outcome = _run_oracle_process_unisolated_for_tests(
        str(tmp_path / "ghost.py"),
        str(tmp_path),
        expected_reason="dispatch-returns-none",
    )
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_LOAD_ERROR"


def test_run_oracle_os_error_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    def boom(*args, **kwargs):
        raise OSError("no such executable")

    monkeypatch.setattr(subprocess, "Popen", boom)
    oracle = _write_oracle(tmp_path, "oracle.py", ORACLE_PASS)
    outcome = _run_oracle_process_unisolated_for_tests(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_EXECUTION_ERROR"
    assert "could not execute" in outcome.stdout_tail
    monkeypatch.undo()


def test_oracle_command_line_quotes_path() -> None:
    from tree_sitter_analyzer.no1_010b.oracle import oracle_command_line

    assert oracle_command_line("oracles/0001.py") == "oracles/0001.py"
    assert oracle_command_line("my oracle.py") == "'my oracle.py'"


def test_parse_result_line_reads_declared_fail() -> None:
    assert (
        _parse_result_line(
            "NO1_010B_ORACLE_REASON: dispatch-returns-none\n"
            "NO1_010B_ORACLE_RESULT: FAIL\n",
            "dispatch-returns-none",
        )
        is OracleStatus.FAIL
    )


def test_parse_result_line_reads_declared_pass() -> None:
    assert (
        _parse_result_line(
            "NO1_010B_ORACLE_REASON: dispatch-returns-none\n"
            "NO1_010B_ORACLE_RESULT: PASS\n",
            "dispatch-returns-none",
        )
        is OracleStatus.PASS
    )


@pytest.mark.parametrize("output", ["no marker here\n", ""])
def test_parse_result_line_rejects_missing_marker(output: str) -> None:
    assert _parse_result_line(output, "reason") is OracleStatus.UNKNOWN


def test_parse_result_line_allows_trailing_blank_lines() -> None:
    # Blank lines after the marker do not change that it is the final output.
    assert (
        _parse_result_line(
            "NO1_010B_ORACLE_REASON: reason\nNO1_010B_ORACLE_RESULT: PASS\n\n\n",
            "reason",
        )
        is OracleStatus.PASS
    )


@pytest.mark.parametrize("token", ["pass", "Pass", "fail", "Fail", "PASS "])
def test_parse_result_line_rejects_noncanonical_token_case(token: str) -> None:
    stdout = f"NO1_010B_ORACLE_REASON: reason\nNO1_010B_ORACLE_RESULT: {token}\n"
    assert _parse_result_line(stdout, "reason") is OracleStatus.UNKNOWN


def test_parse_result_line_rejects_reason_trailing_space() -> None:
    # PR #1307 review: the declared reason is an exact protocol token.
    stdout = "NO1_010B_ORACLE_REASON: reason \nNO1_010B_ORACLE_RESULT: PASS\n"
    assert _parse_result_line(stdout, "reason") is OracleStatus.UNKNOWN


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
    outcome = _run_oracle_process_unisolated_for_tests(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.unknown_reason == "SANDBOX_FAILURE"
    assert (
        _parse_result_line(outcome.stdout_tail, "dispatch-returns-none")
        is OracleStatus.PASS
    )


def test_run_oracle_undecodable_output_is_unknown(tmp_path: Path) -> None:
    body = (
        "#!/usr/bin/env python3\nimport sys\n"
        "sys.stdout.buffer.write(b'\\xff\\xfe\\nNO1_010B_ORACLE_REASON: "
        "dispatch-returns-none\\nNO1_010B_ORACLE_RESULT: PASS\\n')\n"
    )
    oracle = _write_oracle(tmp_path, "binary.py", body)
    outcome = _run_oracle_process_unisolated_for_tests(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_PROTOCOL_ERROR"


def test_run_oracle_resolves_relative_path_against_cwd(tmp_path: Path) -> None:
    _write_oracle(tmp_path, "relative.py", ORACLE_PASS)
    outcome = _run_oracle_process_unisolated_for_tests(
        "relative.py", str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.unknown_reason == "SANDBOX_FAILURE"


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
    outcome = _run_oracle_process_unisolated_for_tests(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_PROTOCOL_ERROR"


def test_run_oracle_rejects_stderr_after_result_marker(tmp_path: Path) -> None:
    # PR #1307: the declared marker is final across both output streams.
    body = (
        "#!/usr/bin/env python3\nimport sys\n"
        "print('NO1_010B_ORACLE_REASON: dispatch-returns-none')\n"
        "print('NO1_010B_ORACLE_RESULT: PASS')\n"
        "print('later diagnostic', file=sys.stderr, flush=True)\n"
    )
    oracle = _write_oracle(tmp_path, "stderr_after.py", body)
    outcome = _run_oracle_process_unisolated_for_tests(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_PROTOCOL_ERROR"


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
    outcome = _run_oracle_process_unisolated_for_tests(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_PROTOCOL_ERROR"
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


def test_drain_bounded_marks_pipe_read_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    import tree_sitter_analyzer.no1_010b.oracle as oracle_module

    stream = Mock()
    stream.read.side_effect = OSError("pipe failed")
    proc = Mock()
    failed = threading.Event()
    kill_tree = Mock()
    monkeypatch.setattr(oracle_module, "_kill_process_tree", kill_tree)

    _drain_bounded(stream, bytearray(), threading.Event(), failed, proc)

    assert failed.is_set()
    kill_tree.assert_called_once_with(proc)


def test_run_oracle_rejects_missing_output_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tree_sitter_analyzer.no1_010b.oracle as oracle_module

    proc = Mock(pid=321, stdout=None, stderr=io.BytesIO())
    proc.returncode = 0
    popen = Mock(return_value=proc)
    monkeypatch.setattr(oracle_module.subprocess, "Popen", popen)
    monkeypatch.setattr(oracle_module, "_kill_process_tree", Mock())
    monkeypatch.setattr(oracle_module, "_reap_process", Mock())
    oracle = _write_oracle(tmp_path, "oracle.py", ORACLE_PASS)

    outcome = _run_oracle_process_unisolated_for_tests(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )

    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_PROTOCOL_ERROR"
    assert outcome.stdout_tail == "oracle output could not be read"


def test_run_oracle_rejects_unclosed_output_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tree_sitter_analyzer.no1_010b.oracle as oracle_module

    class HungThread:
        def __init__(self, **kwargs) -> None:
            pass

        def start(self) -> None:
            pass

        def join(self, timeout: float) -> None:
            pass

        def is_alive(self) -> bool:
            return True

    proc = Mock(pid=321, stdout=io.BytesIO(), stderr=io.BytesIO())
    proc.returncode = 0
    monkeypatch.setattr(oracle_module.subprocess, "Popen", Mock(return_value=proc))
    monkeypatch.setattr(oracle_module.threading, "Thread", HungThread)
    monkeypatch.setattr(oracle_module, "_kill_process_tree", Mock())
    monkeypatch.setattr(oracle_module, "_reap_process", Mock())
    oracle = _write_oracle(tmp_path, "oracle.py", ORACLE_PASS)

    outcome = _run_oracle_process_unisolated_for_tests(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )

    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_PROTOCOL_ERROR"
    assert outcome.stdout_tail == "oracle output did not close"


def test_run_oracle_uses_windows_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tree_sitter_analyzer.no1_010b.oracle as oracle_module

    output = (
        b"NO1_010B_ORACLE_REASON: dispatch-returns-none\nNO1_010B_ORACLE_RESULT: PASS\n"
    )
    proc = Mock(pid=321, stdout=io.BytesIO(output), stderr=io.BytesIO())
    proc.returncode = 0
    popen = Mock(return_value=proc)
    monkeypatch.setattr(oracle_module, "_IS_WINDOWS", True)
    monkeypatch.setattr(oracle_module.subprocess, "Popen", popen)
    oracle = _write_oracle(tmp_path, "oracle.py", ORACLE_PASS)

    outcome = _run_oracle_process_unisolated_for_tests(
        str(oracle), str(tmp_path), expected_reason="dispatch-returns-none"
    )

    assert outcome.unknown_reason == "SANDBOX_FAILURE"
    assert "creationflags" in popen.call_args.kwargs
    assert "start_new_session" not in popen.call_args.kwargs
