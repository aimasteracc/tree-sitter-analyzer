"""SQL schema reference extraction helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import Import
from ...utils import log_debug


def extract_schema_references(
    root_node: tree_sitter.Node,
    imports: list[Import],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
) -> None:
    """Extract schema.table references as generic Import elements."""
    for node in traverse_nodes(root_node):
        if node.type != "qualified_name":
            continue
        _append_schema_reference(node, imports, get_node_text)


def _append_schema_reference(
    node: tree_sitter.Node,
    imports: list[Import],
    get_node_text: Callable[..., str],
) -> None:
    """Append one schema reference when text has exactly two dotted parts."""
    text = get_node_text(node)
    if "." not in text or len(text.split(".")) != 2:
        return

    try:
        imports.append(
            Import(
                name=text,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=text,
                language="sql",
            )
        )
    except Exception as e:
        log_debug(f"Failed to extract schema reference: {e}")
