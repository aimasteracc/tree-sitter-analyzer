from __future__ import annotations

from scripts.dogfood_sprint import (
    _build_priority_matrix,
    _count_tool_failures,
    _project_health_grade,
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
