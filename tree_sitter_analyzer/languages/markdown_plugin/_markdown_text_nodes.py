"""Shared Markdown AST text iteration helpers."""

from collections.abc import Callable, Iterator
from typing import Any

from ...utils import log_debug


def _iter_node_text(
    root_node: Any,
    node_type: str,
    get_node_text: Callable[..., str],
    traverse_nodes: Callable[..., Iterator[Any]],
    failure_message: str,
) -> Iterator[tuple[Any, str]]:
    """Yield non-empty text for nodes of a requested type."""
    for node in traverse_nodes(root_node):
        if node.type != node_type:
            continue
        try:
            raw_text = get_node_text(node)
        except Exception as e:
            log_debug(f"{failure_message}: {e}")
            continue
        if raw_text:
            yield node, raw_text
