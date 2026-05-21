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


def build_file_health_result(
    file_path: str,
    health: Any,
    smells: list[dict[str, Any]],
    resolved: str,
    analysis: Any,
) -> dict[str, Any]:
    """Build the result dict from health data, smells, and optional extraction plan."""
    # H6 fix: the upstream ``detect_code_smells`` emits dicts keyed on
    # ``smell`` (the canonical name) and never sets ``type``. The
    # ``code_patterns`` tool, which shares the same source data, projects
    # ``smell`` into ``type`` before returning. Mirror that projection
    # here so ``file_health.code_smells[].type`` is a non-empty string —
    # otherwise downstream cross-tool consumers see ``type: None`` and
    # think the smell category is missing.
    smells = _project_smell_type(smells)
    # K9: compute the adjusted grade once so every consumer (agent
    # action, optional extraction plan, base envelope) sees the same
    # post-penalty value.
    adjusted_total, adjusted_grade = _apply_smell_penalty(health, smells)
    action = _build_agent_next_action(
        file_path, adjusted_grade, health.dimensions, smells
    )
    result = _build_base_health_result(file_path, health, smells, action)
    result.update(
        _build_optional_extraction_fields(
            file_path, adjusted_grade, smells, resolved, analysis
        )
    )
    # Finding 6: mirror agent_summary.summary_line to the top-level envelope
    # so direct ``tool.execute()`` callers (CLI bridges, tests) see the same
    # ``summary_line`` field the MCP dispatch post-hook would inject.
    from ..base_tool import mirror_summary_line

    return mirror_summary_line(result)


def _project_smell_type(smells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """H6 fix: ensure every smell carries a ``type`` field.

    Upstream ``detect_code_smells`` returns dicts keyed on ``smell`` (e.g.
    ``deep_nesting``, ``long_method``). The ``code_patterns`` tool re-emits
    the same data under ``type`` so cross-tool consumers can branch on a
    single field. ``file_health`` was passing the raw upstream shape, so
    ``code_smells[].type`` came out as ``None``. We project here without
    mutating the upstream list — each smell becomes a new dict with both
    ``smell`` (kept for backwards compatibility) and ``type`` (the
    canonical name).

    N7 (round-28): ``type`` is now the canonical name with the legacy
    ``security:`` prefix stripped. The bare ``smell`` value is also
    normalized so the H6 contract ``type == smell`` keeps holding.
    """
    from .file_health_smells import canonical_smell_type

    projected: list[dict[str, Any]] = []
    for smell in smells:
        canonical = canonical_smell_type(smell)
        # Immutable update: build a new dict so the caller's list is
        # untouched if it is shared with another consumer.
        new_smell = dict(smell)
        new_smell["type"] = canonical
        # Normalize ``smell`` to the same canonical value so cross-tool
        # callers that branch on either field see consistent strings —
        # this also preserves the H6 contract that ``type == smell``.
        new_smell["smell"] = canonical
        projected.append(new_smell)
    return projected


def _build_base_health_result(
    file_path: str,
    health: Any,
    smells: list[dict[str, Any]],
    action: dict[str, Any],
) -> dict[str, Any]:
    """Build the common file-health response fields."""
    # K9: certain smells signal a problem the dimension scorer can't
    # see — a 3.5 KB single-line file has ``line_count==1`` and scores
    # full marks on size/complexity/structure even though it's clearly
    # unreviewable. Apply a smell-driven score adjustment here so the
    # grade reflects what the smells already flagged.
    adjusted_total, adjusted_grade = _apply_smell_penalty(health, smells)
    # ``verdict`` mirrors ``grade`` mapped to the safe_to_edit /
    # modification_guard vocabulary (A/B → SAFE, C → CAUTION, D/F →
    # UNSAFE). Same value, cross-tool canonical key — agents that
    # consume any safety tool's output can branch on ``verdict``.
    verdict_map = {
        "A": "SAFE",
        "B": "SAFE",
        "C": "CAUTION",
        "D": "UNSAFE",
        "F": "UNSAFE",
    }
    verdict = verdict_map.get(adjusted_grade, "CAUTION")
    return {
        "success": True,
        "file_path": file_path,
        "grade": adjusted_grade,
        "verdict": verdict,
        # ``total_score`` is the canonical name; ``health_score`` and
        # ``overall_score`` are documented aliases so callers that follow
        # the more common naming conventions still find the value
        # without needing to know our exact field name.
        "total_score": adjusted_total,
        "health_score": adjusted_total,
        "overall_score": adjusted_total,
        "signal": _build_signal(health.dimensions),
        "dimensions": health.dimensions,
        "code_smells": smells,
        # M8 (round-26): ``smells`` is exposed as a deprecated alias of
        # ``code_smells`` so callers that branch on either name see the
        # same list value. Before this, agents that probed
        # ``result.get('smells')`` got ``None`` while
        # ``result.get('code_smells')`` returned ``[]`` — same datum,
        # different types, and a ``for s in result['smells']`` would
        # raise ``TypeError``. The alias points at the same list object
        # so any mutation by either name is visible to the other.
        "smells": smells,
        "smell_count": len(smells),
        "recommendation": _build_recommendation(
            adjusted_grade, health.dimensions, smells
        ),
        "agent_summary": _build_agent_summary(
            file_path, health, smells, action, adjusted_total, adjusted_grade
        ),
        "agent_next_action": action,
    }


# K9: penalty table keyed on smell name. Numbers are picked so that:
#   - ``single_line_file`` (criticality unambiguous: 3.5 KB on one line)
#     guarantees grade ≤ B, typically dropping the score below 80.
#   - ``long_line`` (per occurrence) docks 3 points, with a ``critical``
#     severity adding a second 5-point penalty.
#   - Other already-handled smells (oversized_file, deep_nesting,
#     god_class, long_method) stay at 0 — the dimension scorer already
#     reflects them; double-docking would distort historical grades.
# Total penalty is bounded so a healthy file with one borderline smell
# still grades A/B.
_SMELL_SCORE_PENALTY: dict[str, int] = {
    "single_line_file": 35,
    "long_line": 3,
}
_SMELL_SEVERITY_PENALTY: dict[str, int] = {
    # Additional dock when the smell carries critical severity AND
    # belongs to one of the K9-introduced types. Other criticals already
    # show up via dimension scoring.
    "single_line_file": 10,
    "long_line": 5,
}
_MAX_SMELL_PENALTY = 60  # never drop further than F-grade floor for these
_GRADE_THRESHOLDS = (
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (50, "D"),
)


def _apply_smell_penalty(
    health: Any, smells: list[dict[str, Any]]
) -> tuple[float, str]:
    """Return (adjusted_total, adjusted_grade) after K9 smell penalties.

    The original ``health.total`` comes from weighted dimension scores
    that have no visibility into K9 smells (``long_line`` /
    ``single_line_file``). We compute an additive penalty here so the
    grade matches what the smells already say is wrong with the file.

    Penalty is clipped at ``_MAX_SMELL_PENALTY`` and the final score is
    floored at 0 to keep downstream math safe.
    """
    if not smells:
        return float(health.total), health.grade
    penalty = 0
    for smell in smells:
        name = smell.get("smell") or smell.get("type")
        if not name:
            continue
        base = _SMELL_SCORE_PENALTY.get(name, 0)
        if base == 0:
            continue
        penalty += base
        if smell.get("severity") == "critical":
            penalty += _SMELL_SEVERITY_PENALTY.get(name, 0)
    if penalty == 0:
        return float(health.total), health.grade
    penalty = min(penalty, _MAX_SMELL_PENALTY)
    adjusted = max(0.0, float(health.total) - penalty)
    adjusted = round(adjusted, 1)
    return adjusted, _grade_from_score(adjusted)


def _grade_from_score(score: float) -> str:
    """Mirror ``HealthScore.grade`` so adjusted scores get a fresh letter."""
    for threshold, letter in _GRADE_THRESHOLDS:
        if score >= threshold:
            return letter
    return "F"


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
    adjusted_total: float | None = None,
    adjusted_grade: str | None = None,
) -> dict[str, Any]:
    """Build the compact first-read health decision summary for agents.

    ``adjusted_total`` / ``adjusted_grade`` are the K9-adjusted numbers
    when smell-driven penalties apply. They default to ``health.total``
    / ``health.grade`` so existing call sites keep their behaviour.
    """
    weakest_dimension, weakest_score = _weakest_dimension_score(health.dimensions)
    score = adjusted_total if adjusted_total is not None else health.total
    grade = adjusted_grade if adjusted_grade is not None else health.grade
    # Finding 6: include a one-line summary so the central post-hook
    # can mirror it to the top-level ``summary_line``. Agents that
    # branch on ``summary_line`` (round-11 envelope) now see a useful
    # value instead of None.
    summary_line = (
        f"{file_path} grade={grade} score={score} "
        f"smells={len(smells)} weakest={weakest_dimension}"
    )
    summary = {
        "summary_line": summary_line,
        "risk": action["priority"],
        "grade": grade,
        "score": score,
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
