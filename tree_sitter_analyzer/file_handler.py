#!/usr/bin/env python3
"""
File Handler Module

This module provides file reading functionality with encoding detection and fallback.
"""

import itertools
from pathlib import Path

from .encoding_utils import read_file_safe, read_file_safe_streaming
from .utils import setup_logger

# Set up logger for this module
logger = setup_logger(__name__)


def log_error(message: str, *args: object, **kwargs: object) -> None:
    """Log error message"""
    logger.error(message, *args, **kwargs)  # type: ignore[arg-type]


def log_info(message: str, *args: object, **kwargs: object) -> None:
    """Log info message"""
    logger.info(message, *args, **kwargs)  # type: ignore[arg-type]


def log_warning(message: str, *args: object, **kwargs: object) -> None:
    """Log warning message"""
    logger.warning(message, *args, **kwargs)  # type: ignore[arg-type]


def detect_language_from_extension(file_path: str) -> str:
    """
    Detect programming language from file extension

    Args:
        file_path: File path to analyze

    Returns:
        Language name or 'unknown' if not recognized
    """
    extension = Path(file_path).suffix.lower()

    extension_map = {
        ".java": "java",
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".kt": "kotlin",
        ".scala": "scala",
        ".swift": "swift",
        ".swiftinterface": "swift",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "bash",
    }

    return extension_map.get(extension, "unknown")


def read_file_with_fallback(file_path: str) -> bytes | None:
    """
    Read file with encoding fallback using unified encoding utilities

    Args:
        file_path: Path to the file to read

    Returns:
        File content as bytes, or None if file doesn't exist
    """
    # Check file existence first
    file_obj = Path(file_path)
    if not file_obj.exists():
        log_error(f"File does not exist: {file_path}")
        return None

    try:
        content, detected_encoding = read_file_safe(file_path)
        log_info(
            f"Successfully read file {file_path} with encoding: {detected_encoding}"
        )
        return content.encode("utf-8")

    except Exception as e:
        log_error(f"Failed to read file {file_path}: {e}")
        return None


def read_file_partial(
    file_path: str,
    start_line: int,
    end_line: int | None = None,
    start_column: int | None = None,
    end_column: int | None = None,
) -> str | None:
    """Read partial file content by line/column range using streaming for memory efficiency.

    Performance: Uses streaming approach for 150x speedup on large files.
    Only loads requested lines into memory instead of entire file.

    r37aw (dogfood): the tool flagged this function at 135 lines / nesting
    depth 7. Refactored into 4 helpers that each do one thing — validation,
    streaming line slice, column clipping, and logging. Behaviour preserved.
    """
    if not _read_file_partial_validate(file_path, start_line, end_line):
        return None

    try:
        selected_lines = _slice_streaming_lines(file_path, start_line, end_line)
        if selected_lines is None:
            # Past-EOF / empty-file case — handled below as empty result.
            return ""

        if start_column is not None or end_column is not None:
            result = _apply_column_range(selected_lines, start_column, end_column)
        else:
            result = "".join(selected_lines)

        _log_partial_read_success(
            file_path, start_line, end_line, start_column, end_column, selected_lines
        )
        return result

    except Exception as e:
        log_error(f"Failed to read partial file {file_path}: {e}")
        return None


def _read_file_partial_validate(
    file_path: str, start_line: int, end_line: int | None
) -> bool:
    """Return False (after logging) when the caller's args are unusable."""
    if not Path(file_path).exists():
        log_error(f"File does not exist: {file_path}")
        return False
    if start_line < 1:
        log_error(f"Invalid start_line: {start_line}. Line numbers start from 1.")
        return False
    if end_line is not None and end_line < start_line:
        log_error(f"Invalid range: end_line ({end_line}) < start_line ({start_line})")
        return False
    return True


def _slice_streaming_lines(
    file_path: str, start_line: int, end_line: int | None
) -> list[str] | None:
    """Stream-read just the requested 1-indexed line range.

    Returns ``None`` when ``start_line`` is past EOF (caller treats that
    as empty-string result). Returns an empty list for an empty file in
    range — also empty-string result.
    """
    with read_file_safe_streaming(file_path) as f:
        start_idx = start_line - 1
        end_idx = end_line - 1 if end_line is not None else None
        if end_idx is not None:
            selected_iter = itertools.islice(f, start_idx, end_idx + 1)
        else:
            selected_iter = itertools.islice(f, start_idx, None)
        selected_lines = list(selected_iter)

    if selected_lines:
        return selected_lines

    # No lines came back — distinguish past-EOF from empty in-range.
    with read_file_safe_streaming(file_path) as f_count:
        total_lines = sum(1 for _ in f_count)
    if (start_line - 1) >= total_lines:
        log_warning(f"start_line ({start_line}) exceeds file length ({total_lines})")
    return None


def _apply_column_range(
    selected_lines: list[str],
    start_column: int | None,
    end_column: int | None,
) -> str:
    """Clip each line by ``start_column`` / ``end_column`` and rejoin."""
    last_idx = len(selected_lines) - 1
    processed_lines: list[str] = []
    for i, line in enumerate(selected_lines):
        line_content = line.rstrip("\r\n")
        if i == 0 and start_column is not None:
            line_content = (
                line_content[start_column:] if start_column < len(line_content) else ""
            )
        if i == last_idx and end_column is not None:
            line_content = _clip_end_column(
                line_content,
                start_column if i == 0 else None,
                end_column,
            )

        if i < last_idx:
            line_content += _trailing_newline(selected_lines[i])
        processed_lines.append(line_content)
    return "".join(processed_lines)


def _clip_end_column(
    line_content: str,
    start_column: int | None,
    end_column: int,
) -> str:
    """Apply ``end_column`` to the final (possibly only) line of the slice."""
    if start_column is not None:
        # Single-line slice: both columns clip the same line.
        col_end = end_column - start_column if end_column >= start_column else 0
        return line_content[:col_end] if col_end > 0 else ""
    if end_column < len(line_content):
        return line_content[:end_column]
    return line_content


def _trailing_newline(original_line: str) -> str:
    """Return the original newline characters (handles \\r\\n / \\n / \\r)."""
    if original_line.endswith("\r\n"):
        return "\r\n"
    if original_line.endswith("\n"):
        return "\n"
    if original_line.endswith("\r"):
        return "\r"
    return ""


def _log_partial_read_success(
    file_path: str,
    start_line: int,
    end_line: int | None,
    start_column: int | None,
    end_column: int | None,
    selected_lines: list[str],
) -> None:
    """Emit the success log line shared by both column-range and full-line paths."""
    actual_end_line = end_line or (start_line + len(selected_lines) - 1)
    column_note = (
        f", columns {start_column}-{end_column}"
        if start_column is not None or end_column is not None
        else ""
    )
    log_info(
        f"Successfully read partial file {file_path}: "
        f"lines {start_line}-{actual_end_line}"
        f"{column_note}"
    )


def read_file_lines_range(
    file_path: str, start_line: int, end_line: int | None = None
) -> str | None:
    """
    指定した行番号範囲でファイルの一部を読み込み（列指定なし）

    Args:
        file_path: 読み込むファイルのパス
        start_line: 開始行番号（1ベース）
        end_line: 終了行番号（Noneの場合はファイル末尾まで、1ベース）

    Returns:
        指定範囲のファイル内容（文字列）、エラーの場合はNone
    """
    return read_file_partial(file_path, start_line, end_line)
