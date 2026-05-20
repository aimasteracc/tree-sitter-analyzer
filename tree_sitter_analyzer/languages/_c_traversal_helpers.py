"""C AST traversal helpers."""

from typing import Any

from ..utils import log_debug, log_warning

_C_CONTAINER_NODE_TYPES = frozenset(
    {
        "translation_unit",
        "compound_statement",
        "struct_specifier",
        "union_specifier",
        "field_declaration_list",
        "declaration_list",
        "type_definition",
        # Preprocessor conditional branches — without these the traversal
        # stops at ``#ifdef`` / ``#if`` boundaries and silently skips every
        # macro definition (and any other declaration) inside them. See
        # ``examples/sample.c`` lines 14–18 (the ``LOG(msg)`` macros).
        # tree-sitter-c uses ``preproc_ifdef`` for both ``#ifdef`` and
        # ``#ifndef``; ``preproc_else``/``preproc_elif`` are nested
        # under their parent conditional.
        "preproc_if",
        "preproc_ifdef",
        "preproc_else",
        "preproc_elif",
    }
)


def c_traverse_and_extract(
    root_node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    element_type: str,
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> None:
    """Iterative node traversal and extraction with caching for C."""
    if root_node is None:
        return

    target_node_types = set(extractors.keys())
    node_stack = [(root_node, 0)]
    processed_count = 0
    max_depth = 50

    while node_stack:
        current_node, depth = node_stack.pop()
        if _depth_exceeded(depth, max_depth):
            continue

        processed_count += 1
        if not _should_visit_node(current_node, depth, target_node_types):
            continue

        if current_node.type in target_node_types:
            should_visit_children = _process_target_node(
                current_node,
                extractors,
                results,
                element_type,
                processed_nodes,
                element_cache,
            )
            if not should_visit_children:
                continue

        _push_children(node_stack, current_node, depth)

    log_debug(f"Iterative traversal processed {processed_count} nodes")


def _depth_exceeded(depth: int, max_depth: int) -> bool:
    if depth > max_depth:
        log_warning(f"Maximum traversal depth ({max_depth}) exceeded")
        return True
    return False


def _should_visit_node(node: Any, depth: int, target_node_types: set[str]) -> bool:
    if depth == 0:
        return True
    return node.type in target_node_types or node.type in _C_CONTAINER_NODE_TYPES


def _process_target_node(
    node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    element_type: str,
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> bool:
    node_id = id(node)
    if node_id in processed_nodes:
        return False

    cache_key = (node_id, element_type)
    if cache_key in element_cache:
        _append_extracted_element(results, element_cache[cache_key])
        processed_nodes.add(node_id)
        return False

    element = extractors[node.type](node)
    element_cache[cache_key] = element
    _append_extracted_element(results, element)
    processed_nodes.add(node_id)
    return True


def _append_extracted_element(results: list[Any], element: Any) -> None:
    if not element:
        return
    if isinstance(element, list):
        results.extend(element)
    else:
        results.append(element)


def _push_children(node_stack: list[tuple[Any, int]], node: Any, depth: int) -> None:
    if not node.children:
        return
    for child in reversed(node.children):
        node_stack.append((child, depth + 1))
