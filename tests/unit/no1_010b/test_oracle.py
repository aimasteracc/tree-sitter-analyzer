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


def test_parse_result_line_uses_final_declared_line() -> None:
    assert (
        _parse_result_line("noise\nNO1_010B_ORACLE_RESULT: FAIL\n") is OracleStatus.FAIL
    )
    assert _parse_result_line("NO1_010B_ORACLE_RESULT: pass\n") is OracleStatus.PASS
    assert _parse_result_line("no marker here\n") is OracleStatus.UNKNOWN
    assert _parse_result_line("") is OracleStatus.UNKNOWN
