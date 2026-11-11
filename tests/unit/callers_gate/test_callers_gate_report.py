"""Exit status, report rendering and shard splitting of the callers gate."""

from __future__ import annotations

from typing import Any

from benchmarks.callers_gate import report
from benchmarks.callers_gate.query import split


def _repo(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "repo": "gson",
        "n": 2,
        "identical_rows": 2,
        "transitions": {"complete->complete": 2},
        "change_counts": dict.fromkeys(
            (
                "verdict",
                "reasons",
                "caller_count",
                "callers",
                "sites",
                "compact",
                "error",
                "other",
            ),
            0,
        ),
        "reason_changes_same_verdict": [],
        "violations": [],
        "truth_failures": [],
        "truth_preexisting": [],
        "new_complete": 0,
        "grep": [],
        "residual": [],
        "baseline": "cache",
        "index_built": False,
        "timings": {"base": 0.0, "head": 1.0},
    }
    base.update(over)
    return base


HIT = {
    "repo": "gson",
    "target": "A.f",
    "target_file": "A.java",
    "mode": "bare",
    "file": "B.java",
    "line": 3,
    "class": "residual",
    "why": "bare name use",
    "text": "f();",
}


def test_exit_codes_rank_error_over_failure_over_review() -> None:
    assert report.exit_code([_repo()]) == report.EXIT_PASS
    assert report.exit_code([_repo(residual=[HIT])]) == report.EXIT_REVIEW
    assert (
        report.exit_code([_repo(residual=[HIT], violations=[{"qual": "A.f"}])])
        == report.EXIT_FAIL
    )
    assert (
        report.exit_code([_repo(truth_failures=[{"kind": "gt2_miss"}])])
        == report.EXIT_FAIL
    )
    assert (
        report.exit_code([_repo(), {"repo": "zod", "error": "server exited"}])
        == report.EXIT_ERROR
    )


def test_report_puts_residuals_first_and_dedupes_bare_and_qualified() -> None:
    twin = {**HIT, "mode": "qualified"}
    text = report.render(
        {"seconds": {}}, [_repo(residual=[HIT, twin])], report.EXIT_REVIEW
    )
    lines = text.splitlines()
    assert (
        lines[0] == "# Callers gate: REVIEW (no failure; residual items need a human)"
    )
    assert lines[2] == "## Residual items for human review (1)"
    assert (
        text.index("Residual items")
        < text.index("## Failures")
        < text.index("## Transitions")
    )
    assert "| gson | `A.f` | B.java:3 | bare name use | `f();` |" in text


def test_report_lists_errors_as_failures() -> None:
    text = report.render(
        {}, [{"repo": "zod", "error": "boom", "timings": {}}], report.EXIT_ERROR
    )
    assert "# Callers gate: ERROR (gate could not run; not a pass)" in text
    assert "- **zod** error: boom" in text


def _targets(n: int) -> list[dict[str, Any]]:
    return [{"mode": "bare", "file": "f", "qual": f"q{i}"} for i in range(n)]


def test_split_without_costs_is_contiguous_and_complete() -> None:
    parts = split(_targets(7), 3)
    assert [[t["qual"] for t in p] for p in parts] == [
        ["q0", "q1", "q2"],
        ["q3", "q4", "q5"],
        ["q6"],
    ]
    assert split(_targets(2), 5) == [[t] for t in _targets(2)]
    assert split(_targets(3), 1) == [_targets(3)]


def test_split_with_costs_balances_and_keeps_corpus_order() -> None:
    targets = _targets(6)
    costs = {
        ("bare", "f", t["qual"]): c
        for t, c in zip(targets, [10.0, 1.0, 1.0, 1.0, 1.0, 9.0], strict=True)
    }
    parts = split(targets, 2, costs)
    assert [[t["qual"] for t in p] for p in parts] == [
        ["q0", "q2", "q4"],
        ["q1", "q3", "q5"],
    ]
    assert sorted(t["qual"] for p in parts for t in p) == [t["qual"] for t in targets]
