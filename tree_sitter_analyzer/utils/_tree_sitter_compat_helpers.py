"""Private helpers for tree-sitter compatibility shims."""

import logging
from typing import Any

logger = logging.getLogger("tree_sitter_analyzer.utils.tree_sitter_compat")


def execute_query_compat(
    language: Any, query_string: str, root_node: Any
) -> list[tuple[Any, str]]:
    try:
        import tree_sitter

        query = tree_sitter.Query(language, query_string)
        return execute_query_object(tree_sitter, query, root_node)
    except Exception as e:
        logger.error(f"Tree-sitter query execution failed: {e}")
        logger.debug("Returning empty result due to query execution failure")
        return []


def execute_query_object(
    tree_sitter_module: Any, query: Any, root_node: Any
) -> list[tuple[Any, str]]:
    if hasattr(tree_sitter_module, "QueryCursor"):
        logger.debug("Using newest tree-sitter API (QueryCursor)")
        return execute_newest_api(query, root_node)
    if hasattr(query, "matches"):
        logger.debug("Using modern tree-sitter API (matches)")
        return execute_modern_api(query, root_node)
    if hasattr(query, "captures"):
        logger.debug("Using legacy tree-sitter API (captures)")
        return execute_legacy_api(query, root_node)
    logger.debug("Using very old tree-sitter API (direct query)")
    return execute_old_api(query, root_node)


def execute_newest_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
    captures: list[tuple[Any, str]] = []
    try:
        import tree_sitter

        cursor = tree_sitter.QueryCursor(query)
        matches = cursor.matches(root_node)
        for _pattern_index, captures_dict in matches:
            captures.extend(
                (node, capture_name)
                for capture_name, nodes in captures_dict.items()
                for node in nodes
            )
    except Exception as e:
        logger.error(f"Newest API execution failed: {e}")
    return captures


def execute_modern_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
    captures: list[tuple[Any, str]] = []
    try:
        matches = query.matches(root_node)
        for match in matches:
            captures.extend(
                (capture.node, query.capture_names[capture.index])
                for capture in match.captures
            )
    except Exception as e:
        logger.error(f"Modern API execution failed: {e}")
        raise
    return captures


def execute_legacy_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
    try:
        return [
            (node, capture_name) for node, capture_name in query.captures(root_node)
        ]
    except Exception as e:
        logger.error(f"Legacy API execution failed: {e}")
        raise


def old_api_capture_from_item(item: Any) -> tuple[Any, str] | None:
    if isinstance(item, tuple) and len(item) >= 2:
        return item[0], str(item[1])
    if hasattr(item, "node") and hasattr(item, "name"):
        return item.node, item.name
    return None


def old_api_captures_from_result(query_result: Any) -> list[tuple[Any, str]]:
    if not isinstance(query_result, list):
        return []
    captures = []
    for item in query_result:
        capture = old_api_capture_from_item(item)
        if capture is not None:
            captures.append(capture)
    return captures


def execute_old_api(query: Any, root_node: Any) -> list[tuple[Any, str]]:
    try:
        if not callable(query):
            logger.warning(
                "No compatible tree-sitter query API found, returning empty result"
            )
            return []
        return old_api_captures_from_result(query(root_node))
    except Exception as e:
        logger.error(f"Old API execution failed: {e}")
        return []


def get_node_text_by_bytes(node: Any, source_code: str, encoding: str) -> str | None:
    if not (hasattr(node, "start_byte") and hasattr(node, "end_byte")):
        return None

    start_byte = node.start_byte
    end_byte = node.end_byte
    source_bytes = source_code.encode(encoding)
    if start_byte <= end_byte <= len(source_bytes):
        return source_bytes[start_byte:end_byte].decode(encoding, errors="replace")
    return None


def get_node_text_attribute(node: Any, encoding: str) -> str | None:
    text = getattr(node, "text", None)
    if not text:
        return None
    if isinstance(text, bytes):
        return text.decode(encoding, errors="replace")
    return str(text)


def get_single_line_text(line: str, start_column: int, end_column: int) -> str:
    start_col = max(0, min(start_column, len(line)))
    end_col = max(start_col, min(end_column, len(line)))
    return str(line[start_col:end_col])


def get_multi_line_text(
    lines: list[str], start_point: tuple[int, int], end_point: tuple[int, int]
) -> str:
    result_lines = []
    for line_index in range(start_point[0], min(end_point[0] + 1, len(lines))):
        line = lines[line_index]
        if line_index == start_point[0]:
            start_col = max(0, min(start_point[1], len(line)))
            result_lines.append(line[start_col:])
        elif line_index == end_point[0]:
            end_col = max(0, min(end_point[1], len(line)))
            result_lines.append(line[:end_col])
        else:
            result_lines.append(line)
    return "\n".join(result_lines)


def get_node_text_by_points(node: Any, source_code: str) -> str | None:
    if not (hasattr(node, "start_point") and hasattr(node, "end_point")):
        return None

    start_point = node.start_point
    end_point = node.end_point
    lines = source_code.split("\n")
    if start_point[0] >= len(lines) or end_point[0] >= len(lines):
        return None
    if start_point[0] == end_point[0]:
        return get_single_line_text(lines[start_point[0]], start_point[1], end_point[1])
    return get_multi_line_text(lines, start_point, end_point)


def get_node_text_compat(node: Any, source_code: str, encoding: str) -> str:
    text = get_node_text_by_bytes(node, source_code, encoding)
    if text is not None:
        return text

    text = get_node_text_attribute(node, encoding)
    if text is not None:
        return text

    text = get_node_text_by_points(node, source_code)
    if text is not None:
        return text

    return ""
