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
    # Modern Java support (2026-09-01): containers for new syntax constructs.
    # Ensures lambda, anonymous_class, static_initializer, and related nodes
    # are reachable and their inner elements are extractable.
    "compact_constructor_declaration",
    "static_initializer",
    "instance_initializer",
    "switch_block",
    "switch_block_statement_group",
    "try_with_resources_statement",
    "lambda_expression",
    "object_creation_expression",
    "anonymous_class_body",
    "module_declaration",
    "module_body",
    # C-1 (2026-09-01): intermediate containers needed to reach
    # object_creation_expression from field/local-variable declarations.
    # Without these, the cursor never descends into anonymous class bodies
    # created in field initialisers or local-variable assignments.
    "field_declaration",
    "local_variable_declaration",
    "variable_declarator",
    "expression_statement",
    "assignment_expression",
    "return_statement",
    "argument_list",
}


def java_traverse_and_extract(
    root_node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    element_type: str,
    processed_nodes: set[tuple[int, int]],
    element_cache: dict[tuple[tuple[int, int], str], Any],
    *,
    log_warning_func: Callable[[str], None],
    log_debug_func: Callable[[str], None],
) -> None:
    """Cursor-based node traversal and extraction with batch field processing.

    Uses tree-sitter's TreeCursor API (node.walk() / goto_first_child /
    goto_next_sibling / goto_parent) instead of a manual node_stack so that
    node identity is stable across traversal.  Only container nodes (listed in
    ``_JAVA_CONTAINER_NODES``) are descended into; all other nodes are visited
    for extraction but not explored further.

    Node identity key: ``(node.start_byte, node.end_byte)`` — unique and stable
    after Cursor movement, unlike ``id(node)`` which may alias across moves.
    """
    if not root_node:
        return

    target_node_types = set(extractors.keys())
    field_batch: list[Any] = []
    processed_count = 0

    cursor = root_node.walk()
    reached_root = False

    while not reached_root:
        current_node = cursor.node
        processed_count += 1

        # Process matched target nodes
        if current_node.type in target_node_types:
            _process_matched_node(
                current_node,
                extractors,
                results,
                element_type,
                processed_nodes,
                element_cache,
                field_batch,
            )

        # Descend into container nodes (and always descend into the root)
        should_descend = (
            current_node == root_node or current_node.type in _JAVA_CONTAINER_NODES
        )
        if should_descend and cursor.goto_first_child():
            continue

        # Move to next sibling at the same level
        if cursor.goto_next_sibling():
            continue

        # Backtrack: climb until we can move to a next sibling or exhaust the tree
        retracing = True
        while retracing:
            if not cursor.goto_parent():
                retracing = False
                reached_root = True
            elif cursor.node == root_node:
                retracing = False
                reached_root = True
            elif cursor.goto_next_sibling():
                retracing = False

    _flush_field_batch(field_batch, extractors, results, processed_nodes, element_cache)
    log_debug_func(f"Cursor traversal processed {processed_count} nodes")


def _process_matched_node(
    node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    element_type: str,
    processed_nodes: set[tuple[int, int]],
    element_cache: dict[tuple[tuple[int, int], str], Any],
    field_batch: list[Any],
) -> None:
    if element_type == "field" and node.type == "field_declaration":
        field_batch.append(node)
        return

    node_id = (node.start_byte, node.end_byte)
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


def _flush_field_batch_if_ready(
    field_batch: list[Any],
    extractors: dict[str, Any],
    results: list[Any],
    processed_nodes: set[tuple[int, int]],
    element_cache: dict[tuple[tuple[int, int], str], Any],
) -> None:
    if len(field_batch) < 10:
        return
    _flush_field_batch(field_batch, extractors, results, processed_nodes, element_cache)


def _flush_field_batch(
    field_batch: list[Any],
    extractors: dict[str, Any],
    results: list[Any],
    processed_nodes: set[tuple[int, int]],
    element_cache: dict[tuple[tuple[int, int], str], Any],
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
    processed_nodes: set[tuple[int, int]],
    element_cache: dict[tuple[tuple[int, int], str], Any],
) -> None:
    """Process field nodes with caching."""
    for node in batch:
        _process_field_node(node, extractors, results, processed_nodes, element_cache)


def _process_field_node(
    node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    processed_nodes: set[tuple[int, int]],
    element_cache: dict[tuple[tuple[int, int], str], Any],
) -> None:
    node_id = (node.start_byte, node.end_byte)
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
