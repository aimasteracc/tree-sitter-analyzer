"""Pure helper builders for refactoring suggestions."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _to_project_relative(file_path: str, project_root: str | None) -> str:
    """Return ``file_path`` rendered as a project-relative path when possible.

    G9: ``build_success_response`` and ``error_response`` were emitting
    raw absolute paths (``/Users/.../foo.py``) in both ``file`` and
    ``file_path``. Every other tool returns a project-relative path. This
    helper normalises both fields so the response no longer leaks the
    user's home directory while preserving the back-compat ``file``
    alias mentioned in the comment below.

    Returns the original path unchanged when there is no project root or
    the path lies outside the root (e.g. tests that pass an absolute
    path under /tmp). The output never includes a leading ``./``.
    """
    if not file_path:
        return file_path
    if not project_root:
        return file_path
    try:
        rel = Path(file_path).resolve().relative_to(Path(project_root).resolve())
    except (ValueError, OSError):
        # Path is outside the project root — return as-is so the caller
        # at least gets a usable identifier. The MCP boundary blocks
        # truly external paths upstream.
        return file_path
    rel_str = str(rel)
    return rel_str if rel_str != "." else file_path


def get_nesting_depth(node: ast.AST) -> int:
    """Calculate the maximum nesting depth of a function."""
    max_depth = 0

    def walk(n: ast.AST, depth: int) -> None:
        nonlocal max_depth
        is_control = isinstance(
            n, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)
        )
        current = depth + (1 if is_control else 0)
        max_depth = max(max_depth, current)
        for child in ast.iter_child_nodes(n):
            walk(child, current)

    walk(node, 0)
    return max_depth


def is_static_method(node: ast.FunctionDef) -> bool:
    """Detect if a method body never references self/cls."""
    if not node.args.args:
        return True
    first_arg = node.args.args[0].arg
    if first_arg not in ("self", "cls"):
        return True
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == first_arg:
            if isinstance(child.ctx, ast.Load):
                return False
    return True


def make_pattern(
    rule: dict[str, Any], priority_score: int = 50, **kwargs: Any
) -> dict[str, Any]:
    """Build a pattern suggestion dict from a rule template."""
    fmt_kwargs = {"threshold": rule["threshold"], **kwargs}
    message = rule["message"].format(**fmt_kwargs)
    result: dict[str, Any] = {
        "type": "pattern",
        "id": rule["id"],
        "name": rule["name"],
        "severity": rule["severity"],
        "message": message,
        "priority_score": priority_score,
    }
    _add_line_range(result, kwargs)
    return result


def make_extraction(
    rule: dict[str, Any], priority_score: int = 50, **kwargs: Any
) -> dict[str, Any]:
    """Build an extraction suggestion dict from a rule template."""
    fmt_kwargs = {"threshold": rule.get("threshold", 0), **kwargs}
    message = rule["message"].format(**fmt_kwargs)
    result: dict[str, Any] = {
        "type": "extraction",
        "id": rule["id"],
        "name": rule["name"],
        "message": message,
        "priority_score": priority_score,
    }
    _add_line_range(result, kwargs)
    return result


def make_summary(suggestions: list[dict[str, Any]]) -> str:
    """Build a human-readable summary of all suggestions."""
    if not suggestions:
        return "No significant refactoring issues found."
    critical = sum(1 for s in suggestions if s.get("severity") == "critical")
    major = sum(1 for s in suggestions if s.get("severity") == "major")
    minor = len(suggestions) - critical - major
    parts = []
    if critical:
        parts.append(f"{critical} critical")
    if major:
        parts.append(f"{major} major")
    if minor:
        parts.append(f"{minor} minor")
    return f"Found {', '.join(parts)} refactoring suggestions."


def make_agent_summary(
    file_path: str, suggestions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build a compact next-action summary for agent workflows."""
    refactor_command = (
        f"uv run python -m tree_sitter_analyzer {file_path} --refactor --format json"
    )
    impact_command = (
        "uv run python -m tree_sitter_analyzer --change-impact "
        f"--change-impact-scope {file_path} --format json"
    )

    if not suggestions:
        # Finding 6: include summary_line so the central post-hook can
        # mirror it to the top-level envelope.
        return {
            "summary_line": f"{file_path} refactor=clean suggestions=0",
            "risk": "low",
            "next_step": "No refactoring action needed.",
            "suggested_tests": [refactor_command],
            "stop_condition": "No suggestions remain for this file.",
        }

    top = suggestions[0]
    tests = [refactor_command, impact_command]
    severities: dict[str, int] = {}
    for s in suggestions:
        sev = str(s.get("severity") or "info")
        severities[sev] = severities.get(sev, 0) + 1
    sev_summary = " ".join(f"{k}={v}" for k, v in severities.items()) or "info=0"
    summary: dict[str, Any] = {
        "summary_line": (
            f"{file_path} suggestions={len(suggestions)} top={top.get('pattern', 'unknown')} "
            f"{sev_summary}"
        ),
        "risk": _agent_risk(suggestions),
        "next_step": _next_step_for(top),
        "suggested_tests": _dedupe_tests(
            tests
            + [command.replace("<file>", file_path) for command in _tests_for(top)]
        ),
        "stop_condition": _stop_condition_for(top),
    }

    line_range = top.get("line_range")
    if line_range:
        summary["target_lines"] = f"{line_range['start']}-{line_range['end']}"

    recipe = top.get("recipe")
    if recipe:
        summary["target_owner"] = recipe.get("target_owner")
        summary["move_methods"] = recipe.get("move_methods", [])

    precise_plan = top.get("precise_plan")
    if precise_plan:
        summary["target_owner"] = precise_plan.get("function")
        summary["target_module"] = precise_plan.get("helper_module")

    return summary


def get_refactoring_tool_schema() -> dict[str, Any]:
    """Return the JSON schema for refactoring suggestion tool input."""
    return {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the source file to analyze",
            },
            "language": {
                "type": "string",
                "description": "Programming language (auto-detected if omitted)",
            },
            "max_suggestions": {
                "type": "integer",
                "description": "Maximum suggestions to return (default: 10)",
                "default": 10,
            },
            "include_extractions": {
                "type": "boolean",
                "description": "Include specific extraction targets (default: true)",
                "default": True,
            },
            "include_skeleton": {
                "type": "boolean",
                "description": (
                    "Include code skeletons in extraction plans "
                    "(default: false, saves ~50% tokens)"
                ),
                "default": False,
            },
            "output_format": {
                "type": "string",
                "enum": ["json", "toon"],
                "description": "'toon' (default) saves ~60% tokens vs 'json'",
                "default": "toon",
            },
        },
        "required": ["file_path"],
        # F5: refuse unknown parameters with a did-you-mean hint. Enforced
        # centrally by BaseMCPTool.__init_subclass__ — declared here so the
        # schema describes the contract accurately.
        "additionalProperties": False,
    }


def build_success_response(
    file_path: str,
    suggestions: list[dict[str, Any]],
    max_suggestions: int,
    include_skeleton: bool,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Build the final successful refactoring response.

    G9: ``project_root`` lets us emit a project-relative ``file_path``
    in the envelope. ``file`` keeps the same value so the (single
    test-only) back-compat alias still resolves without leaking the
    user's absolute home path.
    """
    finalized = finalize_suggestions(suggestions, max_suggestions, include_skeleton)
    from ..base_tool import mirror_summary_line

    display_path = _to_project_relative(file_path, project_root)
    return mirror_summary_line(
        {
            "success": True,
            # ``file_path`` is the canonical field used across every other
            # tool; ``file`` is kept as a backward-compat alias. Both
            # are normalised to a project-relative path (G9).
            "file": display_path,
            "file_path": display_path,
            "total_suggestions": len(finalized),
            # ``count``/``results`` are cross-tool canonical aliases so an
            # agent walking a generic envelope finds the data without
            # learning this tool's specific vocabulary.
            "count": len(finalized),
            "results": finalized,
            "summary": make_summary(finalized),
            "agent_summary": make_agent_summary(display_path, finalized),
            "suggestions": finalized,
        }
    )


def finalize_suggestions(
    suggestions: list[dict[str, Any]],
    max_suggestions: int,
    include_skeleton: bool,
) -> list[dict[str, Any]]:
    """Apply presentation defaults and ordering to suggestions."""
    if not include_skeleton:
        strip_precise_plan_skeletons(suggestions)
    return sorted(suggestions, key=lambda s: s.get("priority_score", 0), reverse=True)[
        :max_suggestions
    ]


def strip_precise_plan_skeletons(suggestions: list[dict[str, Any]]) -> None:
    """Remove extraction skeletons from precise plans in place."""
    for suggestion in suggestions:
        plan = suggestion.get("precise_plan")
        if not plan:
            continue
        for ext_target in plan.get("extractions", []):
            ext_target.pop("skeleton", None)


def error_response(
    file_path: str,
    error: str,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Return a standardized error response.

    G9: when a project root is known, both ``file`` and ``file_path``
    are emitted as project-relative so the error envelope does not leak
    absolute paths either.
    """
    display_path = _to_project_relative(file_path, project_root)
    return {
        "success": False,
        "file": display_path,
        "file_path": display_path,
        "error": error,
        "suggestions": [],
        "results": [],
        "count": 0,
    }


def _add_line_range(result: dict[str, Any], kwargs: dict[str, Any]) -> None:
    """Attach a line_range object to a suggestion when present."""
    if "line_range" not in kwargs:
        return
    lr = kwargs["line_range"]
    result["line_range"] = {"start": lr[0], "end": lr[1]}


def _agent_risk(suggestions: list[dict[str, Any]]) -> str:
    severities = {suggestion.get("severity") for suggestion in suggestions}
    if "critical" in severities:
        return "high"
    if "major" in severities:
        return "medium"
    return "low"


def _next_step_for(suggestion: dict[str, Any]) -> str:
    recipe = suggestion.get("recipe")
    if recipe:
        owner = recipe.get("target_owner", "the suggested owner")
        methods = ", ".join(recipe.get("move_methods", []))
        if methods:
            return f"Extract {methods} into {owner}."
        return f"Extract the suggested responsibility into {owner}."

    plan = suggestion.get("precise_plan")
    if plan:
        function = plan.get("function", "the selected function")
        helper_module = plan.get("helper_module", "a helper module")
        return f"Extract helper logic from {function} into {helper_module}."

    return suggestion.get(
        "message", "Review the highest-priority refactoring suggestion."
    )


def _tests_for(suggestion: dict[str, Any]) -> list[str]:
    recipe = suggestion.get("recipe")
    if recipe:
        return list(recipe.get("tests", []))
    return []


def _stop_condition_for(suggestion: dict[str, Any]) -> str:
    recipe = suggestion.get("recipe")
    if recipe and recipe.get("stop_condition"):
        return str(recipe["stop_condition"])

    if suggestion.get("precise_plan"):
        name = suggestion.get("name", "this suggestion")
        return f"Re-run refactoring_suggestions and confirm {name} no longer appears."

    return "Re-run refactoring_suggestions and confirm the suggestion count drops."


def _dedupe_tests(commands: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for command in commands:
        normalized = command.replace("<file>", "{file_path}")
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(command)
    return deduped
