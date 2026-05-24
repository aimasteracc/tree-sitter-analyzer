"""Python AST bonus analysis for refactoring suggestions."""

from __future__ import annotations

import ast
from typing import Any

from .refactoring_suggestions_helpers import (
    get_nesting_depth,
    is_static_method,
    make_extraction,
    make_pattern,
)

MCP_TOOL_HOOK_METHODS = {
    "execute",
    "get_tool_definition",
    "get_tool_schema",
    "set_project_path",
    "validate_arguments",
}


def python_bonus_analysis(
    source: str,
    suggestions: list[dict[str, Any]],
    include_extractions: bool,
    pattern_rules: list[dict[str, Any]],
    extractable_patterns: list[dict[str, Any]],
) -> None:
    """Run Python-specific bonus analysis using AST."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return

    _attach_class_parents(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue

        name = node.name
        start, end = node.lineno, node.end_lineno or node.lineno
        _check_depth(node, name, start, end, suggestions, pattern_rules)
        _check_param_count(node, name, start, suggestions, pattern_rules)

        if include_extractions and isinstance(node, ast.FunctionDef):
            _check_static_extraction(
                node, name, start, end, suggestions, extractable_patterns
            )


def _attach_class_parents(tree: ast.AST) -> None:
    """Attach class parent references to immediate class children."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for child in node.body:
            child.parent = node  # type: ignore[attr-defined]


def _check_depth(
    node: ast.AST,
    name: str,
    start: int,
    end: int,
    suggestions: list[dict[str, Any]],
    pattern_rules: list[dict[str, Any]],
) -> None:
    """Check and flag functions exceeding nesting depth threshold."""
    depth_rule = pattern_rules[2]
    depth = get_nesting_depth(node)
    if depth <= depth_rule["threshold"]:
        return
    suggestions.append(
        make_pattern(
            depth_rule,
            name=name,
            actual=depth,
            line_range=(start, end),
            priority_score=40 + depth * 5,
        )
    )


def _check_param_count(
    node: ast.AST,
    name: str,
    start: int,
    suggestions: list[dict[str, Any]],
    pattern_rules: list[dict[str, Any]],
) -> None:
    """Check and flag functions with too many parameters."""
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return
    param_rule = pattern_rules[3]
    params = (
        len(node.args.args)
        + len(node.args.kwonlyargs)
        + (1 if node.args.vararg else 0)
        + (1 if node.args.kwarg else 0)
    )
    if params <= param_rule["threshold"]:
        return
    suggestions.append(
        make_pattern(
            param_rule,
            name=name,
            actual=params,
            line_range=(start, start),
            priority_score=30,
        )
    )


def _check_static_extraction(
    node: ast.FunctionDef,
    name: str,
    start: int,
    end: int,
    suggestions: list[dict[str, Any]],
    extractable_patterns: list[dict[str, Any]],
) -> None:
    """Check and flag methods that do not use self or cls."""
    parent = getattr(node, "parent", None)
    if not isinstance(parent, ast.ClassDef):
        return
    if name.startswith("__") or _is_framework_hook(parent, name):
        return
    if not is_static_method(node):
        return
    suggestions.append(
        make_extraction(
            extractable_patterns[2],
            method=name,
            class_name=parent.name,
            line_range=(start, end),
            priority_score=25,
        )
    )


def _is_framework_hook(parent: ast.ClassDef, method_name: str) -> bool:
    """Return True for required framework hook methods that may not use self."""
    if method_name not in MCP_TOOL_HOOK_METHODS:
        return False
    return any(_base_name(base) == "BaseMCPTool" for base in parent.bases)


def _base_name(base: ast.expr) -> str:
    """Return the visible name for a class base expression."""
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return ""
