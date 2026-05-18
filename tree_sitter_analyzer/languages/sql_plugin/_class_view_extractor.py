"""Class-level SQL view extraction helpers."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import Class
from ...utils import log_debug

_RESERVED_VIEW_NAMES = {
    "SELECT",
    "FROM",
    "WHERE",
    "AS",
    "IF",
    "NOT",
    "EXISTS",
    "NULL",
    "CURRENT_TIMESTAMP",
    "NOW",
    "SYSDATE",
}


def extract_class_views(
    root_node: tree_sitter.Node,
    classes: list[Class],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    is_valid_identifier: Callable[[str], bool],
    source_code: str,
    content_lines: list[str],
) -> None:
    """Extract CREATE VIEW statements as generic Class elements."""
    for node in traverse_nodes(root_node):
        if node.type != "create_view":
            continue
        _append_class_view(
            node,
            classes,
            get_node_text,
            is_valid_identifier,
            source_code,
            content_lines,
        )


def _append_class_view(
    node: tree_sitter.Node,
    classes: list[Class],
    get_node_text: Callable[..., str],
    is_valid_identifier: Callable[[str], bool],
    source_code: str,
    content_lines: list[str],
) -> None:
    """Append one view Class when a valid view name can be extracted."""
    raw_text = get_node_text(node)
    view_name = _view_name(raw_text, node, get_node_text, is_valid_identifier)
    if not view_name:
        return

    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        raw_text, end_line = _recover_single_line_view_span(
            raw_text,
            start_line,
            end_line,
            view_name,
            source_code,
            content_lines,
        )
        classes.append(
            Class(
                name=view_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="sql",
            )
        )
    except Exception as e:
        log_debug(f"Failed to extract view: {e}")


def _view_name(
    raw_text: str,
    node: tree_sitter.Node,
    get_node_text: Callable[..., str],
    is_valid_identifier: Callable[[str], bool],
) -> str | None:
    """Return a valid view name from text first, then AST children."""
    from_text = _view_name_from_text(raw_text, is_valid_identifier)
    if from_text:
        return from_text
    return _view_name_from_children(node, get_node_text, is_valid_identifier)


def _view_name_from_text(
    raw_text: str,
    is_valid_identifier: Callable[[str], bool],
) -> str | None:
    """Extract a view name using SQL text."""
    if not raw_text:
        return None
    view_match = re.search(
        r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
        raw_text,
        re.IGNORECASE,
    )
    if not view_match:
        return None
    potential_name = view_match.group(1).strip()
    return potential_name if is_valid_identifier(potential_name) else None


def _view_name_from_children(
    node: tree_sitter.Node,
    get_node_text: Callable[..., str],
    is_valid_identifier: Callable[[str], bool],
) -> str | None:
    """Extract a view name from object_reference children."""
    for child in node.children:
        if child.type != "object_reference":
            continue
        for subchild in child.children:
            if subchild.type != "identifier":
                continue
            potential_name = get_node_text(subchild).strip()
            if _is_valid_view_identifier(potential_name, is_valid_identifier):
                return potential_name
    return None


def _is_valid_view_identifier(
    potential_name: str,
    is_valid_identifier: Callable[[str], bool],
) -> bool:
    """Return whether an AST identifier is a plausible view name."""
    return (
        bool(potential_name)
        and is_valid_identifier(potential_name)
        and potential_name.upper() not in _RESERVED_VIEW_NAMES
    )


def _recover_single_line_view_span(
    raw_text: str,
    start_line: int,
    end_line: int,
    view_name: str,
    source_code: str,
    content_lines: list[str],
) -> tuple[str, int]:
    """Recover full multiline view text when tree-sitter reports one line."""
    if start_line != end_line or not source_code:
        return raw_text, end_line

    current_line_idx = start_line - 1
    recovered_end_line = _find_view_statement_end(current_line_idx, content_lines)
    if recovered_end_line and recovered_end_line > start_line:
        recovered_text = "\n".join(content_lines[current_line_idx:recovered_end_line])
        log_debug(
            f"Corrected view span for {view_name}: {start_line}-{recovered_end_line}"
        )
        return recovered_text, recovered_end_line
    return raw_text, end_line


def _find_view_statement_end(
    current_line_idx: int,
    content_lines: list[str],
) -> int | None:
    """Find the inclusive SQL view statement end line number."""
    for i in range(current_line_idx, len(content_lines)):
        if ";" in content_lines[i]:
            return i + 1

    for i in range(
        current_line_idx + 1, min(len(content_lines), current_line_idx + 50)
    ):
        line = content_lines[i].strip()
        if not line or line.upper().startswith("CREATE "):
            return i
    return None
