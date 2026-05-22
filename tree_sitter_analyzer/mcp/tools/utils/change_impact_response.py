"""Response assembly helpers for change-impact analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LARGE_DIRTY_DIFF_THRESHOLD = 25


@dataclass(frozen=True)
class AgentSummaryContext:
    """Inputs needed for the compact agent decision summary."""

    risk: str
    changed_files: list[str]
    scope_paths: list[str] | None
    verification: dict[str, Any]
    strategy: dict[str, Any]
    affected_count: int
    tests_to_run_count: int


@dataclass(frozen=True)
class ChangeImpactResponseContext:
    """Computed parts for assembling a change-impact response."""

    request: Any
    risk: str
    affected: set[str]
    file_impacts: list[dict[str, Any]]
    visible_tests: list[str]
    all_tests: list[str]
    verification: dict[str, Any]
    strategy: dict[str, Any]
    test_mapping: dict[str, list[str]]
    agent_summary: dict[str, Any]


def _risk_to_verdict(risk: str) -> str:
    """Map change-impact risk_level to the canonical verdict vocabulary.

    pain-01b: tsa-landing and downstream agent loops expect a verdict
    field on every gate tool. Mapping (anti-bias: err high):
      "high"    → "CAUTION"  (block — invasive change, needs review)
      "medium"  → "REVIEW"   (warrants a careful test run)
      "low"     → "INFO"     (safe edit, normal test cadence)
      "none"    → "INFO"     (no changes detected)
    """
    if risk == "high":
        return "CAUTION"
    if risk == "medium":
        return "REVIEW"
    return "INFO"


def build_no_changes_result(
    mode: str, scope_paths: list[str] | None = None
) -> dict[str, Any]:
    """Build a stable empty-diff response."""
    return {
        "success": True,
        "verdict": "INFO",
        "mode": mode,
        "changed_files": [],
        "summary": "No changes detected",
        "agent_summary": {
            "verdict": "INFO",
            "risk": "none",
            "scope": "scoped" if scope_paths else "workspace",
            "changed_count": 0,
            "affected_count": 0,
            "tests_to_run_count": 0,
            "next_step": "No changes detected; no verification needed.",
            "verification_command": "",
            "stop_condition": "Working tree remains unchanged for the selected mode and scope.",
        },
    }


def build_agent_summary_only_response(result: dict[str, Any]) -> dict[str, Any]:
    """Return a compact change-impact response for agent decision loops."""
    summary = result.get("agent_summary", {})
    risk_level = result.get("risk_level", summary.get("risk", "none"))
    return {
        "success": result.get("success", False),
        "verdict": result.get("verdict", _risk_to_verdict(risk_level)),
        "mode": result.get("mode", "diff"),
        "scope_paths": result.get("scope_paths", []),
        "scope_filtered": result.get("scope_filtered", False),
        "agent_summary_only": True,
        "agent_summary": summary,
        "risk_level": risk_level,
        "changed_count": result.get("changed_count", summary.get("changed_count", 0)),
        "affected_count": result.get(
            "affected_count", summary.get("affected_count", 0)
        ),
        "tests_to_run_count": result.get(
            "tests_to_run_count", summary.get("tests_to_run_count", 0)
        ),
        "next_step": summary.get("next_step", ""),
        "verification_command": result.get(
            "verification_command", summary.get("verification_command", "")
        ),
        "focused_test_command": result.get(
            "focused_test_command", summary.get("focused_test_command", "")
        ),
        "queue_ledger": result.get("queue_ledger", summary.get("queue_ledger", {})),
        "verification_strategy": result.get(
            "verification_strategy", summary.get("verification_strategy", "")
        ),
        "verification_steps": result.get("verification_steps", []),
        "stop_condition": summary.get("stop_condition", ""),
    }


def build_agent_summary(context: AgentSummaryContext) -> dict[str, Any]:
    """Build the compact decision surface agents need from change-impact."""
    verification = context.verification
    strategy = context.strategy
    summary: dict[str, Any] = {
        "verdict": _risk_to_verdict(context.risk),
        "risk": context.risk,
        "scope": "scoped" if context.scope_paths else "workspace",
        "changed_count": len(context.changed_files),
        "affected_count": context.affected_count,
        "tests_to_run_count": context.tests_to_run_count,
        "next_step": _agent_next_step(verification, strategy),
        "verification_command": verification["verification_command"],
        "verification_strategy": strategy["verification_strategy"],
        "stop_condition": _agent_stop_condition(context.risk, verification, strategy),
    }

    focused = strategy.get("focused_test_command")
    if focused:
        summary["focused_test_command"] = focused

    if context.changed_files:
        summary["changed_preview"] = context.changed_files[:5]

    if (
        len(context.changed_files) > LARGE_DIRTY_DIFF_THRESHOLD
        and not context.scope_paths
    ):
        summary["scope_hint"] = (
            "Large dirty worktree detected; pass scope_paths or "
            "--change-impact-scope for the current queue."
        )

    return summary


def attach_queue_ledger(
    result: dict[str, Any],
    *,
    mode: str,
    scope_paths: list[str] | None,
    scoped_changed_files: list[str],
    workspace_changed_files: list[str],
) -> dict[str, Any]:
    """Attach a lightweight scoped dirty-worktree ledger for agent handoffs."""
    if not scope_paths:
        return result

    out_of_scope = [
        path
        for path in workspace_changed_files
        if path not in set(scoped_changed_files)
    ]
    verification_command = result.get("verification_command") or result.get(
        "agent_summary", {}
    ).get("verification_command", "")
    ledger = {
        "mode": mode,
        "scope_paths": scope_paths,
        "scoped_changed_count": len(scoped_changed_files),
        "out_of_scope_changed_count": len(out_of_scope),
        "scoped_changed_preview": scoped_changed_files[:5],
        "out_of_scope_changed_preview": out_of_scope[:5],
        "handoff": _queue_ledger_handoff(
            scope_paths, scoped_changed_files, out_of_scope, verification_command
        ),
    }
    result["queue_ledger"] = ledger
    summary = result.setdefault("agent_summary", {})
    summary["queue_ledger"] = ledger
    summary["scope_hint"] = (
        f"Scoped queue has {len(scoped_changed_files)} changed file(s); "
        f"{len(out_of_scope)} out-of-scope dirty file(s) remain untouched."
    )
    return result


def _queue_ledger_handoff(
    scope_paths: list[str],
    scoped_changed_files: list[str],
    out_of_scope: list[str],
    verification_command: str,
) -> str:
    """Build one compact queue handoff sentence."""
    scope = ", ".join(scope_paths)
    verification = verification_command or "none"
    return (
        f"scope={scope}; scoped_changed={len(scoped_changed_files)}; "
        f"out_of_scope_dirty={len(out_of_scope)}; verification={verification}"
    )


def build_change_impact_response(
    context: ChangeImpactResponseContext,
) -> dict[str, Any]:
    """Assemble the final response without mixing computation and formatting."""
    request = context.request
    verification = context.verification
    strategy = context.strategy
    return {
        "success": True,
        "verdict": _risk_to_verdict(context.risk),
        "mode": request.mode,
        "scope_paths": request.scope_paths or [],
        "scope_filtered": bool(request.scope_paths),
        "agent_summary": context.agent_summary,
        "changed_count": len(request.changed_files),
        "changed_files": request.changed_files[:50],
        "affected_count": len(context.affected),
        "affected_files": sorted(context.affected)[:50] if context.affected else [],
        "risk_level": context.risk,
        "file_impacts": context.file_impacts[:20],
        "tests_to_run": context.visible_tests,
        "tests_to_run_count": len(context.all_tests),
        "tests_to_run_omitted_count": max(
            0, len(context.all_tests) - len(context.visible_tests)
        ),
        "test_required": verification["test_required"],
        "test_runner": verification["test_runner"],
        "default_test_command": verification["default_test_command"],
        "pytest_required": verification["pytest_required"],
        "pytest_command": verification["pytest_command"],
        "test_command": verification["test_command"],
        "verification_command": verification["verification_command"],
        "verification_reason": verification["verification_reason"],
        "focused_test_command": strategy["focused_test_command"],
        "verification_strategy": strategy["verification_strategy"],
        "verification_steps": strategy["verification_steps"],
        "verification_hint": strategy["verification_hint"],
        "test_mapping": context.test_mapping if context.test_mapping else {},
        "diff_stat": request.diff_stat[:500] if request.diff_stat else "",
    }


def _agent_next_step(verification: dict[str, Any], strategy: dict[str, Any]) -> str:
    """Return one concise next action for agent decision-making."""
    if not verification["test_required"]:
        return "Run git diff --check; pytest is not required for docs-only changes."
    focused = strategy.get("focused_test_command")
    if focused and focused != verification["verification_command"]:
        return f"Run focused verification first: {focused}"
    return f"Run verification: {verification['verification_command']}"


def _agent_stop_condition(
    risk: str,
    verification: dict[str, Any],
    strategy: dict[str, Any],
) -> str:
    """Describe when the current edit queue can be considered closed."""
    if not verification["test_required"]:
        # docs-only: no tests required, just diff cleanliness
        return "docs-only: git diff --check passes and no runtime files are added."
    if (
        risk == "high"
        and verification["verification_command"] != verification["default_test_command"]
    ):
        return (
            f"{verification['verification_command']} passes; run "
            f"{verification['default_test_command']} at the queue boundary."
        )
    steps = strategy.get("verification_steps") or [verification["verification_command"]]
    return f"{steps[-1]} exits successfully."
