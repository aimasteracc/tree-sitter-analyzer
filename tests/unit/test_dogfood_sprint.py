from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from scripts import _dogfood_sprint_runner as runner_module
from scripts import dogfood_sprint
from scripts.dogfood_sprint import (
    _build_priority_matrix,
    _count_tool_failures,
    _parse_claim_junit_report,
    _project_health_grade,
    _run_tsa,
)


def test_build_priority_matrix_keeps_xpass_single_item() -> None:
    claim_results = [{"test": "tests::test_claim", "status": "xpass", "message": ""}]

    items = _build_priority_matrix({}, {}, {}, claim_results)

    assert len(items) == 1
    assert items[0]["priority"] == "P0"
    assert items[0]["category"] == "xpass_needs_un_xfail"


def test_project_health_grade_uses_worst_distribution_bucket() -> None:
    health_data = {"grade_distribution": {"A": 3, "B": 2, "C": 1, "D": 4, "F": 0}}

    assert _project_health_grade(health_data) == "D"


def test_tool_failure_count_includes_claim_suite_errors() -> None:
    sequence = [{"tool": "project_health", "status": "error"}]
    claim_results = [{"test": "claims_suite", "status": "error", "message": ""}]

    assert _count_tool_failures(sequence, claim_results) == 2


def test_run_tsa_preserves_facade_process_injection(monkeypatch) -> None:
    """The compatibility facade must still expose its subprocess seam."""
    # Issue #1188 (2026-07-27): runner extraction must preserve test injection.
    clocks = iter((10.0, 10.25))
    monkeypatch.setattr(dogfood_sprint.time, "perf_counter", lambda: next(clocks))
    monkeypatch.setattr(
        dogfood_sprint.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"success": true}',
            stderr="",
        ),
    )

    assert _run_tsa(["--project-health"]) == {
        "status": "ok",
        "elapsed_s": 0.25,
        "data": {"success": True},
    }


def test_parse_claim_junit_report_preserves_all_statuses(tmp_path) -> None:
    """JUnit extraction must retain passed, failed, xfail, and error states."""
    # Issue #1188 (2026-07-27): parsing moved out of the stable script facade.
    report = tmp_path / "claims.xml"
    report.write_text(
        """<testsuite>
        <testcase classname="claims" name="passed" />
        <testcase classname="claims" name="failed"><failure message="boom" /></testcase>
        <testcase classname="claims" name="xfail"><skipped type="pytest.xfail" message="known" /></testcase>
        <testcase classname="claims" name="error"><error message="broken" /></testcase>
        </testsuite>""",
        encoding="utf-8",
    )

    results = _parse_claim_junit_report(report)

    assert [(item["test"], item["status"]) for item in results] == [
        ("claims::passed", "passed"),
        ("claims::failed", "failed"),
        ("claims::xfail", "xfail"),
        ("claims::error", "error"),
    ]


def test_parse_claim_junit_report_rejects_oversized_input(
    tmp_path, monkeypatch
) -> None:
    """The local XML parser must enforce its report-size safety bound."""
    # Issue #1188 (2026-07-27): splitting exposed the parser to security scans.
    report = tmp_path / "claims.xml"
    report.write_text("<testsuite />", encoding="utf-8")
    monkeypatch.setattr(runner_module, "_MAX_CLAIM_REPORT_BYTES", 1)

    with pytest.raises(ET.ParseError, match="8 MiB safety bound"):
        _parse_claim_junit_report(report)


def test_run_claim_tests_normalizes_disappearing_junit_report(tmp_path) -> None:
    """A report read race must remain a claim-suite error, not a traceback."""
    # Issue #1188 (2026-07-27): extraction narrowed the report error handler.
    report = tmp_path / "dogfood-claims-report.xml"

    def create_report(*_args, **_kwargs):
        report.write_text("<testsuite />", encoding="utf-8")
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    def raise_read_error(_path):
        raise OSError("report disappeared")

    results = runner_module.run_claim_tests(
        root=tmp_path,
        pytest_bin=["pytest"],
        process_runner=create_report,
        report_parser=raise_read_error,
    )

    assert results == [
        {
            "test": "claims_suite",
            "status": "error",
            "message": "unreadable junit xml: report disappeared",
        }
    ]


def _run_clean_main(monkeypatch, capsys, *extra_args, quiet=True):
    monkeypatch.setattr(
        dogfood_sprint,
        "_run_tsa",
        lambda _args, **_kwargs: {
            "status": "ok",
            "elapsed_s": 0,
            "data": {"grade_distribution": {"A": 1}},
        },
    )
    monkeypatch.setattr(
        dogfood_sprint,
        "_run_readme_counts",
        lambda: {"status": "ok", "elapsed_s": 0, "data": {"output": "passed"}},
    )
    arguments = ["dogfood_sprint.py", "--skip-claims", *extra_args]
    if quiet:
        arguments.append("--quiet")
    monkeypatch.setattr(dogfood_sprint.sys, "argv", arguments)

    exit_code = dogfood_sprint.main()
    captured = capsys.readouterr()
    return exit_code, json.loads(captured.out or "{}"), captured.err


def test_main_preserves_clean_exit_code(monkeypatch, capsys) -> None:
    """The split orchestrator must retain the clean-run exit code."""
    # Issue #1188 (2026-07-27): main moved from one 135-line implementation.
    exit_code, _report, _stderr = _run_clean_main(monkeypatch, capsys)

    assert exit_code == 0


def test_main_preserves_top_level_report_field_order(monkeypatch, capsys) -> None:
    """The split orchestrator must retain top-level JSON field order."""
    # Issue #1188 (2026-07-27): main moved from one 135-line implementation.
    _exit_code, report, _stderr = _run_clean_main(monkeypatch, capsys)

    assert list(report) == [
        "generated_at_utc",
        "dogfood_sequence",
        "claim_invariant_status",
        "priority_matrix",
        "summary",
    ]


def test_main_preserves_stage_order(monkeypatch, capsys) -> None:
    """The split orchestrator must retain its five persisted tool stages."""
    # Issue #1188 (2026-07-27): main moved from one 135-line implementation.
    _exit_code, report, _stderr = _run_clean_main(monkeypatch, capsys)

    assert [step["tool"] for step in report["dogfood_sequence"]] == [
        "project_health",
        "dead_code",
        "change_impact",
        "check_constraints",
        "readme_counts",
    ]


def test_main_preserves_summary_shape(monkeypatch, capsys) -> None:
    """The split orchestrator must retain the clean-run summary."""
    # Issue #1188 (2026-07-27): main moved from one 135-line implementation.
    _exit_code, report, _stderr = _run_clean_main(monkeypatch, capsys)

    assert report["summary"] == {
        "work_item_count": 0,
        "highest_priority": "None",
        "health_grade": "A",
        "claim_failures": 0,
        "tool_failures": 0,
    }


def test_main_emits_done_after_output_file_is_ready(
    tmp_path, monkeypatch, capsys
) -> None:
    """The completion signal must follow the durable output-file signal."""
    # Issue #1188 (2026-07-27): orchestration logged Done before main wrote output.
    output = tmp_path / "report.json"

    _exit_code, _report, stderr = _run_clean_main(
        monkeypatch,
        capsys,
        "--out",
        str(output),
        quiet=False,
    )
    messages = stderr.splitlines()

    assert messages[-2:] == [
        f"[dogfood] Report written to {output}",
        "[dogfood] Done. Work items: 0, highest priority: None",
    ]


def test_direct_cli_ignores_unrelated_installed_scripts_package(tmp_path) -> None:
    """Direct execution must resolve helpers beside the checked-out script."""
    # Issue #1188 (2026-07-27): absolute namespace imports could select another package.
    shadow_root = tmp_path / "shadow"
    shadow_package = shadow_root / "scripts"
    shadow_package.mkdir(parents=True)
    (shadow_package / "__init__.py").write_text("", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(shadow_root)

    process = subprocess.run(
        [sys.executable, str(Path(dogfood_sprint.__file__).resolve()), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert (process.returncode, process.stderr) == (0, "")


def test_cli_description_preserves_pipeline_and_report_contract() -> None:
    """The public help description must retain its established contract."""
    # Issue #1188 (2026-07-27): facade extraction replaced the detailed help text.
    expected_lines = [
        "Opus 4.8 reads this output → writes task briefs → spawns Sonnet dev agents",
        "Sonnet dev agents → open feature PRs → GPT-5.5 reviews them",
        "0  Dogfood complete, no actionable items found.",
        "1  Dogfood complete, actionable items found.",
        "2  Tool invocation failed (unexpected — check logs).",
        "Output JSON schema",
        '"generated_at_utc": "<ISO timestamp>",',
        '"priority_matrix": [',
        '"tool_failures": N',
    ]
    description_lines = [
        line.strip()
        for line in (dogfood_sprint.__doc__ or "").splitlines()
        if line.strip() in expected_lines
    ]

    assert description_lines == expected_lines
