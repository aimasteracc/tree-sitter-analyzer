#!/usr/bin/env python3
"""
Path Resolver Utility for MCP Tools

This module provides unified path resolution functionality for all MCP tools,
ensuring consistent handling of relative and absolute paths across different
operating systems.
"""

import logging
import os

logger = logging.getLogger(__name__)


class PathResolver:
    """
    Utility class for resolving file paths in MCP tools.

    Handles relative path resolution against project root and provides
    cross-platform compatibility for Windows, macOS, and Linux.
    """

    def __init__(self, project_root: str | None = None):
        """
        Initialize the path resolver.

        Args:
            project_root: Optional project root directory for resolving relative paths
        """
        self.project_root = project_root
        if project_root:
            # Normalize project root path
            self.project_root = os.path.normpath(project_root)
            logger.debug(
                f"PathResolver initialized with project root: {self.project_root}"
            )

    def resolve(self, file_path: str) -> str:
        """
        Resolve a file path to an absolute path.

        Args:
            file_path: Input file path (can be relative or absolute)

        Returns:
            Resolved absolute file path

        Raises:
            ValueError: If file_path is empty or None
        """
        if not file_path:
            raise ValueError("file_path cannot be empty or None")

        # If already absolute, return as is
        if os.path.isabs(file_path):
            resolved_path = os.path.normpath(file_path)
            logger.debug(f"Path already absolute: {file_path} -> {resolved_path}")
            return resolved_path

        # If we have a project root, resolve relative to it
        if self.project_root:
            resolved_path = os.path.join(self.project_root, file_path)
            # Normalize path separators for cross-platform compatibility
            resolved_path = os.path.normpath(resolved_path)
            logger.debug(
                f"Resolved relative path '{file_path}' to '{resolved_path}' using project root"
            )
            return resolved_path

        # Fallback: try to resolve relative to current working directory
        resolved_path = os.path.abspath(file_path)
        resolved_path = os.path.normpath(resolved_path)
        logger.debug(
            f"Resolved relative path '{file_path}' to '{resolved_path}' using current working directory"
        )
        return resolved_path

    def is_relative(self, file_path: str) -> bool:
        """
        Check if a file path is relative.

        Args:
            file_path: File path to check

        Returns:
            True if the path is relative, False if absolute
        """
        return not os.path.isabs(file_path)

    def get_relative_path(self, absolute_path: str) -> str:
        """
        Get the relative path from project root to the given absolute path.

        Args:
            absolute_path: Absolute file path

        Returns:
            Relative path from project root, or the original path if no project root

        Raises:
            ValueError: If absolute_path is not actually absolute
        """
        if not os.path.isabs(absolute_path):
            raise ValueError(f"Path is not absolute: {absolute_path}")

        if not self.project_root:
            return absolute_path

        try:
            # Get relative path from project root
            relative_path = os.path.relpath(absolute_path, self.project_root)
            logger.debug(
                f"Converted absolute path '{absolute_path}' to relative path '{relative_path}'"
            )
            return relative_path
        except ValueError:
            # Paths are on different drives (Windows) or other error
            logger.warning(
                f"Could not convert absolute path '{absolute_path}' to relative path"
            )
            return absolute_path

    def validate_path(self, file_path: str) -> tuple[bool, str | None]:
        """
        Validate if a file path is valid and safe.

        Args:
            file_path: File path to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            resolved_path = self.resolve(file_path)

            # Check if file exists
            if not os.path.exists(resolved_path):
                return False, f"File does not exist: {resolved_path}"

            # Check if it's a file (not directory)
            if not os.path.isfile(resolved_path):
                return False, f"Path is not a file: {resolved_path}"

            # Check if it's within project root (if we have one)
            if self.project_root:
                try:
                    os.path.commonpath([resolved_path, self.project_root])
                except ValueError:
                    return False, f"File path is outside project root: {resolved_path}"

            return True, None

        except Exception as e:
            return False, f"Path validation error: {str(e)}"

    def get_project_root(self) -> str | None:
        """
        Get the current project root.

        Returns:
            Project root path or None if not set
        """
        return self.project_root

    def set_project_root(self, project_root: str) -> None:
        """
        Set or update the project root.

        Args:
            project_root: New project root directory
        """
        if project_root:
            self.project_root = os.path.normpath(project_root)
            logger.info(f"Project root updated to: {self.project_root}")
        else:
            self.project_root = None
            logger.info("Project root cleared")


# Convenience function for backward compatibility
def resolve_path(file_path: str, project_root: str | None = None) -> str:
    """
    Convenience function to resolve a file path.

    Args:
        file_path: File path to resolve
        project_root: Optional project root directory

    Returns:
        Resolved absolute file path
    """
    resolver = PathResolver(project_root)
    return resolver.resolve(file_path)
