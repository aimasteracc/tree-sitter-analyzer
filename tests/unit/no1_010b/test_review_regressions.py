"""Focused regressions from the exact-head Codex review of PR #1307."""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b.oracle import (
    OracleOutcome,
    OracleStatus,
    _extract_wrapper_status,
    _run_oracle_process_unisolated_for_tests,
)
from tree_sitter_analyzer.no1_010b.record import BenchmarkRecordError, record_from_dict
from tree_sitter_analyzer.no1_010b.runner import (
    PatchFormatError,
    Verdict,
    diff_paths,
    preflight_agent_patch,
)

PATCH = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"


def _payload(patch: str) -> dict:
    return {
        "id": "no1-010b/review-regression",
        "task_class": "bugfix",
        "repo": "fixtures/app",
        "repo_commit": "0" * 40,
        "operation": "plan_change",
        "task": "repair the behavior",
        "allowed_paths": ["x.py"],
        "oracle": "oracles/review.py",
        "oracle_baseline_reason": "review-regression",
        "verification_argv": ["pytest", "-q"],
        "expected_terminal": {"verdict": "PASS", "reason_code": None},
        "patch": patch,
    }


def _run_oracle(tmp_path: Path, body: str) -> OracleOutcome:
    oracle = tmp_path / "oracle.py"
    oracle.write_text(body, encoding="utf-8")
    return _run_oracle_process_unisolated_for_tests(
        str(oracle), str(tmp_path), expected_reason="review-regression"
    )


def test_diff_paths_rejects_quoted_git_header() -> None:
    with pytest.raises(PatchFormatError, match="non-canonical"):
        diff_paths('diff --git "a/path with spaces" "b/path with spaces"\n')


def test_diff_paths_rejects_wrong_side_git_header() -> None:
    with pytest.raises(PatchFormatError, match="non-canonical"):
        diff_paths("diff --git b/wrong.py b/wrong.py\n")


def test_diff_paths_rejects_traversal_in_extended_header() -> None:
    patch = PATCH + "diff --git a/x.py b/x.py\nrename from ../secret.py\n"
    with pytest.raises(PatchFormatError, match="extended path"):
        diff_paths(patch)


def test_diff_paths_preserves_trailing_space_before_timestamp_tab() -> None:
    patch = "--- a/x \t\n+++ b/x \t\n@@ -1 +1 @@\n-old\n+new\n"
    assert [path.rel_path for path in diff_paths(patch)] == ["x "]


def test_preflight_accepts_crlf_patch() -> None:
    assert preflight_agent_patch(PATCH.replace("\n", "\r\n")) is None


def test_preflight_rejects_invalid_mode_metadata() -> None:
    patch = "diff --git a/x.py b/x.py\nold mode xyz\n" + PATCH
    assert preflight_agent_patch(patch) == Verdict("UNKNOWN", "AGENT_OUTPUT_ERROR")


def test_preflight_rejects_standalone_metadata_garbage() -> None:
    patch = "diff --git a/x.py b/x.py\nGARBAGE\n" + PATCH
    assert preflight_agent_patch(patch) == Verdict("UNKNOWN", "AGENT_OUTPUT_ERROR")


def test_record_rejects_noncanonical_git_header() -> None:
    patch = 'diff --git "a/x.py" "b/x.py"\n' + PATCH
    with pytest.raises(BenchmarkRecordError, match="unified diff"):
        record_from_dict(_payload(patch))


def test_runtime_exit_86_is_execution_error(tmp_path: Path) -> None:
    outcome = _run_oracle(tmp_path, "raise SystemExit(86)\n")
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_EXECUTION_ERROR"


def test_candidate_cannot_pass_by_exiting_after_forged_markers(tmp_path: Path) -> None:
    body = (
        "import os\n"
        "print('NO1_010B_ORACLE_REASON: review-regression', flush=True)\n"
        "print('NO1_010B_ORACLE_RESULT: PASS', flush=True)\n"
        "os._exit(0)\n"
    )
    outcome = _run_oracle(tmp_path, body)
    assert outcome.status == OracleStatus.UNKNOWN
    assert outcome.unknown_reason == "ORACLE_EXECUTION_ERROR"


def test_wrapper_status_rejects_trailing_output() -> None:
    output = "NO1_010B_TRUSTED_WRAPPER:token:COMPLETE\nlater\n"
    assert _extract_wrapper_status(output, "token") == (None, output)


def test_wrapper_status_rejects_unknown_state() -> None:
    output = "NO1_010B_TRUSTED_WRAPPER:token:MAYBE\n"
    assert _extract_wrapper_status(output, "token") == (None, output)


def test_wrapper_status_accepts_empty_oracle_output() -> None:
    output = "NO1_010B_TRUSTED_WRAPPER:token:LOAD_ERROR\n"
    assert _extract_wrapper_status(output, "token") == ("LOAD_ERROR", "")
