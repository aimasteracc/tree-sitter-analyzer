"""Tree-sitter node text extraction helpers for Markdown."""

from typing import TYPE_CHECKING

from ...encoding_utils import extract_text_slice, safe_encode

if TYPE_CHECKING:
    import tree_sitter


def _extract_node_text_by_bytes(
    node: "tree_sitter.Node",
    content_lines: list[str],
    encoding: str,
) -> str:
    """Extract node text from byte offsets using the file encoding."""
    content_bytes = safe_encode("\n".join(content_lines), encoding)
    return extract_text_slice(
        content_bytes,
        node.start_byte,
        node.end_byte,
        encoding,
    )


def _extract_node_text_by_points(
    node: "tree_sitter.Node",
    content_lines: list[str],
) -> str:
    """Fallback node text extraction using tree-sitter point coordinates."""
    start_point = node.start_point
    end_point = node.end_point

    if not _line_in_bounds(start_point[0], content_lines):
        return ""
    if not _line_in_bounds(end_point[0], content_lines):
        return ""
    if start_point[0] == end_point[0]:
        return _slice_single_line(
            content_lines[start_point[0]],
            start_point[1],
            end_point[1],
        )

    return "\n".join(_slice_multiline_node_text(start_point, end_point, content_lines))


def _line_in_bounds(line_number: int, content_lines: list[str]) -> bool:
    """Return whether a line index can be read from content_lines."""
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
        line = content_lines[line_number]
        if line_number == start_point[0]:
            start_col = max(0, min(start_point[1], len(line)))
            lines.append(line[start_col:])
        elif line_number == end_point[0]:
            end_col = max(0, min(end_point[1], len(line)))
            lines.append(line[:end_col])
        else:
            lines.append(line)
    return lines
