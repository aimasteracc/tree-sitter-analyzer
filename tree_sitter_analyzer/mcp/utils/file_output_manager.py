#!/usr/bin/env python3
"""
File Output Manager for MCP Tools

This module provides functionality to save analysis results to files with
appropriate extensions based on content type, with security validation.

Enhanced with Managed Singleton Factory Pattern support for consistent
instance management across MCP tools.
"""

import json
import os
from pathlib import Path

from ...utils import setup_logger

# Set up logging
logger = setup_logger(__name__)


class FileOutputManager:
    """
    Manages file output for analysis results with automatic extension detection
    and security validation.

    Enhanced with factory method support for consistent instance management
    across MCP tools while maintaining full backward compatibility.
    """

    def __init__(self, project_root: str | None = None):
        """
        Initialize the file output manager.

        Args:
            project_root: Optional project root directory for fallback output path
        """
        self.project_root = project_root
        self._output_path = None
        self._initialize_output_path()

    @classmethod
    def get_managed_instance(
        cls, project_root: str | None = None
    ) -> "FileOutputManager":
        """
        Get a managed FileOutputManager instance using the factory pattern.

        This method provides access to the Managed Singleton Factory Pattern,
        ensuring one instance per project root for optimal resource usage
        and consistency across MCP tools.

        Args:
            project_root: Project root directory. If None, uses current working directory.

        Returns:
            FileOutputManager instance managed by the factory

        Note:
            This method requires the factory module to be available. If the factory
            is not available, it falls back to creating a new instance directly.
        """
        try:
            # Import here to avoid circular imports
            from .file_output_factory import FileOutputManagerFactory

            return FileOutputManagerFactory.get_instance(project_root)
        except ImportError as e:
            logger.warning(
                f"Factory not available, creating new instance directly: {e}"
            )
            return cls(project_root)

    @classmethod
    def create_instance(cls, project_root: str | None = None) -> "FileOutputManager":
        """
        Create a new FileOutputManager instance directly (bypass factory).

        This method creates a new instance without using the factory pattern.
        Use this when you specifically need a separate instance that won't
        be managed by the factory.

        Args:
            project_root: Project root directory. If None, uses current working directory.

        Returns:
            New FileOutputManager instance
        """
        return cls(project_root)

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
                    1
                    for line in lines[1:4]
                    if abs(line.count(",") - first_line_commas) <= 1
                )
                if similar_comma_lines >= 1:
                    return "csv"

        # Check for Markdown (simple heuristic)
        markdown_indicators = ["#", "##", "###", "|", "```", "*", "-", "+"]
        if any(
            content_stripped.startswith(indicator) for indicator in markdown_indicators
        ):
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
            "text": ".txt",
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

    def save_to_file(
        self, content: str, filename: str | None = None, base_name: str | None = None
    ) -> str:
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
