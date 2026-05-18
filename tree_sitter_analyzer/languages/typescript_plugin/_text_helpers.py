"""Node text extraction helpers for the TypeScript extractor."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeAlias

from ...utils import log_debug, log_error

if TYPE_CHECKING:
    import tree_sitter


TextSliceExtractor: TypeAlias = Callable[[bytes, int, int, str], str]
SafeEncoder: TypeAlias = Callable[[str, str], bytes]


def get_node_text_optimized(
    node: tree_sitter.Node,
    content_lines: list[str],
    file_encoding: str | None,
    node_text_cache: dict[tuple[int, int], str],
    extract_text_slice_func: TextSliceExtractor,
    safe_encode_func: SafeEncoder,
) -> str:
    """Get node text with optimized caching using position-based keys."""
    cache_key = (node.start_byte, node.end_byte)
    if cache_key in node_text_cache:
        return node_text_cache[cache_key]

    try:
        text = _extract_from_encoded_content(
            node,
            content_lines,
            file_encoding,
            extract_text_slice_func,
            safe_encode_func,
        )
        node_text_cache[cache_key] = text
        return text
    except Exception as e:
        log_error(f"Error in _get_node_text_optimized: {e}")
        return _fallback_node_text(node, content_lines)


def _extract_from_encoded_content(
    node: tree_sitter.Node,
    content_lines: list[str],
    file_encoding: str | None,
    extract_text_slice_func: TextSliceExtractor,
    safe_encode_func: SafeEncoder,
) -> str:
    encoding = file_encoding or "utf-8"
    content_bytes = safe_encode_func("\n".join(content_lines), encoding)
    return extract_text_slice_func(
        content_bytes,
        node.start_byte,
        node.end_byte,
        encoding,
    )


def _fallback_node_text(node: tree_sitter.Node, content_lines: list[str]) -> str:
    try:
        start_point = node.start_point
        end_point = node.end_point

        if start_point[0] == end_point[0]:
            line = content_lines[start_point[0]]
            return str(line[start_point[1] : end_point[1]])

        return _fallback_multiline_text(start_point, end_point, content_lines)
    except Exception as fallback_error:
        log_error(f"Fallback text extraction also failed: {fallback_error}")
        return ""


def _fallback_multiline_text(
    start_point: tuple[int, int],
    end_point: tuple[int, int],
    content_lines: list[str],
) -> str:
    lines = []
    for line_index in range(start_point[0], end_point[0] + 1):
        if line_index < len(content_lines):
            lines.append(
                _slice_fallback_line(line_index, start_point, end_point, content_lines)
            )
    return "\n".join(lines)


def _slice_fallback_line(
    line_index: int,
    start_point: tuple[int, int],
    end_point: tuple[int, int],
    content_lines: list[str],
) -> str:
    line = content_lines[line_index]
    if line_index == start_point[0]:
        return line[start_point[1] :]
    if line_index == end_point[0]:
        return line[: end_point[1]]
    return line


_COMPLEXITY_KEYWORDS = (
    "if",
    "else if",
    "while",
    "for",
    "catch",
    "case",
    "switch",
    "&&",
    "||",
    "?",
)


def calculate_complexity(
    node: tree_sitter.Node,
    get_node_text: Callable[[tree_sitter.Node], str],
    cache: dict[int, int],
) -> int:
    """Calculate cyclomatic complexity for a node."""
    node_id = id(node)
    if node_id in cache:
        return cache[node_id]

    complexity = 1
    try:
        node_text = get_node_text(node).lower()
        for keyword in _COMPLEXITY_KEYWORDS:
            complexity += node_text.count(keyword)
    except Exception as e:
        log_debug(f"Failed to calculate complexity: {e}")

    cache[node_id] = complexity
    return complexity
