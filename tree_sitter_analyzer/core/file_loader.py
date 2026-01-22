#!/usr/bin/env python3
"""
File Loader - Responsible for loading file content with encoding detection
"""

import os
from pathlib import Path


class FileLoadError(Exception):
    """File loading error"""

    pass


class FileLoader:
    """
    File loader with encoding detection and error handling.

    Responsibilities:
    - Load file content from disk
    - Detect and handle various encodings
    - Provide clear error messages
    """

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize file loader.

        Args:
            project_root: Optional project root (for backward compatibility, not used)
        """
        # Comprehensive encoding list supporting multiple languages
        # Priority order: UTF-8 with BOM first (auto-removes BOM), then UTF-8, then regional encodings
        self._default_encodings = [
            "utf-8-sig",  # UTF-8 with BOM (auto-removes BOM)
            "utf-8",  # UTF-8 without BOM
            "shift_jis",
            "cp932",  # Japanese (Windows Shift_JIS)
            "euc-jp",
            "iso-2022-jp",  # Japanese (Unix/Email)
            "gbk",
            "gb18030",  # Simplified Chinese
            "big5",  # Traditional Chinese
            "latin-1",
            "cp1252",  # Western European
        ]

    def load(self, file_path: str | Path) -> str:
        """
        Load file content with automatic encoding detection.

        Args:
            file_path: Path to the file to load

        Returns:
            File content as string

        Raises:
            FileLoadError: If file cannot be loaded
        """
        path = Path(file_path)

        # Validate file exists
        if not path.exists():
            raise FileLoadError(f"File not found: {file_path}")

        if not path.is_file():
            raise FileLoadError(f"Not a file: {file_path}")

        # Try to load with different encodings
        last_error: Exception | None = None

        for encoding in self._default_encodings:
            try:
                with open(path, encoding=encoding) as f:
                    return f.read()
            except (UnicodeDecodeError, LookupError) as e:
                last_error = e
                continue

        # If all encodings failed, raise error
        raise FileLoadError(
            f"Failed to load file {file_path} with any supported encoding. "
            f"Last error: {last_error}"
        )

    def load_with_encoding(self, file_path: str | Path, encoding: str) -> str:
        """
        Load file content with specific encoding.

        Args:
            file_path: Path to the file to load
            encoding: Specific encoding to use

        Returns:
            File content as string

        Raises:
            FileLoadError: If file cannot be loaded
        """
        path = Path(file_path)

        if not path.exists():
            raise FileLoadError(f"File not found: {file_path}")

        try:
            with open(path, encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError, OSError) as e:
            raise FileLoadError(
                f"Failed to load file {file_path} with encoding {encoding}: {e}"
            )

    def exists(self, file_path: str | Path) -> bool:
        """
        Check if file exists.

        Args:
            file_path: Path to check

        Returns:
            True if file exists, False otherwise
        """
        return Path(file_path).exists()

    def get_file_size(self, file_path: str | Path) -> int:
        """
        Get file size in bytes.

        Args:
            file_path: Path to the file

        Returns:
            File size in bytes

        Raises:
            FileLoadError: If file cannot be accessed
        """
        path = Path(file_path)

        if not path.exists():
            raise FileLoadError(f"File not found: {file_path}")

        try:
            return os.path.getsize(path)
        except OSError as e:
            raise FileLoadError(f"Failed to get file size for {file_path}: {e}")
