#!/usr/bin/env python3
"""
File Output Manager for MCP Tools

This module provides functionality to save analysis results to files with
appropriate extensions based on content type, with security validation.
"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from ...utils import setup_logger

# Set up logging
logger = setup_logger(__name__)


class FileOutputManager:
    """
    Manages file output for analysis results with automatic extension detection
    and security validation.
    """
    
    # クラス変数で警告メッセージの重複を防ぐ（プロセス内のみ）
    _warning_messages_shown = set()
    
    # プロセス間共有用のファイルベース重複防止
    @staticmethod
    def _get_warning_lock_file(warning_key: str) -> Path:
        """警告メッセージ用のロックファイルパスを取得"""
        temp_dir = Path(tempfile.gettempdir())
        safe_key = warning_key.replace("/", "_").replace(":", "_").replace("\\", "_")
        return temp_dir / f"tree_sitter_analyzer_warning_{safe_key}.lock"
    
    @staticmethod
    def _should_show_warning(warning_key: str, max_age_seconds: int = 300) -> bool:
        """
        プロセス間で警告表示の可否を判定
        
        Args:
            warning_key: 警告キー
            max_age_seconds: ロックファイルの有効期間（秒）
            
        Returns:
            警告を表示すべきかどうか
        """
        # プロセス内での重複チェック
        if warning_key in FileOutputManager._warning_messages_shown:
            return False
        
        # プロセス間での重複チェック
        lock_file = FileOutputManager._get_warning_lock_file(warning_key)
        
        try:
            # ロックファイルが存在し、有効期間内なら警告をスキップ
            if lock_file.exists():
                mtime = lock_file.stat().st_mtime
                if time.time() - mtime < max_age_seconds:
                    FileOutputManager._warning_messages_shown.add(warning_key)
                    return False
                else:
                    # 期限切れのロックファイルを削除
                    try:
                        lock_file.unlink()
                    except (OSError, FileNotFoundError):
                        pass
            
            # ロックファイルを作成して警告表示権を獲得
            lock_file.touch()
            FileOutputManager._warning_messages_shown.add(warning_key)
            return True
            
        except (OSError, IOError):
            # ファイル操作に失敗した場合はフォールバック
            # プロセス内のみの重複防止に戻る
            FileOutputManager._warning_messages_shown.add(warning_key)
            return True

    def __init__(self, project_root: str | None = None):
        """
        Initialize the file output manager.

        Args:
            project_root: Optional project root directory for fallback output path
        """
        self.project_root = project_root
        self._output_path = None
        self._initialize_output_path()

    def _initialize_output_path(self) -> None:
        """Initialize the output path from environment variables or project root."""
        # Priority 1: Environment variable TREE_SITTER_OUTPUT_PATH
        env_output_path = os.environ.get("TREE_SITTER_OUTPUT_PATH")
        if env_output_path and Path(env_output_path).exists():
            self._output_path = env_output_path
            logger.info(f"Using output path from environment: {self._output_path}")
            return

        # Priority 2: Project root if available
        if self.project_root and Path(self.project_root).exists():
            self._output_path = self.project_root
            logger.info(f"Using project root as output path: {self._output_path}")
            return

        # Priority 3: Current working directory as fallback
        self._output_path = str(Path.cwd())
        
        # プロセス間で重複警告を防ぐ
        warning_key = f"fallback_path:{self._output_path}"
        if self._should_show_warning(warning_key):
            logger.warning(f"Using current directory as output path: {self._output_path}")

    def get_output_path(self) -> str:
        """
        Get the current output path.

        Returns:
            Current output path
        """
        return self._output_path or str(Path.cwd())

    def set_output_path(self, output_path: str) -> None:
        """
        Set a custom output path.

        Args:
            output_path: New output path

        Raises:
            ValueError: If the path doesn't exist or is not a directory
        """
        path_obj = Path(output_path)
        if not path_obj.exists():
            raise ValueError(f"Output path does not exist: {output_path}")
        if not path_obj.is_dir():
            raise ValueError(f"Output path is not a directory: {output_path}")

        self._output_path = str(path_obj.resolve())
        logger.info(f"Output path updated to: {self._output_path}")

    def detect_content_type(self, content: str) -> str:
        """
        Detect content type based on content structure.

        Args:
            content: Content to analyze

        Returns:
            Detected content type ('json', 'csv', 'markdown', or 'text')
        """
        content_stripped = content.strip()

        # Check for JSON
        if content_stripped.startswith(("{", "[")):
            try:
                json.loads(content_stripped)
                return "json"
            except (json.JSONDecodeError, ValueError):
                pass

        # Check for CSV (simple heuristic)
        lines = content_stripped.split("\n")
        if len(lines) >= 2:
            # Check if first few lines have consistent comma separation
            first_line_commas = lines[0].count(",")
            if first_line_commas > 0:
                # Check if at least 2 more lines have similar comma counts
                similar_comma_lines = sum(
                    1 for line in lines[1:4] if abs(line.count(",") - first_line_commas) <= 1
                )
                if similar_comma_lines >= 1:
                    return "csv"

        # Check for Markdown (simple heuristic)
        markdown_indicators = ["#", "##", "###", "|", "```", "*", "-", "+"]
        if any(content_stripped.startswith(indicator) for indicator in markdown_indicators):
            return "markdown"

        # Check for table format (pipe-separated)
        if "|" in content and "\n" in content:
            lines = content_stripped.split("\n")
            pipe_lines = sum(1 for line in lines if "|" in line)
            if pipe_lines >= 2:  # At least header and one data row
                return "markdown"

        # Default to text
        return "text"

    def get_file_extension(self, content_type: str) -> str:
        """
        Get file extension for content type.

        Args:
            content_type: Content type ('json', 'csv', 'markdown', 'text')

        Returns:
            File extension including the dot
        """
        extension_map = {
            "json": ".json",
            "csv": ".csv",
            "markdown": ".md",
            "text": ".txt"
        }
        return extension_map.get(content_type, ".txt")

    def generate_output_filename(self, base_name: str, content: str) -> str:
        """
        Generate output filename with appropriate extension.

        Args:
            base_name: Base filename (without extension)
            content: Content to analyze for type detection

        Returns:
            Complete filename with extension
        """
        content_type = self.detect_content_type(content)
        extension = self.get_file_extension(content_type)
        
        # Remove existing extension if present
        base_name_clean = Path(base_name).stem
        
        return f"{base_name_clean}{extension}"

    def save_to_file(self, content: str, filename: str | None = None, base_name: str | None = None) -> str:
        """
        Save content to file with automatic extension detection.

        Args:
            content: Content to save
            filename: Optional specific filename (overrides base_name)
            base_name: Optional base name for auto-generated filename

        Returns:
            Path to the saved file

        Raises:
            ValueError: If neither filename nor base_name is provided
            OSError: If file cannot be written
        """
        if not filename and not base_name:
            raise ValueError("Either filename or base_name must be provided")

        output_path = Path(self.get_output_path())

        if filename:
            # Use provided filename as-is
            output_file = output_path / filename
        else:
            # Generate filename with appropriate extension
            generated_filename = self.generate_output_filename(base_name, content)
            output_file = output_path / generated_filename

        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write content to file
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            logger.info(f"Content saved to file: {output_file}")
            return str(output_file)

        except OSError as e:
            logger.error(f"Failed to save content to file {output_file}: {e}")
            raise

    def validate_output_path(self, path: str) -> tuple[bool, str | None]:
        """
        Validate if a path is safe for output.

        Args:
            path: Path to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            path_obj = Path(path).resolve()
            
            # Check if parent directory exists or can be created
            parent_dir = path_obj.parent
            if not parent_dir.exists():
                try:
                    parent_dir.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    return False, f"Cannot create parent directory: {e}"

            # Check if we can write to the directory
            if not os.access(parent_dir, os.W_OK):
                return False, f"No write permission for directory: {parent_dir}"

            # Check if file already exists and is writable
            if path_obj.exists() and not os.access(path_obj, os.W_OK):
                return False, f"No write permission for existing file: {path_obj}"

            return True, None

        except Exception as e:
            return False, f"Path validation error: {str(e)}"

    def set_project_root(self, project_root: str) -> None:
        """
        Update the project root and reinitialize output path if needed.

        Args:
            project_root: New project root directory
        """
        self.project_root = project_root
        # Only reinitialize if we don't have an explicit output path from environment
        if not os.environ.get("TREE_SITTER_OUTPUT_PATH"):
            self._initialize_output_path()