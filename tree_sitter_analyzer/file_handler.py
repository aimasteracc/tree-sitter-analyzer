#!/usr/bin/env python3
"""
File Handler Module

This module provides file reading functionality with encoding detection and fallback.
"""

from pathlib import Path

from .encoding_utils import read_file_safe
from .utils import log_error, log_info, log_warning


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
    """
    Read partial file content by line/column range

    Args:
        file_path: Path to file
        start_line: Start line (1-based)
        end_line: End line (1-based, None means EOF)
        start_column: Start column (0-based, optional)
        end_column: End column (0-based, optional)

    Returns:
        Selected content string, or None on error
    """
    # Check file existence
    file_obj = Path(file_path)
    if not file_obj.exists():
        log_error(f"File does not exist: {file_path}")
        return None

    # Parameter validation
    if start_line < 1:
        log_error(f"Invalid start_line: {start_line}. Line numbers start from 1.")
        return None

    if end_line is not None and end_line < start_line:
        log_error(f"Invalid range: end_line ({end_line}) < start_line ({start_line})")
        return None

    try:
        # Read whole file safely
        content, detected_encoding = read_file_safe(file_path)

        # Split to lines
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        # Adjust line indexes
        start_idx = start_line - 1  # convert to 0-based
        end_idx = min(
            end_line - 1 if end_line is not None else total_lines - 1, total_lines - 1
        )

        # Range check
        if start_idx >= total_lines:
            log_warning(
                f"start_line ({start_line}) exceeds file length ({total_lines})"
            )
            return ""

        # Select lines
        selected_lines = lines[start_idx : end_idx + 1]

        # Handle column range
        if start_column is not None or end_column is not None:
            processed_lines = []
            for i, line in enumerate(selected_lines):
                # Strip newline for processing
                line_content = line.rstrip("\r\n")

                if i == 0 and start_column is not None:
                    # First line: apply start_column
                    line_content = (
                        line_content[start_column:]
                        if start_column < len(line_content)
                        else ""
                    )

                if i == len(selected_lines) - 1 and end_column is not None:
                    # Last line: apply end_column
                    if i == 0 and start_column is not None:
                        # Single line: apply both start and end columns
                        col_end = (
                            end_column - start_column
                            if end_column >= start_column
                            else 0
                        )
                        line_content = line_content[:col_end] if col_end > 0 else ""
                    else:
                        line_content = (
                            line_content[:end_column]
                            if end_column < len(line_content)
                            else line_content
                        )

                # Preserve original newline (except last line)
                if i < len(selected_lines) - 1:
                    # Detect original newline char of the line
                    original_line = lines[start_idx + i]
                    if original_line.endswith("\r\n"):
                        line_content += "\r\n"
                    elif original_line.endswith("\n"):
                        line_content += "\n"
                    elif original_line.endswith("\r"):
                        line_content += "\r"

                processed_lines.append(line_content)

            result = "".join(processed_lines)
        else:
            # No column range: join lines directly
            result = "".join(selected_lines)

        log_info(
            f"Successfully read partial file {file_path}: "
            f"lines {start_line}-{end_line or total_lines}"
            f"{f', columns {start_column}-{end_column}' if start_column is not None or end_column is not None else ''}"
        )

        return result

    except Exception as e:
        log_error(f"Failed to read partial file {file_path}: {e}")
        return None


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
