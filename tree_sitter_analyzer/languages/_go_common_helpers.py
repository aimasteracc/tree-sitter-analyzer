"""Shared helpers for Go AST extraction."""

import re
from collections.abc import Callable
from typing import Any


def extract_parameters(node: Any, get_node_text: Callable[..., str]) -> list[str]:
    """Extract function/method parameters.

    Theme E (2026-06-10): also capture ``variadic_parameter_declaration``
    nodes (e.g. ``numbers ...int``) which were previously silently dropped.
    """
    parameters: list[str] = []
    params_node = node.child_by_field_name("parameters")
    if params_node:
        for child in params_node.children:
            if child.type in (
                "parameter_declaration",
                "variadic_parameter_declaration",
            ):
                parameters.append(get_node_text(child))
    return parameters


def extract_return_type(node: Any, get_node_text: Callable[..., str]) -> str:
    """Extract function/method return type."""
    result_node = node.child_by_field_name("result")
    if result_node:
        return get_node_text(result_node)
    return ""


def extract_docstring(node: Any, content_lines: list[str]) -> str | None:
    """Extract doc comments preceding the node."""
    scan_start = _docstring_scan_start(node, content_lines)
    if scan_start is None:
        return None

    docs = _collect_docstring_lines(content_lines, scan_start)
    return "\n".join(docs) if docs else None


def _docstring_scan_start(node: Any, content_lines: list[str]) -> int | None:
    start_line = node.start_point[0]
    if start_line == 0:
        return None
    return min(start_line - 1, len(content_lines) - 1)


def _collect_docstring_lines(content_lines: list[str], scan_start: int) -> list[str]:
    docs: list[str] = []
    for line_idx in range(scan_start, -1, -1):
        line = content_lines[line_idx].strip()
        if line.startswith("//"):
            docs.insert(0, line[2:].strip())
            continue
        if line:
            break
    return docs


def extract_method_receiver(
    node: Any, get_node_text: Callable[..., str]
) -> tuple[str | None, str | None]:
    """Extract method receiver name and type.

    Handles generic receivers such as ``(s *Stack[T])`` or ``(p Pair[A, B])``.
    The type-parameter suffix ``[...]`` is stripped so that ``receiver_type``
    returns the bare type name (e.g. ``"*Stack"`` instead of ``"*Stack[T]"``).
    Bug #750.
    """
    receiver_node = node.child_by_field_name("receiver")
    if receiver_node:
        receiver_text = get_node_text(receiver_node)
        # Match: open-paren, receiver-var, receiver-type (optional pointer),
        # optional generic type-param list ``[...]``, close-paren.
        match = re.search(r"\(\s*(\w+)\s+(\*?\w+)(?:\[.*?\])?\s*\)", receiver_text)
        if match:
            return match.group(1), match.group(2)
    return None, None


def go_visibility(name: str) -> str:
    return "public" if name[0].isupper() else "private"
