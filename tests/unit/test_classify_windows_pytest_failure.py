"""Behavioral tests for the Windows degraded-runner classifier."""

import sys
from pathlib import Path
from unittest.mock import patch

from scripts.classify_windows_pytest_failure import classify, main


def test_budget_only_failures_are_retry_eligible() -> None:
    output = (
        "FAILED tests/unit/test_a.py::test_a - Failed: Unit test exceeded "
        "per-test budget: 8.92s > 8.0s.\n"
        "FAILED tests/unit/test_b.py::test_b - Failed: Unit test exceeded "
        "per-test budget: 9.10s > 8.0s.\n"
    )

    assert classify(output) == {
        "retry_eligible": True,
        "nodeids": ["tests/unit/test_a.py::test_a", "tests/unit/test_b.py::test_b"],
        "failure_count": 2,
        "reason": "budget_only",
    }


def test_assertion_failure_blocks_retry() -> None:
    output = "FAILED tests/unit/test_a.py::test_a - AssertionError: wrong value\n"

    assert classify(output) == {
        "retry_eligible": False,
        "nodeids": [],
        "failure_count": 1,
        "reason": "non_budget_or_unclassified",
    }


def test_mixed_failures_block_retry() -> None:
    output = (
        "FAILED tests/unit/test_a.py::test_a - Failed: Unit test exceeded "
        "per-test budget: 8.92s > 8.0s.\n"
        "FAILED tests/unit/test_b.py::test_b - RuntimeError: boom\n"
    )

    assert classify(output)["retry_eligible"] is False


def test_collection_error_blocks_retry() -> None:
    output = (
        "FAILED tests/unit/test_a.py::test_a - Failed: Unit test exceeded "
        "per-test budget: 8.92s > 8.0s.\n"
        "ERROR tests/unit/test_b.py - ImportError: missing dependency\n"
    )

    assert classify(output)["retry_eligible"] is False


def test_nodeid_file_uses_lf_so_the_ci_retry_can_match(tmp_path: Path) -> None:
    """The nodeid file must be LF-only or the Windows retry path cannot work.

    reusable-test.yml reads this file with ``mapfile -t``, which strips only
    the trailing newline. On Windows, ``Path.write_text`` without
    ``newline=""`` translates each line separator into CRLF, so mapfile
    leaves a carriage return attached to every nodeid, pytest matches
    nothing, and the run exits 5 - turning a recoverable budget blip into a
    red job. The retry path had never been able to succeed on Windows.
    """
    log = tmp_path / "pytest-output.txt"
    log.write_text(
        "FAILED tests/a.py::t1 - Failed: Unit test exceeded per-test "
        "budget: 8.48s > 8.0s." + chr(10),
        encoding="utf-8",
        newline="",
    )
    out = tmp_path / "windows-budget-retry.txt"
    argv = ["classify", str(log), "--nodeids-output", str(out)]

    with patch.object(sys, "argv", argv):
        assert main() == 0

    assert out.read_bytes() == b"tests/a.py::t1" + chr(10).encode()
