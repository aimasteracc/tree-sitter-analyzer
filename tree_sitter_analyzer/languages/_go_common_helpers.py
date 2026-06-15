"""Shared helpers for Go AST extraction."""

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

    Handles AST-level receiver extraction and strips trailing generic type
    parameters so type arguments are omitted. Pointer markers (``*``) are
    preserved so ``receiver_type`` remains a Go receiver type (for example,
    ``*Stack`` instead of ``Stack``).
    Bug #750.
    """
    receiver_node = node.child_by_field_name("receiver")
    if receiver_node is None:
        return None, None

    for child in receiver_node.children:
        if child.type != "parameter_declaration":
            continue
        return _extract_receiver_parts(child, get_node_text)

    # Unit tests use lightweight fake nodes that provide only `text`. Fall back to
    # tolerant text parsing in that shape so helper behavior remains testable
    # without constructing a full tree-sitter parameter node.
    return _extract_receiver_from_text(get_node_text(receiver_node))


def _extract_receiver_parts(
    parameter_node: Any, get_node_text: Callable[..., str]
) -> tuple[str | None, str | None]:
    """Extract ``(name, normalized_type)`` from a Go ``parameter_declaration``."""
    receiver_name = None
    receiver_type = None

    for child in parameter_node.children:
        if child.type == "identifier" and receiver_name is None:
            receiver_name = get_node_text(child)
            continue
        if child.type in (
            "type_identifier",
            "generic_type",
            "pointer_type",
            "qualified_type",
        ):
            receiver_type = _strip_generic_suffix(get_node_text(child))
            break

    if receiver_type is None:
        return None, None
    return receiver_name, receiver_type


def _extract_receiver_from_text(receiver_text: str) -> tuple[str | None, str | None]:
    """Parse a raw receiver tuple text like ``(p *Stack[T])``."""
    text = (receiver_text or "").strip()
    if not text:
        return None, None
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    if not text:
        return None, None

    depth = 0
    for idx, ch in enumerate(text):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(depth - 1, 0)
        elif depth == 0 and ch.isspace():
            name = text[:idx].strip()
            tail = text[idx:].strip()
            if not name:
                break
            return name, _strip_generic_suffix(tail)

    return None, _strip_generic_suffix(text)


def _strip_generic_suffix(receiver_type: str) -> str | None:
    """Strip trailing Go type arguments like ``[T]`` or ``[A, B]``."""
    text = (receiver_type or "").strip()
    if not text or "[" not in text:
        return text or None

    idx = len(text) - 1
    while idx >= 0 and text[idx].isspace():
        idx -= 1
    if idx < 0 or text[idx] != "]":
        return text or None

    depth = 0
    start = None
    for i in range(idx, -1, -1):
        if text[i] == "]":
            depth += 1
        elif text[i] == "[":
            depth -= 1
            if depth == 0:
                start = i
                break
    if start is None:
        return text or None

    base = text[:start].rstrip()
    return base or None


def go_visibility(name: str) -> str:
    return "public" if name[0].isupper() else "private"
