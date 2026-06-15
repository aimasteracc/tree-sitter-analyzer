"""Class-level SQL table extraction helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import Class
from ...utils import log_debug


def extract_class_tables(
    root_node: tree_sitter.Node,
    classes: list[Class],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    is_valid_identifier: Callable[[str], bool],
) -> None:
    """Extract CREATE TABLE statements as generic Class elements."""
    for node in traverse_nodes(root_node):
        if node.type != "create_table":
            continue
        _append_class_table(node, classes, get_node_text, is_valid_identifier)


def _append_class_table(
    node: tree_sitter.Node,
    classes: list[Class],
    get_node_text: Callable[..., str],
    is_valid_identifier: Callable[[str], bool],
) -> None:
    """Append one table Class when a valid table name can be extracted."""
    table_name = _table_name_from_children(node, get_node_text, is_valid_identifier)
    if not table_name:
        return

    try:
        classes.append(
            Class(
                name=table_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=get_node_text(node),
                language="sql",
            )
        )
    except Exception as e:
        log_debug(f"Failed to extract table: {e}")


def _table_name_from_children(
    node: tree_sitter.Node,
    get_node_text: Callable[..., str],
    is_valid_identifier: Callable[[str], bool],
) -> str | None:
    """Extract a table name from object_reference children.

    For ``schema.table`` patterns the LAST identifier is the table name.
    """
    for child in node.children:
        if child.type != "object_reference":
            continue
        table_name = _last_identifier_from_object_reference(
            child,
            get_node_text,
            is_valid_identifier,
        )
        if table_name:
            return table_name
    return None


def _last_identifier_from_object_reference(
    node: tree_sitter.Node,
    get_node_text: Callable[..., str],
    is_valid_identifier: Callable[[str], bool],
) -> str | None:
    """Extract the LAST valid identifier from an object_reference node.

    For a plain ``tablename`` reference there is one identifier child.
    For a ``schema.tablename`` reference there are two; we return the last.
    """
    valid = [
        get_node_text(subchild).strip()
        for subchild in node.children
        if subchild.type == "identifier"
        and get_node_text(subchild).strip()
        and is_valid_identifier(get_node_text(subchild).strip())
    ]
    return valid[-1] if valid else None
