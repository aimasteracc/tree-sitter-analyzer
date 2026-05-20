"""Pure helper builders for refactoring suggestions."""

from __future__ import annotations

import ast
from typing import Any


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
        return {
            "risk": "low",
            "next_step": "No refactoring action needed.",
            "suggested_tests": [refactor_command],
            "stop_condition": "No suggestions remain for this file.",
        }

    top = suggestions[0]
    tests = [refactor_command, impact_command]
    summary: dict[str, Any] = {
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
    }


def build_success_response(
    file_path: str,
    suggestions: list[dict[str, Any]],
    max_suggestions: int,
    include_skeleton: bool,
) -> dict[str, Any]:
    """Build the final successful refactoring response."""
    finalized = finalize_suggestions(suggestions, max_suggestions, include_skeleton)
    return {
        "success": True,
        # ``file_path`` is the canonical field used across every other
        # tool; ``file`` is kept as a backward-compat alias.
        "file": file_path,
        "file_path": file_path,
        "total_suggestions": len(finalized),
        # ``count``/``results`` are cross-tool canonical aliases so an
        # agent walking a generic envelope finds the data without
        # learning this tool's specific vocabulary.
        "count": len(finalized),
        "results": finalized,
        "summary": make_summary(finalized),
        "agent_summary": make_agent_summary(file_path, finalized),
        "suggestions": finalized,
    }


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


def error_response(file_path: str, error: str) -> dict[str, Any]:
    """Return a standardized error response."""
    return {
        "success": False,
        "file": file_path,
        "file_path": file_path,
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
