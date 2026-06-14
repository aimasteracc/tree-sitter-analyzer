"""C struct, union, and enum extraction helpers."""

from collections.abc import Callable
from typing import Any

from ..models import Class
from ..utils import log_debug
from ._c_comment_helpers import extract_comment_for_line


def extract_struct_definition(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Class | None:
    """Extract struct definition."""
    return _extract_type_definition(
        node, get_node_text, content_lines, "struct", "anonymous_struct", "struct"
    )


def extract_enum_definition(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Class | None:
    """Extract enum definition."""
    return _extract_type_definition(
        node, get_node_text, content_lines, "enum", "anonymous_enum", "enum"
    )


def _is_anonymous_nested_member(node: Any, get_node_text: Callable[..., str]) -> bool:
    """Return True when ``node`` is an anonymous container (struct/union/enum
    with no ``type_identifier`` child) that appears as a typed member inside
    another struct/union body via ``field_declaration``.

    These are *anonymous member containers* (e.g. ``union { int a; float b; }
    data;``).  They have no independent identity as a named type and must be
    skipped rather than emitted with a synthetic ``anonymous_union_N`` name
    (bug #753).  Named nested types (``struct Inner { int x; }``) DO have a
    ``type_identifier`` child and therefore return False.
    """
    # Must have no direct type name of its own.
    if _direct_type_name(node, get_node_text) is not None:
        return False
    # Must not be the primary type in a typedef (handled elsewhere).
    if node.parent and node.parent.type == "type_definition":
        return False
    # Must be the specifier inside a field_declaration (a struct/union member).
    return bool(node.parent and node.parent.type == "field_declaration")


def _extract_type_definition(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    class_type: str,
    anonymous_prefix: str,
    error_label: str,
) -> Class | None:
    try:
        # Skip anonymous containers that are just typed members of another
        # struct/union body — they have no meaningful type name and emitting
        # them with a synthetic ``anonymous_union_N`` name pollutes the class
        # list (bug #753).
        if _is_anonymous_nested_member(node, get_node_text):
            return None

        start_line, end_line = _node_line_range(node)
        name, start_line, end_line = _type_name_and_range(
            node, get_node_text, start_line, end_line, anonymous_prefix
        )
        return Class(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=_raw_text(content_lines, start_line, end_line),
            language="c",
            class_type=class_type,
            full_qualified_name=name,
            docstring=extract_comment_for_line(start_line, content_lines),
        )
    except Exception as e:
        log_debug(f"Failed to extract {error_label} info: {e}")
        return None


def _type_name_and_range(
    node: Any,
    get_node_text: Callable[..., str],
    start_line: int,
    end_line: int,
    anonymous_prefix: str,
) -> tuple[str, int, int]:
    name = _direct_type_name(node, get_node_text)
    if name:
        return name, start_line, end_line

    typedef_name = _typedef_type_name(node, get_node_text)
    if typedef_name:
        parent = node.parent
        return typedef_name, parent.start_point[0] + 1, parent.end_point[0] + 1

    return f"{anonymous_prefix}_{start_line}", start_line, end_line


def _direct_type_name(node: Any, get_node_text: Callable[..., str]) -> str | None:
    for child in node.children:
        if child.type == "type_identifier":
            return get_node_text(child)
    return None


def _typedef_type_name(node: Any, get_node_text: Callable[..., str]) -> str | None:
    if not node.parent or node.parent.type != "type_definition":
        return None
    for sibling in node.parent.children:
        if sibling.type == "type_identifier":
            return get_node_text(sibling)
    return None


def _node_line_range(node: Any) -> tuple[int, int]:
    return node.start_point[0] + 1, node.end_point[0] + 1


def _raw_text(content_lines: list[str], start_line: int, end_line: int) -> str:
    start_line_idx = max(0, start_line - 1)
    end_line_idx = min(len(content_lines), end_line)
    return "\n".join(content_lines[start_line_idx:end_line_idx])
