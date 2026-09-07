"""Java AST 游标遍历辅助函数。"""

from collections.abc import Callable
from typing import Any


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
    """用 TreeCursor 遍历所有 named 后代，并批量处理字段。

    不按语法容器白名单剪枝，避免遗漏任意表达式或控制流中的声明。
    缓存仍以字节范围为键，不依赖游标移动时临时 Node 对象的身份。
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

        # PR #1350：只跳过匿名标点的内部，不截断任何 named 子树。
        should_descend = current_node == root_node or current_node.is_named
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
