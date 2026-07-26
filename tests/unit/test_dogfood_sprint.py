from __future__ import annotations

import json
import subprocess
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


def test_main_preserves_sequence_schema_and_clean_exit(monkeypatch, capsys) -> None:
    """The split orchestrator must retain stage order, schema, and exit code."""
    # Issue #1188 (2026-07-27): main moved from one 135-line implementation.
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
    monkeypatch.setattr(
        dogfood_sprint.sys,
        "argv",
        ["dogfood_sprint.py", "--quiet", "--skip-claims"],
    )

    exit_code = dogfood_sprint.main()
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert list(report) == [
        "generated_at_utc",
        "dogfood_sequence",
        "claim_invariant_status",
        "priority_matrix",
        "summary",
    ]
    assert [step["tool"] for step in report["dogfood_sequence"]] == [
        "project_health",
        "dead_code",
        "change_impact",
        "check_constraints",
        "readme_counts",
    ]
    assert report["summary"] == {
        "work_item_count": 0,
        "highest_priority": "None",
        "health_grade": "A",
        "claim_failures": 0,
        "tool_failures": 0,
    }
