"""Contract tests for the NO1-010B oracle wrapper (RFC-0026 §3, C19)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b.oracle import (
    OracleStatus,
    _parse_result_line,
    run_oracle,
)

ORACLE_PASS = "#!/usr/bin/env python3\nprint('NO1_010B_ORACLE_RESULT: PASS')\n"
ORACLE_FAIL = "#!/usr/bin/env python3\nprint('NO1_010B_ORACLE_RESULT: FAIL')\n"
ORACLE_CRASH = "#!/usr/bin/env python3\nraise ImportError('missing dep')\n"
ORACLE_SYNTAX = "#!/usr/bin/env python3\ndef broken(:\n"
ORACLE_MALFORMED = "#!/usr/bin/env python3\nprint('NO1_010B_ORACLE_RESULT: MAYBE')\n"
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
    outcome = run_oracle(str(oracle), str(tmp_path))
    assert outcome.status == expected


def test_run_oracle_timeout_is_unknown(tmp_path: Path) -> None:
    oracle = _write_oracle(tmp_path, "hang.py", ORACLE_HANG)
    outcome = run_oracle(str(oracle), str(tmp_path), timeout_s=1.0)
    assert outcome.status == OracleStatus.UNKNOWN
    assert "timed out" in outcome.stdout_tail


def test_run_oracle_missing_file_is_unknown(tmp_path: Path) -> None:
    outcome = run_oracle(str(tmp_path / "ghost.py"), str(tmp_path))
    assert outcome.status == OracleStatus.UNKNOWN


def test_run_oracle_os_error_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    def boom(*args, **kwargs):
        raise OSError("no such executable")

    monkeypatch.setattr(subprocess, "Popen", boom)
    oracle = _write_oracle(tmp_path, "oracle.py", ORACLE_PASS)
    outcome = run_oracle(str(oracle), str(tmp_path))
    assert outcome.status == OracleStatus.UNKNOWN
    assert "could not execute" in outcome.stdout_tail
    monkeypatch.undo()


def test_oracle_command_line_quotes_path() -> None:
    from tree_sitter_analyzer.no1_010b.oracle import oracle_command_line

    assert oracle_command_line("oracles/0001.py") == "oracles/0001.py"
    assert oracle_command_line("my oracle.py") == "'my oracle.py'"


def test_parse_result_line_uses_final_declared_line() -> None:
    assert (
        _parse_result_line("noise\nNO1_010B_ORACLE_RESULT: FAIL\n") is OracleStatus.FAIL
    )
    assert _parse_result_line("NO1_010B_ORACLE_RESULT: pass\n") is OracleStatus.PASS
    assert _parse_result_line("no marker here\n") is OracleStatus.UNKNOWN
    assert _parse_result_line("") is OracleStatus.UNKNOWN
    # Blank lines after the marker do not change that it is the final output.
    assert _parse_result_line("NO1_010B_ORACLE_RESULT: PASS\n\n\n") is OracleStatus.PASS


def test_parse_result_line_rejects_trailing_diagnostics() -> None:
    # A PASS marker followed by a later diagnostic is NOT final -> UNKNOWN,
    # never a stale PASS (Codex #1307 P2).
    assert (
        _parse_result_line("NO1_010B_ORACLE_RESULT: PASS\ncleanup warning\n")
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
        "print('NO1_010B_ORACLE_RESULT: ' + ('PASS' if ok else 'FAIL'))\n"
    )
    oracle = _write_oracle(tmp_path, "env_check.py", body)
    outcome = run_oracle(str(oracle), str(tmp_path))
    assert outcome.status == OracleStatus.PASS


def test_run_oracle_undecodable_output_is_unknown(tmp_path: Path) -> None:
    body = (
        "#!/usr/bin/env python3\nimport sys\nsys.stdout.buffer.write(b'\\xff\\xfe')\n"
    )
    oracle = _write_oracle(tmp_path, "binary.py", body)
    outcome = run_oracle(str(oracle), str(tmp_path))
    assert outcome.status == OracleStatus.UNKNOWN
