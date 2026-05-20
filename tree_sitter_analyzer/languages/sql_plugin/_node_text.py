"""Tree-sitter node text extraction helpers for SQL."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...encoding_utils import extract_text_slice, safe_encode
from ...utils import log_debug

if TYPE_CHECKING:
    import tree_sitter


NodeTextCache = dict[tuple[int, int], str]


def get_node_text(
    node: tree_sitter.Node,
    content_lines: list[str],
    node_text_cache: NodeTextCache,
    file_encoding: str | None,
) -> str:
    """Return cached node text, falling back from byte offsets to point slices."""
    cache_key = (node.start_byte, node.end_byte)
    if cache_key in node_text_cache:
        return node_text_cache[cache_key]

    text = _extract_by_bytes(node, content_lines, file_encoding or "utf-8")
    if text:
        node_text_cache[cache_key] = text
        return text

    return _extract_by_points(node, content_lines, node_text_cache, cache_key)


def _extract_by_bytes(
    node: tree_sitter.Node,
    content_lines: list[str],
    encoding: str,
) -> str:
    """Extract node text with tree-sitter byte offsets."""
    try:
        content_bytes = safe_encode("\n".join(content_lines), encoding)
        return extract_text_slice(
            content_bytes,
            node.start_byte,
            node.end_byte,
            encoding,
        )
    except Exception as e:
        log_debug(f"Error in _get_node_text: {e}")
        return ""


def _extract_by_points(
    node: tree_sitter.Node,
    content_lines: list[str],
    node_text_cache: NodeTextCache,
    cache_key: tuple[int, int],
) -> str:
    """Extract node text with tree-sitter point coordinates."""
    try:
        start_point = node.start_point
        end_point = node.end_point

        if not _line_in_bounds(start_point[0], content_lines):
            return ""
        if not _line_in_bounds(end_point[0], content_lines):
            return ""

        if start_point[0] == end_point[0]:
            result = _slice_single_line(
                content_lines[start_point[0]],
                start_point[1],
                end_point[1],
            )
        else:
            result = "\n".join(
                _slice_multiline_node_text(start_point, end_point, content_lines)
            )

        node_text_cache[cache_key] = result
        return result
    except Exception as fallback_error:
        log_debug(f"Fallback text extraction also failed: {fallback_error}")
        return ""


def _line_in_bounds(line_number: int, content_lines: list[str]) -> bool:
    """Return whether a point line index is readable."""
    return 0 <= line_number < len(content_lines)


def _slice_single_line(line: str, start_col: int, end_col: int) -> str:
    """Return a bounded slice from one line."""
    start = max(0, min(start_col, len(line)))
    end = max(start, min(end_col, len(line)))
    return line[start:end]


def _slice_multiline_node_text(
    start_point: tuple[int, int],
    end_point: tuple[int, int],
    content_lines: list[str],
) -> list[str]:
    """Return bounded line slices for a multi-line node."""
    lines = []
    for line_number in range(
        start_point[0],
        min(end_point[0] + 1, len(content_lines)),
    ):
        lines.append(
            _slice_line_in_span(line_number, start_point, end_point, content_lines)
        )
    return lines


def _slice_line_in_span(
    line_number: int,
    start_point: tuple[int, int],
    end_point: tuple[int, int],
    content_lines: list[str],
) -> str:
    """Return one line slice for a multi-line node span."""
    line = content_lines[line_number]
    if line_number == start_point[0]:
        start_col = max(0, min(start_point[1], len(line)))
        return line[start_col:]
    if line_number == end_point[0]:
        end_col = max(0, min(end_point[1], len(line)))
        return line[:end_col]
    return line
