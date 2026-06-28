"""Java AST traversal helpers."""

from collections.abc import Callable
from typing import Any

_JAVA_CONTAINER_NODES = {
    "program",
    "class_body",
    "interface_body",
    "enum_body",
    "enum_body_declarations",
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    # Theme-I (2026-06-10): descend into records and annotation types so
    # their members (e.g. a record's methods) are reachable. A record's body
    # is a plain ``class_body``; annotation types use ``annotation_type_body``.
    "record_declaration",
    "annotation_type_declaration",
    "annotation_type_body",
    "method_declaration",
    "constructor_declaration",
    "block",
    "modifiers",
}


def java_traverse_and_extract(
    root_node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    element_type: str,
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
    *,
    log_warning_func: Callable[[str], None],
    log_debug_func: Callable[[str], None],
) -> None:
    """Iterative node traversal and extraction with batch field processing."""
    if not root_node:
        return

    target_node_types, max_depth = set(extractors.keys()), 50
    node_stack: list[tuple[Any, int]]
    field_batch: list[Any]
    node_stack, field_batch = [(root_node, 0)], []
    processed_count = 0

    while node_stack:
        current_node, depth = node_stack.pop()

        if depth > max_depth:
            log_warning_func(f"Maximum traversal depth ({max_depth}) exceeded")
            continue

        processed_count += 1
        node_type = current_node.type
        if _should_skip_node(depth, node_type, target_node_types):
            continue

        if node_type in target_node_types:
            _process_matched_node(
                current_node,
                extractors,
                results,
                element_type,
                processed_nodes,
                element_cache,
                field_batch,
            )

        _push_children(node_stack, current_node, depth)
        _flush_field_batch_if_ready(
            field_batch, extractors, results, processed_nodes, element_cache
        )

    _flush_field_batch(field_batch, extractors, results, processed_nodes, element_cache)
    log_debug_func(f"Iterative traversal processed {processed_count} nodes")


def _should_skip_node(depth: int, node_type: str, target_node_types: set[str]) -> bool:
    return (
        depth > 0
        and node_type not in target_node_types
        and node_type not in _JAVA_CONTAINER_NODES
    )


def _process_matched_node(
    node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    element_type: str,
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
    field_batch: list[Any],
) -> None:
    if element_type == "field" and node.type == "field_declaration":
        field_batch.append(node)
        return

    node_id = id(node)
    if node_id in processed_nodes:
        return

    cache_key = (node_id, element_type)
    if cache_key in element_cache:
        _append_element(results, element_cache[cache_key])
        processed_nodes.add(node_id)
        return

    extractor = extractors.get(node.type)
    if not extractor:
        return

    element = extractor(node)
    element_cache[cache_key] = element
    _append_element(results, element)
    processed_nodes.add(node_id)


def _append_element(results: list[Any], element: Any) -> None:
    if not element:
        return
    if isinstance(element, list):
        results.extend(element)
        return
    results.append(element)


def _push_children(
    node_stack: list[tuple[Any, int]], current_node: Any, depth: int
) -> None:
    if not current_node.children:
        return
    for child in reversed(current_node.children):
        node_stack.append((child, depth + 1))


def _flush_field_batch_if_ready(
    field_batch: list[Any],
    extractors: dict[str, Any],
    results: list[Any],
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> None:
    if len(field_batch) < 10:
        return
    _flush_field_batch(field_batch, extractors, results, processed_nodes, element_cache)


def _flush_field_batch(
    field_batch: list[Any],
    extractors: dict[str, Any],
    results: list[Any],
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> None:
    if not field_batch:
        return
    _process_field_batch(
        field_batch, extractors, results, processed_nodes, element_cache
    )
    field_batch.clear()


def _process_field_batch(
    batch: list[Any],
    extractors: dict[str, Any],
    results: list[Any],
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> None:
    """Process field nodes with caching."""
    for node in batch:
        _process_field_node(node, extractors, results, processed_nodes, element_cache)


def _process_field_node(
    node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> None:
    node_id = id(node)
    if node_id in processed_nodes:
        return

    cache_key = (node_id, "field")
    if cache_key in element_cache:
        _append_element(results, element_cache[cache_key])
        processed_nodes.add(node_id)
        return

    extractor = extractors.get(node.type)
    if not extractor:
        return

    elements = extractor(node)
    element_cache[cache_key] = elements
    _append_element(results, elements)
    processed_nodes.add(node_id)
