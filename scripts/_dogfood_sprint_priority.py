"""Priority-matrix and summary shaping for the dogfood sprint."""

from __future__ import annotations

from typing import Any

WorkItem = dict[str, Any]
ClaimResult = dict[str, Any]


def build_priority_matrix(
    health: dict[str, Any],
    dead_code: dict[str, Any],
    constraints: dict[str, Any],
    claim_results: list[ClaimResult],
) -> list[WorkItem]:
    """Build the stable P0-to-P3 work queue in priority order."""
    return [
        *_claim_items(claim_results),
        *_constraint_items(constraints),
        *_health_items(health),
        *_dead_code_items(dead_code),
    ]


def _claim_items(claim_results: list[ClaimResult]) -> list[WorkItem]:
    items = [
        {
            "priority": "P0",
            "category": "claim_failure",
            "title": f"Claim invariant failed: {_claim_name(claim)}",
            "details": str(claim["message"])[:300],
            "verification_command": "uv run pytest tests/benchmarks/claims/ -v",
        }
        for claim in claim_results
        if claim["status"] == "failed"
    ]
    items.extend(
        {
            "priority": "P0",
            "category": "xpass_needs_un_xfail",
            "title": f"xpass — remove strict xfail: {_claim_name(claim)}",
            "details": (
                "A previously-failing claim now passes. Remove the xfail decorator."
            ),
            "verification_command": f"uv run pytest {claim['test']} -v",
        }
        for claim in claim_results
        if claim["status"] == "xpass"
    )
    return items


def _claim_name(claim: ClaimResult) -> str:
    return str(claim["test"]).split("::")[-1]


def _constraint_items(constraints: dict[str, Any]) -> list[WorkItem]:
    violations = constraints.get("data", {}).get("violations") or []
    return [
        {
            "priority": "P1",
            "category": "constraint_violation",
            "title": f"Architecture violation: {violation.get('rule_name', '?')}",
            "details": str(violation)[:300],
            "verification_command": (
                "uv run python -m tree_sitter_analyzer --check-constraints"
            ),
        }
        for violation in violations[:5]
    ]


def _health_items(health: dict[str, Any]) -> list[WorkItem]:
    health_data = health.get("data", {})
    graded_files = health_data.get("files") or health_data.get("file_grades") or []
    unhealthy = [
        file_data
        for file_data in graded_files
        if isinstance(file_data, dict) and file_data.get("grade") in ("D", "F")
    ]
    return [_health_item(file_data) for file_data in unhealthy[:5]]


def _health_item(file_data: dict[str, Any]) -> WorkItem:
    file_path = file_data.get("file_path", "?")
    return {
        "priority": "P2",
        "category": "health_grade_df",
        "title": f"File graded {file_data.get('grade')}: {file_path}",
        "details": (
            f"Score: {file_data.get('score', '?')}, "
            f"weakest: {file_data.get('weakest_dimension', '?')}"
        ),
        "verification_command": (
            f"uv run python -m tree_sitter_analyzer --file-health {file_path}"
        ),
    }


def _dead_code_items(dead_code: dict[str, Any]) -> list[WorkItem]:
    dead_functions = dead_code.get("data", {}).get("dead_functions") or []
    if not dead_functions:
        return []
    names = ", ".join(function.get("name", "?") for function in dead_functions[:10])
    return [
        {
            "priority": "P3",
            "category": "dead_code",
            "title": f"{len(dead_functions)} potentially dead function(s) detected",
            "details": names,
            "verification_command": (
                "uv run python -m tree_sitter_analyzer --dead-code --output-format json"
            ),
        }
    ]


def project_health_grade(health_data: dict[str, Any]) -> str:
    """Collapse project-health output into the worst populated A-F bucket."""
    grade_distribution = health_data.get("grade_distribution")
    if not isinstance(grade_distribution, dict):
        agent_summary = health_data.get("agent_summary", {})
        if isinstance(agent_summary, dict):
            grade_distribution = agent_summary.get("grade_distribution")
    if not isinstance(grade_distribution, dict):
        return "?"
    for grade in ("F", "D", "C", "B", "A"):
        count = grade_distribution.get(grade, 0)
        if isinstance(count, (int, float)) and count > 0:
            return grade
    return "?"


def count_tool_failures(
    sequence: list[dict[str, Any]],
    claim_results: list[ClaimResult],
) -> int:
    """Count TSA and claim-suite invocation failures."""
    sequence_failures = sum(1 for step in sequence if step.get("status") == "error")
    claim_failures = sum(1 for claim in claim_results if claim.get("status") == "error")
    return sequence_failures + claim_failures


def highest_priority(items: list[WorkItem]) -> str:
    """Return the first populated priority bucket."""
    for level in ("P0", "P1", "P2", "P3"):
        if any(item["priority"] == level for item in items):
            return level
    return "None"
