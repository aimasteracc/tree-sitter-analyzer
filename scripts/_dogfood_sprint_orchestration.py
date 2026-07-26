"""Six-stage dogfood orchestration with injected runners."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

ToolResult = dict[str, Any]
ClaimResult = dict[str, Any]
WorkItem = dict[str, Any]
ToolRunner = Callable[..., ToolResult]
ClaimRunner = Callable[[], list[ClaimResult]]
ReadmeRunner = Callable[[], ToolResult]
Log = Callable[[str], None]
PriorityBuilder = Callable[
    [ToolResult, ToolResult, ToolResult, list[ClaimResult]],
    list[WorkItem],
]
GradeResolver = Callable[[dict[str, Any]], str]
FailureCounter = Callable[[list[ToolResult], list[ClaimResult]], int]


def run_dogfood(
    *,
    skip_claims: bool,
    log: Log,
    tsa_runner: ToolRunner,
    claim_runner: ClaimRunner,
    readme_runner: ReadmeRunner,
    priority_builder: PriorityBuilder,
    grade_resolver: GradeResolver,
    failure_counter: FailureCounter,
) -> tuple[dict[str, Any], int]:
    """Execute all stages and return the report plus historical exit code."""
    log("Starting full dogfood sequence...")
    sequence = _run_tool_sequence(log, tsa_runner, readme_runner)
    claim_results = _run_claim_stage(skip_claims, log, claim_runner)
    log("Building priority matrix...")
    report = _build_report(
        sequence,
        claim_results,
        priority_builder,
        grade_resolver,
        failure_counter,
    )
    summary = report["summary"]
    log(
        "Done. Work items: "
        f"{summary['work_item_count']}, "
        f"highest priority: {summary['highest_priority']}"
    )
    return report, _exit_code(summary)


def _run_tool_sequence(
    log: Log,
    tsa_runner: ToolRunner,
    readme_runner: ReadmeRunner,
) -> list[ToolResult]:
    sequence: list[ToolResult] = []
    _append_tsa_step(
        sequence,
        log,
        tsa_runner,
        "1/6 project health...",
        "project_health",
        ["--project-health"],
    )
    _append_tsa_step(
        sequence,
        log,
        tsa_runner,
        "2/6 dead code analysis...",
        "dead_code",
        ["--dead-code"],
        timeout=60,
    )
    _append_tsa_step(
        sequence,
        log,
        tsa_runner,
        "3/6 change impact...",
        "change_impact",
        ["--change-impact"],
    )
    _append_tsa_step(
        sequence,
        log,
        tsa_runner,
        "4/6 architectural constraints...",
        "check_constraints",
        ["--check-constraints"],
    )
    log("5/6 README number verification...")
    sequence.append({"tool": "readme_counts", **readme_runner()})
    return sequence


def _append_tsa_step(
    sequence: list[ToolResult],
    log: Log,
    runner: ToolRunner,
    message: str,
    tool: str,
    args: list[str],
    *,
    timeout: int = 120,
) -> None:
    log(message)
    sequence.append({"tool": tool, **runner(args, timeout=timeout)})


def _run_claim_stage(
    skip_claims: bool,
    log: Log,
    claim_runner: ClaimRunner,
) -> list[ClaimResult]:
    if skip_claims:
        log("6/6 claim invariants SKIPPED (--skip-claims)")
        return []
    log("6/6 claim invariant suite...")
    return claim_runner()


def _build_report(
    sequence: list[ToolResult],
    claim_results: list[ClaimResult],
    priority_builder: PriorityBuilder,
    grade_resolver: GradeResolver,
    failure_counter: FailureCounter,
) -> dict[str, Any]:
    health = _step(sequence, "project_health")
    dead_code = _step(sequence, "dead_code")
    constraints = _step(sequence, "check_constraints")
    items = priority_builder(health, dead_code, constraints, claim_results)
    priority = _highest_priority(items)
    failures = failure_counter(sequence, claim_results)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dogfood_sequence": sequence,
        "claim_invariant_status": claim_results,
        "priority_matrix": items,
        "summary": {
            "work_item_count": len(items),
            "highest_priority": priority,
            "health_grade": grade_resolver(health.get("data", {})),
            "claim_failures": sum(
                claim["status"] == "failed" for claim in claim_results
            ),
            "tool_failures": failures,
        },
    }


def _step(sequence: list[ToolResult], tool: str) -> ToolResult:
    return next((step for step in sequence if step["tool"] == tool), {})


def _highest_priority(items: list[WorkItem]) -> str:
    for level in ("P0", "P1", "P2", "P3"):
        if any(item["priority"] == level for item in items):
            return level
    return "None"


def _exit_code(summary: dict[str, Any]) -> int:
    if summary["tool_failures"]:
        return 2
    return 1 if summary["work_item_count"] else 0
