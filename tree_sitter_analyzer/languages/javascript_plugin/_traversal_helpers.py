"""Traversal helpers for JavaScript element extraction."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeAlias

from ...utils import log_debug, log_warning

if TYPE_CHECKING:
    import tree_sitter


ExtractorMap: TypeAlias = dict[str, Callable[["tree_sitter.Node"], Any]]
ElementCache: TypeAlias = dict[tuple[int, str], Any]


def traverse_and_extract_iterative(
    root_node: tree_sitter.Node | None,
    extractors: ExtractorMap,
    results: list[Any],
    element_type: str,
    processed_nodes: set[int],
    element_cache: ElementCache,
    max_depth: int = 50,
) -> None:
    """Iterative node traversal and extraction with caching."""
    if not root_node:
        return

    target_node_types = set(extractors.keys())
    container_node_types = _container_node_types()
    node_stack = [(root_node, 0)]
    processed_count = 0

    while node_stack:
        current_node, depth = node_stack.pop()

        if depth > max_depth:
            log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
            continue

        processed_count += 1
        node_type = current_node.type

        if _should_skip_node(depth, node_type, target_node_types, container_node_types):
            continue

        if node_type in target_node_types:
            skip_children = _process_target_node(
                current_node,
                extractors,
                results,
                element_type,
                processed_nodes,
                element_cache,
            )
            if skip_children:
                continue

        _extend_stack(current_node, depth, node_stack)

    log_debug(f"Iterative traversal processed {processed_count} nodes")


def _container_node_types() -> set[str]:
    return {
        "program",
        "class_body",
        "statement_block",
        "object",
        "class_declaration",
        "function_declaration",
        "method_definition",
        "export_statement",
        "variable_declaration",
        "lexical_declaration",
        "variable_declarator",
        "assignment_expression",
    }


def _should_skip_node(
    depth: int,
    node_type: str,
    target_node_types: set[str],
    container_node_types: set[str],
) -> bool:
    return (
        depth > 0
        and node_type not in target_node_types
        and node_type not in container_node_types
    )


def _process_target_node(
    current_node: tree_sitter.Node,
    extractors: ExtractorMap,
    results: list[Any],
    element_type: str,
    processed_nodes: set[int],
    element_cache: ElementCache,
) -> bool:
    node_id = id(current_node)

    if node_id in processed_nodes:
        return True

    cache_key = (node_id, element_type)
    if cache_key in element_cache:
        _append_element(results, element_cache[cache_key])
        processed_nodes.add(node_id)
        return True

    extractor = extractors.get(current_node.type)
    if extractor:
        element = extractor(current_node)
        element_cache[cache_key] = element
        _append_element(results, element)
        processed_nodes.add(node_id)

    return False


def _append_element(results: list[Any], element: Any) -> None:
    if not element:
        return
    if isinstance(element, list):
        results.extend(element)
    else:
        results.append(element)


def _extend_stack(
    current_node: tree_sitter.Node,
    depth: int,
    node_stack: list[tuple[tree_sitter.Node, int]],
) -> None:
    if current_node.children:
        for child in reversed(current_node.children):
            node_stack.append((child, depth + 1))
