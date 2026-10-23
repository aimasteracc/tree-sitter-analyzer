"""Verdict vocabulary and agent edit-workflow builders for safe-to-edit."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any

from .verification_command import build_test_command, detect_default_test_command


@dataclass(frozen=True)
class AgentWorkflowContext:
    """Inputs needed to build the structured agent edit workflow.

    ``certified`` (Codex P2 #1299 round-6): on snapshot-certified routes the
    workflow's default test command must not be derived from live
    non-inventoried config files (package.json/go.mod/...) that can drift
    for the same snapshot identity.
    """

    file_path: str
    risk: str
    edit_type: str
    has_tests: bool
    test_files: list[str]
    health_grade: str
    project_root: str
    certified: bool = False


# Verdict severity order — higher index = more severe. Used to promote
# the safe_to_edit verdict when constraint violations imply a stricter
# answer than the risk-level-derived one.
_VERDICT_SEVERITY: dict[str, int] = {
    "SAFE": 0,
    "INFO": 0,
    "REVIEW": 1,
    "CAUTION": 2,
    "UNSAFE": 3,
    "ERROR": 3,
}


def _max_verdict(base: str, override: str | None) -> str:
    """Return whichever verdict is more severe, preferring the override on ties."""
    if not override:
        return base
    base_rank = _VERDICT_SEVERITY.get(base, 0)
    override_rank = _VERDICT_SEVERITY.get(override, 0)
    return override if override_rank >= base_rank else base


def _risk_to_verdict(risk: str) -> str:
    """Map ``risk_level`` to the modification_guard verdict vocabulary.

    safe → SAFE; caution → CAUTION; dangerous / high → UNSAFE.
    """
    risk_lower = (risk or "").lower()
    if risk_lower in ("dangerous", "high", "unsafe"):
        return "UNSAFE"
    if risk_lower in ("caution", "medium"):
        return "CAUTION"
    return "SAFE"


def build_agent_summary(
    context: AgentWorkflowContext,
    workflow: dict[str, Any],
    verdict_override: str | None = None,
) -> dict[str, Any]:
    """Build the compact first-read decision summary for agents.

    N1 (round-27): include ``summary_line`` + ``verdict`` so the
    cross-tool envelope contract (``TestEnvelopeContractSnapshot``) is
    satisfied. ``mirror_summary_line`` then copies the line to the
    top-level envelope for direct callers that bypass the dispatch hook.

    #781: ``verdict_override`` lets the caller pass an escalated verdict (from a
    constraint-violation or fixture promotion) so it flows into BOTH the
    ``summary_line`` and ``summary["verdict"]`` — the one-line decision surface
    must never disagree with the structured verdict.
    """
    before = workflow["before_edit_commands"]
    after = workflow["after_edit_commands"]
    boundary = workflow["queue_boundary_commands"]
    # verdict_override is a floor-raiser (escalation), never a downgrade:
    # _max_verdict keeps the more severe of the risk-derived base and the
    # override (and tolerates a None override), so a future caller can't use it
    # to silently lower the verdict below the risk level.
    verdict = _max_verdict(_risk_to_verdict(context.risk), verdict_override)
    summary_line = (
        f"{context.file_path} risk={context.risk} verdict={verdict} "
        f"health={context.health_grade} "
        f"tests={'yes' if context.has_tests else 'no'}"
    )
    summary = {
        "summary_line": summary_line,
        "verdict": verdict,
        "risk": context.risk,
        "edit_strategy": workflow["edit_strategy"],
        "next_step": _agent_next_step(context, workflow),
        "verification_command": (
            ""
            if workflow.get("test_verification_unidentified")
            else (after[0] if after else (boundary[0] if boundary else ""))
        ),
        "stop_condition": _agent_stop_condition(context, workflow),
    }
    if before:
        summary["preflight_command"] = before[0]
    if boundary:
        summary["queue_boundary_command"] = boundary[0]
    if workflow["guardrails"]:
        summary["guardrails"] = workflow["guardrails"]
    return summary


def build_agent_workflow(context: AgentWorkflowContext) -> dict[str, Any]:
    """Build a machine-friendly edit workflow for autonomous agents."""
    if context.certified:
        # Codex P2 (#1299 round-6/7/8): snapshot-bound default — live config
        # detection would read non-inventoried files, so the runner is
        # inferred from the target's extension; ambiguous ecosystems omit
        # the command entirely (None) rather than guessing.
        from .verification_command import certified_default_test_command

        default_command = certified_default_test_command(context.file_path)
    else:
        default_command = detect_default_test_command(context.project_root)
    focused_command = (
        build_test_command(default_command, context.test_files)
        if context.has_tests and default_command is not None
        else ""
    )
    boundary_command = default_command.command if default_command is not None else ""
    # Codex P2 (#1299 round-11, C49): when no runner can be identified, the
    # health/impact commands must never be promoted to TEST verification.
    test_verification_unidentified = context.certified and default_command is None
    quoted_path = shlex.quote(context.file_path)
    pre_edit_commands = [focused_command] if focused_command else []
    post_edit_commands = [
        command
        for command in (
            focused_command or boundary_command,
            (
                "uv run python -m tree_sitter_analyzer "
                f"{quoted_path} --file-health --format json"
            ),
            "uv run python -m tree_sitter_analyzer --change-impact --format json",
        )
        if command
    ]

    return {
        "edit_strategy": _edit_strategy(context.risk, context.edit_type),
        "before_edit_commands": pre_edit_commands,
        "after_edit_commands": post_edit_commands,
        "queue_boundary_commands": [boundary_command] if boundary_command else [],
        "test_verification_unidentified": test_verification_unidentified,
        "guardrails": _agent_guardrails(
            context.risk,
            context.edit_type,
            context.health_grade,
            context.has_tests,
        ),
    }


def _edit_strategy(risk: str, edit_type: str) -> str:
    """Return a compact edit strategy label for agents."""
    if risk == "dangerous":
        return "split_into_atomic_edits"
    if edit_type == "rename":
        return "trace_references_before_edit"
    if risk == "caution":
        return "focused_edit_with_tests"
    return "direct_focused_edit"


def _agent_guardrails(
    risk: str,
    edit_type: str,
    health_grade: str,
    has_tests: bool,
) -> list[str]:
    """Return concise guardrails for an autonomous edit."""
    guardrails: list[str] = []
    if risk == "dangerous":
        guardrails.append("do not expand scope; split work into smaller edits")
    if edit_type == "refactor":
        guardrails.append("preserve public API signatures")
    if edit_type == "rename":
        guardrails.append("find and update all references before verification")
    if health_grade in {"D", "F"}:
        guardrails.append("run edit action=refactor before editing")
    if not has_tests:
        guardrails.append("add or identify verification before changing behavior")
    return guardrails


def _agent_next_step(
    context: AgentWorkflowContext,
    workflow: dict[str, Any],
) -> str:
    """Return one immediate action for the safe-to-edit decision."""
    before = workflow["before_edit_commands"]
    if context.risk == "dangerous":
        return "Split this edit into smaller scoped changes before editing."
    if before:
        return f"Run pre-edit verification first: {before[0]}"
    if not context.has_tests:
        return "Identify verification before changing behavior."
    return "Proceed with a focused edit."


def _agent_stop_condition(
    context: AgentWorkflowContext,
    workflow: dict[str, Any],
) -> str:
    """Describe when this edit queue can be considered safe to close."""
    after = workflow["after_edit_commands"]
    boundary = workflow["queue_boundary_commands"]
    verify = after[0] if after else (boundary[0] if boundary else "")
    if workflow.get("test_verification_unidentified"):
        return (
            "Test verification is unidentified for this project; run the "
            "project's test suite manually before and after the edit."
        )
    if context.risk == "dangerous":
        return "Each smaller edit passes focused verification before scope expands."
    if verify and boundary and verify != boundary[0]:
        return f"{verify} passes; run {boundary[0]} at the queue boundary."
    if verify:
        return f"{verify} exits successfully."
    return "A concrete verification command has been identified and run."
