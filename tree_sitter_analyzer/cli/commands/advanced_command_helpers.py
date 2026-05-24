"""Helpers for advanced CLI command metrics."""

from __future__ import annotations

from dataclasses import dataclass

from ...encoding_utils import read_file_safe


@dataclass
class LineMetricCounts:
    """Mutable line-counting state."""

    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    in_multiline_comment: bool = False


def calculate_file_metrics(file_path: str, language: str) -> dict[str, int]:
    """Calculate accurate file metrics including line counts."""
    try:
        content, _ = read_file_safe(file_path)
    except Exception:
        return _zero_metrics()
    return calculate_content_metrics(content, language)


def calculate_content_metrics(content: str, language: str) -> dict[str, int]:
    """Calculate code, comment, and blank line counts from file content."""
    lines = content.split("\n")
    total_lines = len(lines)
    if lines and not lines[-1]:
        total_lines -= 1

    counts = _count_lines(lines, language)
    counts.blank_lines = _adjust_blank_lines(counts, total_lines)

    return {
        "total_lines": total_lines,
        "code_lines": counts.code_lines,
        "comment_lines": counts.comment_lines,
        "blank_lines": counts.blank_lines,
    }


def _count_lines(lines: list[str], language: str) -> LineMetricCounts:
    """Count line categories while preserving multiline comment state."""
    counts = LineMetricCounts()
    for line in lines:
        _count_line(line.strip(), language, counts)
    return counts


def _count_line(stripped: str, language: str, counts: LineMetricCounts) -> None:
    """Count one stripped line into code, comment, or blank categories."""
    if not stripped:
        counts.blank_lines += 1
        return

    if counts.in_multiline_comment:
        counts.comment_lines += 1
        if "*/" in stripped:
            counts.in_multiline_comment = False
        return

    if _starts_c_style_multiline_comment(stripped):
        counts.comment_lines += 1
        counts.in_multiline_comment = "*/" not in stripped
        return

    if _is_single_line_comment(stripped, language):
        counts.comment_lines += 1
        return

    if language in ["html", "xml"] and stripped.startswith("<!--"):
        counts.comment_lines += 1
        if "-->" not in stripped:
            counts.in_multiline_comment = True
        return

    counts.code_lines += 1


def _starts_c_style_multiline_comment(stripped: str) -> bool:
    """Return whether a line starts a C-style multiline comment."""
    return stripped.startswith("/**") or stripped.startswith("/*")


def _is_single_line_comment(stripped: str, language: str) -> bool:
    """Return whether a line is a single-line comment."""
    return (
        stripped.startswith("//")
        or (stripped.startswith("*") and not stripped.startswith("*/"))
        or (language == "python" and stripped.startswith("#"))
        or (language == "sql" and stripped.startswith("--"))
    )


def _adjust_blank_lines(counts: LineMetricCounts, total_lines: int) -> int:
    """Adjust blank lines so counted categories sum to total lines."""
    calculated_total = counts.code_lines + counts.comment_lines + counts.blank_lines
    if calculated_total == total_lines:
        return counts.blank_lines
    return max(0, total_lines - counts.code_lines - counts.comment_lines)


def _zero_metrics() -> dict[str, int]:
    """Return zero-valued file metrics."""
    return {
        "total_lines": 0,
        "code_lines": 0,
        "comment_lines": 0,
        "blank_lines": 0,
    }
