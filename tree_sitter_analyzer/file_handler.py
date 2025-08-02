#!/usr/bin/env python3
"""
File Handler Module

This module provides file reading functionality with encoding detection and fallback.
"""

import os

from .encoding_utils import read_file_safe
from .utils import log_error, log_info, log_warning


def detect_language_from_extension(file_path: str) -> str:
    """
    ファイル拡張子から言語を判定

    Args:
        file_path: ファイルパス

    Returns:
        言語名または'unknown'
    """
    extension = os.path.splitext(file_path)[1].lower()

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
    # まずファイルの存在を確認
    if not os.path.exists(file_path):
        log_error(f"File does not exist: {file_path}")
        return None

    try:
        content, detected_encoding = read_file_safe(file_path)
        if content is not None:  # 空文字列も有効なコンテンツ
            log_info(
                f"Successfully read file {file_path} with encoding: {detected_encoding}"
            )
            return content.encode("utf-8")
        else:
            log_warning(f"File {file_path} is empty or could not be read")
            return b""

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
    指定した行番号・列番号範囲でファイルの一部を読み込み

    Args:
        file_path: 読み込むファイルのパス
        start_line: 開始行番号（1ベース）
        end_line: 終了行番号（Noneの場合はファイル末尾まで、1ベース）
        start_column: 開始列番号（0ベース、省略可）
        end_column: 終了列番号（0ベース、省略可）

    Returns:
        指定範囲のファイル内容（文字列）、エラーの場合はNone
    """
    # ファイルの存在確認
    if not os.path.exists(file_path):
        log_error(f"File does not exist: {file_path}")
        return None

    # パラメータ検証
    if start_line < 1:
        log_error(f"Invalid start_line: {start_line}. Line numbers start from 1.")
        return None

    if end_line is not None and end_line < start_line:
        log_error(f"Invalid range: end_line ({end_line}) < start_line ({start_line})")
        return None

    try:
        # ファイル全体を安全に読み込み
        content, detected_encoding = read_file_safe(file_path)
        if content is None:
            log_error(f"Failed to read file: {file_path}")
            return None

        # 行に分割
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        # 行範囲の調整
        start_idx = start_line - 1  # 0ベースに変換
        end_idx = min(
            end_line - 1 if end_line is not None else total_lines - 1, total_lines - 1
        )

        # 範囲チェック
        if start_idx >= total_lines:
            log_warning(
                f"start_line ({start_line}) exceeds file length ({total_lines})"
            )
            return ""

        # 指定範囲の行を取得
        selected_lines = lines[start_idx : end_idx + 1]

        # 列範囲の処理
        if start_column is not None or end_column is not None:
            processed_lines = []
            for i, line in enumerate(selected_lines):
                # 改行文字を除去して処理
                line_content = line.rstrip("\r\n")

                if i == 0 and start_column is not None:
                    # 最初の行：開始列から
                    line_content = (
                        line_content[start_column:]
                        if start_column < len(line_content)
                        else ""
                    )

                if i == len(selected_lines) - 1 and end_column is not None:
                    # 最後の行：終了列まで
                    if i == 0 and start_column is not None:
                        # 単一行の場合：開始列と終了列の両方を適用
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

                # 元の改行文字を保持（最後の行以外）
                if i < len(selected_lines) - 1:
                    # 元の行の改行文字を取得
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
            # 列指定なしの場合は行をそのまま結合
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
