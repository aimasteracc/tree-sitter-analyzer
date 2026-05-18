"""Agent workflow pack builders for the CLI."""

from __future__ import annotations

from typing import Any

PHASE_ORDER = ("set", "map", "analyze", "retrieve", "trace")


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
    result = {
        "success": True,
        "workflow": "SMART agent workflow pack",
        "project_root": project_root,
        "target_path": target_path,
        "current_phase": current_phase,
        "phase_order": list(PHASE_ORDER),
        "current_step": current_step,
        "recommended_commands": recommended_commands,
        "steps": steps,
        "queue_boundary_commands": queue_boundary,
        "agent_summary": _build_agent_summary(
            target_path,
            steps,
            queue_boundary,
            current_phase,
            recommended_commands,
        ),
    }
    result["toon_content"] = _build_toon_content(result)
    return result


def _build_steps(target: str) -> list[dict[str, Any]]:
    """Build all SMART workflow steps."""
    return [
        _set_step(),
        _map_step(),
        _analyze_step(target),
        _retrieve_step(target),
        _trace_step(target),
    ]


def _current_phase(target_path: str | None) -> str:
    """Return the phase an agent should start from for the current request."""
    return "analyze" if target_path else "set"


def _step_for_phase(steps: list[dict[str, Any]], phase: str) -> dict[str, Any]:
    """Return the workflow step matching the requested phase."""
    for step in steps:
        if step["step"] == phase:
            return step
    raise ValueError(f"Unknown workflow phase: {phase}")


def _set_step() -> dict[str, Any]:
    return {
        "step": "set",
        "goal": "Establish project context and get a first project portrait.",
        "mcp_tools": ["set_project_path", "get_project_overview"],
        "cli_commands": ["uv run tree-sitter-analyzer overview --format json"],
        "stop_condition": "Project root and broad shape are understood.",
    }


def _map_step() -> dict[str, Any]:
    return {
        "step": "map",
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
    return {
        "risk": "none",
        "next_step": first_command,
        "current_phase": current_phase,
        "phase_order": [step["step"] for step in steps],
        "recommended_commands": recommended_commands,
        "step_count": len(steps),
        "stop_condition": "Run each step until its stop_condition is satisfied.",
        "queue_ledger_command": queue_ledger_command,
        "queue_boundary_command": queue_boundary[-1],
    }


def _scoped_change_impact_command(target: str) -> str:
    """Build the scoped trace command that also emits queue_ledger."""
    return (
        "uv run tree-sitter-analyzer change-impact "
        f"--change-impact-scope {target} --agent-summary-only --format json"
    )


def _build_toon_content(result: dict[str, Any]) -> str:
    """Build a compact text representation for --format toon."""
    lines = [
        "workflow: SMART agent workflow pack",
        f"project_root: {result['project_root']}",
        f"target_path: {result.get('target_path') or ''}",
        f"current_phase: {result['current_phase']}",
        f"next_step: {result['agent_summary']['next_step']}",
        "recommended_commands:",
        *[f"  - {command}" for command in result["recommended_commands"]],
        "steps:",
    ]
    for step in result["steps"]:
        lines.append(
            f"  - {step['step']}: {step['goal']} | first_cli={step['cli_commands'][0]}"
        )
    queue_ledger_command = result["agent_summary"].get("queue_ledger_command")
    if queue_ledger_command:
        lines.append(f"queue_ledger: {queue_ledger_command}")
    lines.append(f"queue_boundary: {result['queue_boundary_commands'][-1]}")
    return "\n".join(lines)
