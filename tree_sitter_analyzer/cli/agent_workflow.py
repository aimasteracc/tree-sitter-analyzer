"""Agent workflow pack builders for the CLI."""

from __future__ import annotations

from typing import Any

PHASE_ORDER = ("set", "map", "analyze", "retrieve", "trace")


PHASE_ROUTING: tuple[dict[str, str], ...] = (
    {
        "from": "set",
        "to": "map",
        "condition": "When you can read a quick project portrait and target language is clear.",
        "goal": "Move from global context to candidate-file discovery.",
    },
    {
        "from": "map",
        "to": "analyze",
        "condition": "When a candidate queue head is chosen.",
        "goal": "Move from broad file list to one scoped target file.",
    },
    {
        "from": "analyze",
        "to": "retrieve",
        "condition": "When risk, edits, and test hints are known.",
        "goal": "Move from risk triage to focused read slice.",
    },
    {
        "from": "retrieve",
        "to": "trace",
        "condition": "When target symbols or ranges are in context.",
        "goal": "Move from local slice understanding to impact and test planning.",
    },
    {
        "from": "trace",
        "to": "done",
        "condition": "When queue-boundary verification is done.",
        "goal": "Close the queue item and hand off evidence for next run.",
    },
)


def build_agent_workflow_pack(
    project_root: str,
    target_path: str | None = None,
) -> dict[str, Any]:
    """Build a SMART workflow command pack for agents and humans."""
    target = target_path or "path/to/file.py"
    steps = _build_steps(target)
    queue_boundary = _build_queue_boundary_commands()
    current_phase = _current_phase(target_path)
    current_step = _step_for_phase(steps, current_phase)
    recommended_commands = list(current_step["cli_commands"])
    sprint_contract = _build_sprint_contract(
        target_path,
        current_phase,
        current_step,
        steps,
        queue_boundary,
    )
    agent_summary = _build_agent_summary(
        target_path,
        steps,
        queue_boundary,
        current_phase,
        recommended_commands,
    )
    result = {
        "success": True,
        "workflow": "SMART agent workflow pack",
        "workflow_mode": "SMART-SET-MAP-ANALYZE-RETRIEVE-TRACE",
        "project_root": project_root,
        "target_path": target_path,
        "current_phase": current_phase,
        "routing": _build_phase_routing(steps),
        "phase_order": list(PHASE_ORDER),
        "current_step": current_step,
        "recommended_commands": recommended_commands,
        "steps": steps,
        "queue_boundary_commands": queue_boundary,
        "sprint_contract": sprint_contract,
        "agent_summary": agent_summary,
        # G8: mirror agent_summary.summary_line to top-level so callers
        # walking the generic envelope find it without reaching into the
        # nested dict.
        "summary_line": agent_summary["summary_line"],
    }
    result["toon_content"] = _build_toon_content(result)
    return result


def _build_steps(target: str) -> list[dict[str, Any]]:
    """Build all SMART workflow steps."""
    steps = [
        _set_step(),
        _map_step(),
        _analyze_step(target),
        _retrieve_step(target),
        _trace_step(target),
    ]
    return _build_step_handoffs(steps)


def _build_step_handoffs(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach handoff condition metadata to each step."""
    phase_map = {route["from"]: route for route in PHASE_ROUTING}
    for step in steps:
        route = phase_map[step["step"]]
        step["handoff"] = {
            "to": route["to"],
            "condition": route["condition"],
            "goal": route["goal"],
            "transition_command": (
                step["cli_commands"][0] if step["cli_commands"] else ""
            ),
        }
    return steps


def _current_phase(target_path: str | None) -> str:
    """Return the phase an agent should start from for the current request."""
    return "analyze" if target_path else "set"


def _step_for_phase(steps: list[dict[str, Any]], phase: str) -> dict[str, Any]:
    """Return the workflow step matching the requested phase."""
    for step in steps:
        if step["step"] == phase:
            return step
    raise ValueError(f"Unknown workflow phase: {phase}")


def _build_phase_routing(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build route metadata in the same order as command pack steps."""
    phase_map = {route["from"]: route for route in PHASE_ROUTING}
    routes = []
    for step in steps:
        route = phase_map[step["step"]]
        next_step = route["to"]
        routes.append(
            {
                **route,
                "phase_index": step["step_index"],
                "to_step": next_step,
                "stop_condition": step["stop_condition"],
                "transition_command": (
                    step["cli_commands"][0] if step["cli_commands"] else ""
                ),
            }
        )
    return routes


def _build_next_phase(current_phase: str) -> str:
    """Return the expected next phase for a queue item."""
    for route in PHASE_ROUTING:
        if route["from"] == current_phase:
            return route["to"]
    return "done"


def _build_transition_signal(current_phase: str) -> str:
    """Return a compact reason to move out of the current phase."""
    for route in PHASE_ROUTING:
        if route["from"] == current_phase:
            return route["condition"]
    return "Queue item is complete; proceed to next file or next workflow run."


def _set_step() -> dict[str, Any]:
    return {
        "step": "set",
        "step_index": 0,
        "goal": "Establish project context and get a first project portrait.",
        "mcp_tools": ["set_project_path", "get_project_overview"],
        "cli_commands": [
            "uv run tree-sitter-analyzer overview --format json",
            "uv run tree-sitter-analyzer agent-skills --format json",
            "uv run tree-sitter-analyzer parser-readiness --format json",
        ],
        "stop_condition": "Project root and broad shape are understood.",
    }


def _map_step() -> dict[str, Any]:
    return {
        "step": "map",
        "step_index": 1,
        "goal": "Find candidate files before reading code.",
        "mcp_tools": ["list_files", "find_and_grep", "search_content"],
        "cli_commands": [
            "uv run list-files . --types f",
            'uv run find-and-grep --roots . --query "TODO|FIXME" --output-format json',
        ],
        "stop_condition": "A small set of relevant files is identified.",
    }


def _analyze_step(target: str) -> dict[str, Any]:
    return {
        "step": "analyze",
        "step_index": 2,
        "goal": "Understand file shape, health, and edit risk.",
        "mcp_tools": [
            "smart_context",
            "check_file_health",
            "safe_to_edit",
            "refactoring_suggestions",
        ],
        "cli_commands": [
            f"uv run tree-sitter-analyzer smart-context {target} --format json",
            f"uv run tree-sitter-analyzer file-health {target} --format json",
            f"uv run tree-sitter-analyzer safe-to-edit {target} --edit-type refactor --format json",
            f"uv run tree-sitter-analyzer refactor {target} --format json",
        ],
        "stop_condition": "Queue head, edit boundary, and verification hints are clear.",
    }


def _retrieve_step(target: str) -> dict[str, Any]:
    return {
        "step": "retrieve",
        "step_index": 3,
        "goal": "Read only the code slice needed for the current decision.",
        "mcp_tools": ["analyze_code_structure", "extract_code_section", "query_code"],
        "cli_commands": [
            f"uv run tree-sitter-analyzer {target} --structure --output-format json",
            f"uv run tree-sitter-analyzer {target} --partial-read --start-line 1 --end-line 80 --format json",
            f"uv run tree-sitter-analyzer {target} --query-key methods --output-format json",
        ],
        "stop_condition": "Only relevant symbols or line ranges are in context.",
    }


def _trace_step(target: str) -> dict[str, Any]:
    return {
        "step": "trace",
        "step_index": 4,
        "goal": "Close the loop with dependency and test impact.",
        "mcp_tools": ["analyze_dependencies", "analyze_change_impact"],
        "cli_commands": [
            f"uv run tree-sitter-analyzer {target} --dependencies file_deps --format json",
            _scoped_change_impact_command(target),
        ],
        "stop_condition": (
            "Run the reported verification_command, then the queue boundary when risk remains."
        ),
    }


def _build_queue_boundary_commands() -> list[str]:
    return [
        "uv run tree-sitter-analyzer change-impact --agent-summary-only --format json",
        "uv run pytest -q",
    ]


def _build_agent_summary(
    target_path: str | None,
    steps: list[dict[str, Any]],
    queue_boundary: list[str],
    current_phase: str,
    recommended_commands: list[str],
) -> dict[str, Any]:
    """Build the compact decision surface for the workflow pack."""
    first_command = (
        f"uv run tree-sitter-analyzer safe-to-edit {target_path} --edit-type refactor --format json"
        if target_path
        else "uv run tree-sitter-analyzer overview --format json"
    )
    queue_ledger_command = (
        _scoped_change_impact_command(target_path) if target_path else ""
    )
    next_phase = _build_next_phase(current_phase)
    # G8: build summary_line + verdict so this planning tool obeys the
    # cross-tool envelope contract. ``verdict`` is "n/a" — workflow
    # planning has no analysis result to gate on; callers should branch
    # on ``current_phase`` / ``next_phase`` instead.
    summary_line = (
        f"agent_workflow phase={current_phase} next={next_phase} "
        f"recommended={len(recommended_commands)}"
    )
    return {
        "summary_line": summary_line,
        "verdict": "n/a",
        "risk": "none",
        "next_step": first_command,
        "current_phase": current_phase,
        "next_phase": next_phase,
        "transition_signal": _build_transition_signal(current_phase),
        "phase_order": [step["step"] for step in steps],
        "recommended_commands": recommended_commands,
        "step_count": len(steps),
        "stop_condition": "Run each step until its stop_condition is satisfied.",
        "queue_ledger_command": queue_ledger_command,
        "queue_boundary_command": queue_boundary[-1],
    }


def _build_sprint_contract(
    target_path: str | None,
    current_phase: str,
    current_step: dict[str, Any],
    steps: list[dict[str, Any]],
    queue_boundary: list[str],
) -> dict[str, Any]:
    """Build a compact evaluator contract for one queue item."""
    evaluator_checks = _build_evaluator_checks(target_path, queue_boundary)
    scope = "single_target_file" if target_path else "project_surface_discovery"
    return {
        "mode": "single_queue_item",
        "scope": scope,
        "current_phase": current_phase,
        "next_phase": _build_next_phase(current_phase),
        "transition_signal": _build_transition_signal(current_phase),
        "target_path": target_path,
        "phase_goal": current_step["goal"],
        "evaluator_checks": evaluator_checks,
        "evaluator_signature": {
            "required_pass": [
                check["name"] for check in evaluator_checks if check["required"]
            ],
            "ordered": True,
        },
        "steps_total": len(steps),
        "step_index": current_step["step_index"],
    }


def _build_evaluator_checks(
    target_path: str | None,
    queue_boundary: list[str],
) -> list[dict[str, Any]]:
    """Build evaluator checks that prevent one-shot and context-regression failures."""
    checks = [
        {
            "name": "queue_boundary",
            "command": queue_boundary[-1],
            "required": True,
            "purpose": "Run one queue-cycle verification before advancing.",
        }
    ]
    if target_path:
        checks.append(
            {
                "name": "queue_ledger",
                "command": _scoped_change_impact_command(target_path),
                "required": False,
                "purpose": (
                    "Emit scoped change-impact so evaluator can approve the handoff "
                    "to next queue item."
                ),
            }
        )
    return checks


def _scoped_change_impact_command(target: str) -> str:
    """Build the scoped trace command that also emits queue_ledger."""
    return (
        "uv run tree-sitter-analyzer change-impact "
        f"--change-impact-scope {target} --agent-summary-only --format json"
    )


def _build_toon_content(result: dict[str, Any]) -> str:
    """Build a compact text representation for --format toon."""
    sprint_contract = result["sprint_contract"]
    evaluator_checks = ", ".join(
        check["name"] for check in sprint_contract["evaluator_checks"]
    )
    lines = [
        "workflow: SMART agent workflow pack",
        f"workflow_mode: {result['workflow_mode']}",
        f"project_root: {result['project_root']}",
        f"target_path: {result.get('target_path') or ''}",
        f"current_phase: {result['current_phase']}",
        f"next_phase: {result['agent_summary']['next_phase']}",
        f"transition_signal: {result['agent_summary']['transition_signal']}",
        f"next_step: {result['agent_summary']['next_step']}",
        f"sprint_contract_mode: {sprint_contract['mode']}",
        f"evaluator_checks: {evaluator_checks}",
        "recommended_commands:",
        *[f"  - {command}" for command in result["recommended_commands"]],
        "steps:",
    ]
    for step in result["steps"]:
        lines.append(
            f"  - {step['step']}: {step['goal']} | first_cli={step['cli_commands'][0]}"
        )
    lines.append("handoffs:")
    for step in result["steps"]:
        handoff = step["handoff"]
        lines.append(
            f"  - {step['step']} -> {handoff['to']} when {handoff['condition']} "
            f"via {handoff['transition_command']}"
        )
    queue_ledger_command = result["agent_summary"].get("queue_ledger_command")
    if queue_ledger_command:
        lines.append(f"queue_ledger: {queue_ledger_command}")
    lines.append(f"queue_boundary: {result['queue_boundary_commands'][-1]}")
    return "\n".join(lines)
