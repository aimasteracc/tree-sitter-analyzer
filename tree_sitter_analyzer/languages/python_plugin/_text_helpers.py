"""Source text extraction helpers for the Python language extractor."""

from __future__ import annotations

from collections.abc import Callable

from ...encoding_utils import extract_text_slice, safe_encode


def _extract_node_text_by_bytes(
    content_lines: list[str],
    encoding: str,
    start_byte: int,
    end_byte: int,
    safe_encode_fn: Callable[[str, str], bytes] = safe_encode,
    extract_text_slice_fn: Callable[[bytes, int, int, str], str] = extract_text_slice,
) -> str:
    content_bytes = safe_encode_fn("\n".join(content_lines), encoding)
    return extract_text_slice_fn(content_bytes, start_byte, end_byte, encoding)


def _extract_node_text_by_points(
    content_lines: list[str], start_point: tuple[int, int], end_point: tuple[int, int]
) -> str:
    if not _point_range_within_lines(start_point, end_point, content_lines):
        return ""
    if start_point[0] == end_point[0]:
        return _extract_single_line_text(content_lines, start_point, end_point)
    return _extract_multiline_text(content_lines, start_point, end_point)


def _point_range_within_lines(
    start_point: tuple[int, int], end_point: tuple[int, int], content_lines: list[str]
) -> bool:
    return 0 <= start_point[0] < len(content_lines) and 0 <= end_point[0] < len(
        content_lines
    )


def _extract_single_line_text(
    content_lines: list[str], start_point: tuple[int, int], end_point: tuple[int, int]
) -> str:
    line = content_lines[start_point[0]]
    return _clamped_line_slice(line, start_point[1], end_point[1])


def _clamped_line_slice(line: str, start_col: int, end_col: int) -> str:
    start_col = max(0, min(start_col, len(line)))
    end_col = max(start_col, min(end_col, len(line)))
    return line[start_col:end_col]


def _extract_multiline_text(
    content_lines: list[str], start_point: tuple[int, int], end_point: tuple[int, int]
) -> str:
    lines = []
    for i in range(start_point[0], end_point[0] + 1):
        line = content_lines[i]
        if i == start_point[0]:
            lines.append(line[max(0, min(start_point[1], len(line))) :])
        elif i == end_point[0]:
            lines.append(line[: max(0, min(end_point[1], len(line)))])
        else:
            lines.append(line)
    return "\n".join(lines)
