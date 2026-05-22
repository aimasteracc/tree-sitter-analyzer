"""Response builders for file health reports."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from .element_extractor import get_functions

_SIGNAL_MAP = {
    "complexity": {"low": "simple", "mid": "moderate_cc", "high": "high_cc"},
    "dependencies": {
        "low": "few_deps",
        "mid": "moderate_deps",
        "high": "high_coupling",
    },
    "size": {"low": "small", "mid": "medium_size", "high": "large_file"},
    "structure": {"low": "flat", "mid": "moderate_depth", "high": "deep_nesting"},
    "duplication": {"low": "dry", "mid": "some_dup", "high": "repeated_blocks"},
    "git_hotspot": {"low": "stable", "mid": "active", "high": "volatile"},
    "coverage": {
        "low": "well_tested",
        "mid": "partial_coverage",
        "high": "low_coverage",
    },
}


def _file_health_verdict(grade: str) -> str:
    """Map A-F grade to canonical verdict vocabulary.

    Anti-bias: when in doubt err toward higher severity — a false REVIEW
    is recoverable; a false INFO ships bugs.

    A or B → INFO; C → REVIEW; D or F → CAUTION.
    """
    if grade in ("A", "B"):
        return "INFO"
    if grade == "C":
        return "REVIEW"
    if grade in ("D", "F"):
        return "CAUTION"
    return "REVIEW"


def build_file_health_result(
    file_path: str,
    health: Any,
    smells: list[dict[str, Any]],
    resolved: str,
    analysis: Any,
) -> dict[str, Any]:
    """Build the result dict from health data, smells, and optional extraction plan."""
    action = _build_agent_next_action(
        file_path, health.grade, health.dimensions, smells
    )
    result = _build_base_health_result(file_path, health, smells, action)
    result.update(
        _build_optional_extraction_fields(
            file_path, health.grade, smells, resolved, analysis
        )
    )
    return result


def _build_base_health_result(
    file_path: str,
    health: Any,
    smells: list[dict[str, Any]],
    action: dict[str, Any],
) -> dict[str, Any]:
    """Build the common file-health response fields."""
    return {
        "success": True,
        "verdict": _file_health_verdict(health.grade),
        "file_path": file_path,
        "grade": health.grade,
        "total_score": health.total,
        "signal": _build_signal(health.dimensions),
        "dimensions": health.dimensions,
        "code_smells": smells,
        "smell_count": len(smells),
        "recommendation": _build_recommendation(
            health.grade, health.dimensions, smells
        ),
        "agent_summary": _build_agent_summary(file_path, health, smells, action),
        "agent_next_action": action,
    }


def _build_optional_extraction_fields(
    file_path: str,
    grade: str,
    smells: list[dict[str, Any]],
    resolved: str,
    analysis: Any,
) -> dict[str, Any]:
    """Build D/F-only next action and extraction plan fields."""
    if grade not in ("D", "F"):
        return {}

    fields = {"next_action": _suggest_next_action(file_path, smells)}
    plan = _build_extraction_plan(file_path, smells, resolved, analysis)
    if plan:
        fields["extraction_plan"] = plan
    return fields


def _build_signal(dimensions: dict[str, float]) -> str:
    """Build a concise signal string identifying the weakest dimension."""
    if not dimensions:
        return "no_data"

    worst_dim = min(dimensions, key=lambda k: dimensions[k], default="")
    worst_score = dimensions.get(worst_dim, 100)

    if worst_score >= 70:
        return "healthy"

    level = "mid" if worst_score >= 40 else "high"
    dim_signals = _SIGNAL_MAP.get(worst_dim, {})
    return dim_signals.get(level, f"{worst_dim}_{level}")


def _build_recommendation(
    grade: str,
    dimensions: dict[str, float],
    smells: list[dict[str, Any]],
) -> str:
    """Build a human-readable recommendation based on grade and smells."""
    if grade in ("A", "B") and not smells:
        return "File is in good shape. No immediate action needed."
    if not smells:
        worst = min(dimensions, key=lambda k: dimensions[k], default="")
        return f"Overall grade {grade} - weakest dimension is '{worst}'. Consider targeted improvement."

    critical = [s for s in smells if s["severity"] == "critical"]
    warnings = [s for s in smells if s["severity"] == "warning"]
    parts = [f"Grade {grade}"]
    if critical:
        parts.append(
            f"{len(critical)} critical: {', '.join(s['smell'] for s in critical)}"
        )
    if warnings:
        parts.append(
            f"{len(warnings)} warning(s): {', '.join(s['smell'] for s in warnings)}"
        )

    names = _long_method_names(smells)
    if names:
        parts.append(
            f"Extract: {', '.join(names[:3])} into standalone functions in a new module"
        )

    return ". ".join(parts) + ". Focus on critical items first."


def _long_method_names(smells: list[dict[str, Any]]) -> list[str]:
    """Extract long-method names from smell detail strings."""
    return [
        smell["detail"].split("'")[1]
        for smell in smells
        if smell["smell"] == "long_method" and "'" in smell["detail"]
    ]


def _suggest_next_action(file_path: str, smells: list[dict[str, Any]]) -> str:
    """Suggest the next action for D/F grade files."""
    if any(s["smell"] == "long_method" for s in smells):
        return (
            f"Call refactoring_suggestions(file_path='{file_path}') "
            f"for precise extraction plans with code skeletons"
        )

    if any(s["smell"] == "oversized_file" for s in smells):
        return (
            f"Call refactoring_suggestions(file_path='{file_path}') "
            f"to identify extraction targets, then split into focused modules"
        )

    return (
        f"Call refactoring_suggestions(file_path='{file_path}') "
        f"for specific fixes, then re-run check_file_health to verify"
    )


def _build_agent_next_action(
    file_path: str,
    grade: str,
    dimensions: dict[str, float],
    smells: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a structured next action that agents can execute directly."""
    if grade in ("A", "B") and not smells:
        return _build_noop_agent_action()

    weakest_dimension = min(dimensions, key=lambda k: dimensions[k], default="unknown")
    return _build_refactor_agent_action(file_path, grade, weakest_dimension, smells)


def _build_noop_agent_action() -> dict[str, Any]:
    """Build the action payload for files that need no immediate work."""
    return {
        "priority": "none",
        "reason": "file is healthy enough; no immediate refactor needed",
        "mcp_command": "",
        "cli_command": "",
        "post_edit_commands": [],
    }


def _build_refactor_agent_action(
    file_path: str,
    grade: str,
    weakest_dimension: str,
    smells: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the action payload for files that need focused cleanup."""
    return {
        "priority": _agent_action_priority(grade, smells),
        "reason": _agent_action_reason(grade, weakest_dimension, smells),
        "mcp_command": f"refactoring_suggestions(file_path='{file_path}')",
        "cli_command": _refactor_cli_command(file_path),
        "post_edit_commands": [
            _file_health_cli_command(file_path),
            "uv run python -m tree_sitter_analyzer --change-impact --format json",
        ],
    }


def _refactor_cli_command(file_path: str) -> str:
    """Build the CLI command for refactoring suggestions."""
    return (
        "uv run python -m tree_sitter_analyzer "
        f"{shlex.quote(file_path)} --refactor --format json"
    )


def _file_health_cli_command(file_path: str) -> str:
    """Build the CLI command for re-running file health."""
    return (
        "uv run python -m tree_sitter_analyzer "
        f"{shlex.quote(file_path)} --file-health --format json"
    )


def _agent_action_reason(
    grade: str,
    weakest_dimension: str,
    smells: list[dict[str, Any]],
) -> str:
    """Explain why the structured action is being recommended."""
    if smells:
        smell_names = ", ".join(smell["smell"] for smell in smells[:3])
        return f"grade {grade} with actionable smell(s): {smell_names}"
    return f"grade {grade}; weakest dimension is {weakest_dimension}"


def _agent_action_priority(grade: str, smells: list[dict[str, Any]]) -> str:
    """Return a coarse priority for autonomous agents."""
    if any(smell.get("severity") == "critical" for smell in smells):
        return "high"
    if grade in ("D", "F"):
        return "high"
    if grade == "C" or smells:
        return "medium"
    return "low"


def _build_agent_summary(
    file_path: str,
    health: Any,
    smells: list[dict[str, Any]],
    action: dict[str, Any],
) -> dict[str, Any]:
    """Build the compact first-read health decision summary for agents."""
    weakest_dimension, weakest_score = _weakest_dimension_score(health.dimensions)
    summary = {
        "verdict": _file_health_verdict(health.grade),
        "risk": action["priority"],
        "grade": health.grade,
        "score": health.total,
        "weakest_dimension": weakest_dimension,
        "weakest_score": weakest_score,
        "next_step": _health_next_step(action, smells),
        "verification_command": _health_verification_command(action, file_path),
        "stop_condition": _health_stop_condition(action, file_path),
    }
    target = _first_actionable_smell(smells)
    if target:
        summary["target_smell"] = target["smell"]
        _add_target_location_summary(summary, target)
    return summary


def _add_target_location_summary(
    summary: dict[str, Any], target: dict[str, Any]
) -> None:
    """Attach compact location details for the first actionable smell."""
    if "line" in target:
        summary["target_line"] = target["line"]
    if "symbol" in target:
        summary["target_symbol"] = target["symbol"]
    if ("line" in target or "symbol" in target) and target.get("detail"):
        summary["target_detail"] = target["detail"]


def _weakest_dimension_score(dimensions: dict[str, float]) -> tuple[str, float | None]:
    """Return the lowest health dimension and score for compact summaries."""
    if not dimensions:
        return "unknown", None
    dimension = min(dimensions, key=lambda key: dimensions[key])
    return dimension, dimensions[dimension]


def _health_next_step(action: dict[str, Any], smells: list[dict[str, Any]]) -> str:
    """Return the immediate next step for a health report."""
    if action["priority"] == "none":
        return "No immediate refactor needed."
    if not _has_refactor_target_smell(smells):
        return "Inspect the weakest health dimension and make a focused cleanup."
    return f"Run refactoring suggestions: {action['cli_command']}"


def _health_verification_command(action: dict[str, Any], file_path: str) -> str:
    """Return the primary command that verifies a health-driven edit."""
    post_edit = action.get("post_edit_commands") or []
    if post_edit:
        return post_edit[0]
    return _file_health_cli_command(file_path)


def _health_stop_condition(action: dict[str, Any], file_path: str) -> str:
    """Describe when a health-driven edit queue can close."""
    if action["priority"] == "none":
        return "File remains grade A/B with no actionable smells."
    return (
        f"Re-run {_file_health_cli_command(file_path)} "
        "and confirm the grade improves or smell_count drops."
    )


def _first_actionable_smell(smells: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the first smell worth surfacing in a compact summary."""
    if not smells:
        return None
    critical = [smell for smell in smells if smell.get("severity") == "critical"]
    return (critical or smells)[0]


def _has_refactor_target_smell(smells: list[dict[str, Any]]) -> bool:
    """Return whether refactoring_suggestions is likely to produce concrete targets."""
    target_smells = {"long_method", "oversized_file", "god_class", "deep_nesting"}
    return any(smell.get("smell") in target_smells for smell in smells)


def _build_extraction_plan(
    file_path: str,
    smells: list[dict[str, Any]],
    resolved_path: str,
    analysis: Any,
) -> dict[str, Any] | None:
    """Build a structured extraction plan for D/F grade files."""
    long_methods = [s for s in smells if s["smell"] == "long_method"]
    if not long_methods:
        return None

    targets = [
        _build_extraction_target(smell, resolved_path, analysis)
        for smell in long_methods[:3]
    ]
    stem = Path(file_path).stem
    parent = str(Path(file_path).parent)
    new_module = f"{parent}/_{stem}_helpers.py" if parent else f"_{stem}_helpers.py"

    return {
        "target_file": file_path,
        "new_module": new_module,
        "methods_to_extract": targets,
        "steps": [
            f"1. Read {file_path} with extract_code_section",
            f"2. Create {new_module} with extracted methods as standalone functions",
            f"3. Add delegates in {file_path} calling the new module",
            "4. Run tests to verify zero regressions",
            f"5. Re-run check_file_health(file_path='{file_path}')",
        ],
    }


def _build_extraction_target(
    smell: dict[str, Any], resolved_path: str, analysis: Any
) -> dict[str, Any]:
    """Build one extraction target from a long-method smell."""
    detail = smell.get("detail", "")
    name = detail.split("'")[1] if "'" in detail else "unknown"
    line_match = re.search(r"\(L(\d+)\)", detail)
    start_line = int(line_match.group(1)) if line_match else 0
    end_line = _find_function_end_line(resolved_path, start_line, analysis)
    return {
        "method": name,
        "start_line": start_line,
        "end_line": end_line,
        "priority": "critical" if smell.get("severity") == "critical" else "normal",
    }


def _find_function_end_line(file_path: str, start_line: int, analysis: Any) -> int:
    """Find the end line of a function using tree-sitter elements, with fallback."""
    if analysis:
        for func in get_functions(analysis):
            if func["line"] == start_line:
                return func["end_line"]  # type: ignore[no-any-return]

    try:
        lines = (
            Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
        )
    except Exception:  # nosec B110
        return start_line

    if start_line - 1 >= len(lines):
        return start_line

    base_indent = len(lines[start_line - 1]) - len(lines[start_line - 1].lstrip())
    for i in range(start_line, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        current_indent = len(lines[i]) - len(lines[i].lstrip())
        if current_indent <= base_indent:
            return i
    return len(lines)
