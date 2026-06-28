"""C++ iterative traversal helpers."""

from dataclasses import dataclass
from typing import Any

from ..utils import log_debug, log_warning

_CONTAINER_NODE_TYPES = frozenset(
    {
        "translation_unit",
        "namespace_definition",
        "class_specifier",
        "struct_specifier",
        "union_specifier",
        "declaration_list",
        "field_declaration_list",
        # field_declaration is required so that nested class/struct/union types
        # declared as members of a class body are reachable.  Without it, the
        # traversal stops at field_declaration_list children and never descends
        # into member declarations that contain a type specifier (bug #751).
        "field_declaration",
        "compound_statement",
        "template_declaration",
        "declaration",
    }
)


@dataclass
class CppTraversalState:
    extractors: dict[str, Any]
    results: list[Any]
    element_type: str
    processed_nodes: set[int]
    element_cache: dict[tuple[int, str], Any]


def traverse_and_extract_iterative(
    root_node: Any,
    state: CppTraversalState | dict[str, Any],
    *legacy_args: Any,
) -> None:
    """Iterative node traversal and extraction with caching."""
    if root_node is None:
        return

    ctx = _traversal_state(state, *legacy_args)
    target_node_types = set(ctx.extractors.keys())
    node_stack = [(root_node, 0)]
    processed_count = 0
    max_depth = 50

    while node_stack:
        current_node, depth = node_stack.pop()
        if depth > max_depth:
            log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
            continue

        processed_count += 1
        if _should_skip_node(current_node, depth, target_node_types):
            continue

        if current_node.type in target_node_types:
            _extract_node(current_node, ctx)

        node_stack.extend(
            (child, depth + 1) for child in reversed(current_node.children or [])
        )

    log_debug(f"Iterative traversal processed {processed_count} nodes")


def _should_skip_node(node: Any, depth: int, target_node_types: set[str]) -> bool:
    return (
        depth > 0
        and node.type not in target_node_types
        and node.type not in _CONTAINER_NODE_TYPES
    )


def _extract_node(
    node: Any,
    state: CppTraversalState,
) -> None:
    node_id = id(node)
    if node_id in state.processed_nodes:
        return

    cache_key = (node_id, state.element_type)
    if cache_key in state.element_cache:
        _append_extracted(state.results, state.element_cache[cache_key])
        state.processed_nodes.add(node_id)
        return

    element = state.extractors[node.type](node)
    state.element_cache[cache_key] = element
    _append_extracted(state.results, element)
    state.processed_nodes.add(node_id)


def _traversal_state(
    state: CppTraversalState | dict[str, Any],
    *legacy_args: Any,
) -> CppTraversalState:
    if isinstance(state, CppTraversalState):
        return state
    if len(legacy_args) != 4:
        raise TypeError("Expected CppTraversalState or legacy traversal arguments")
    return CppTraversalState(
        extractors=state,
        results=legacy_args[0],
        element_type=legacy_args[1],
        processed_nodes=legacy_args[2],
        element_cache=legacy_args[3],
    )


def _append_extracted(results: list[Any], element: Any) -> None:
    if not element:
        return
    if isinstance(element, list):
        results.extend(element)
    else:
        results.append(element)
