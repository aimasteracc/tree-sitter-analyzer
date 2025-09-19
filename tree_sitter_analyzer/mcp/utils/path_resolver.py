#!/usr/bin/env python3
"""
Path Resolver Utility for MCP Tools

This module provides unified path resolution functionality for all MCP tools,
ensuring consistent handling of relative and absolute paths across different
operating systems.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _normalize_path_cross_platform(path_str: str) -> str:
    """
    Normalize path for cross-platform compatibility.

    Args:
        path_str: Input path string

    Returns:
        Normalized path string
    """
    if not path_str:
        return path_str

    # Handle macOS path normalization issues
    if os.name == "posix":
        # Handle /System/Volumes/Data prefix on macOS
        if path_str.startswith("/System/Volumes/Data/"):
            # Remove the /System/Volumes/Data prefix
            normalized = path_str[len("/System/Volumes/Data") :]
            return normalized

        # Handle /private/var vs /var symlink difference on macOS
        if path_str.startswith("/private/var/"):
            # Always normalize to /var form on macOS for consistency
            var_path = path_str.replace("/private/var/", "/var/", 1)
            return var_path
        elif path_str.startswith("/var/"):
            # Keep /var form as is
            return path_str

    # Handle Windows short path names (8.3 format)
    if os.name == "nt" and path_str:
        try:
            # Try to get the long path name on Windows
            import ctypes
            from ctypes import wintypes

            # GetLongPathNameW function
            _GetLongPathNameW = ctypes.windll.kernel32.GetLongPathNameW  # type: ignore[attr-defined]
            _GetLongPathNameW.argtypes = [
                wintypes.LPCWSTR,
                wintypes.LPWSTR,
                wintypes.DWORD,
            ]
            _GetLongPathNameW.restype = wintypes.DWORD

            # Buffer for the long path
            buffer_size = 1000
            buffer = ctypes.create_unicode_buffer(buffer_size)

            # Get the long path name
            result = _GetLongPathNameW(path_str, buffer, buffer_size)
            if result > 0 and result < buffer_size:
                long_path = buffer.value
                if long_path and long_path != path_str:
                    return long_path
        except (ImportError, AttributeError, OSError):
            # If Windows API calls fail, continue with original path
            pass

    return path_str


def _is_windows_absolute_path(path_str: str) -> bool:
    """
    Check if a path is a Windows-style absolute path.

    Args:
        path_str: Path string to check

    Returns:
        True if it's a Windows absolute path (e.g., C:\\path or C:/path)
    """
    if not path_str or len(path_str) < 3:
        return False

    # Check for drive letter pattern: X:\ or X:/
    return path_str[1] == ":" and path_str[0].isalpha() and path_str[2] in ("\\", "/")


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
        self.project_root = None
        self._cache = {}  # Simple cache for resolved paths
        self._cache_size_limit = 100  # Limit cache size to prevent memory issues

        if project_root:
            # Use pathlib for consistent path handling, but preserve relative paths for compatibility
            path_obj = Path(project_root)
            if path_obj.is_absolute():
                resolved_root = str(path_obj.resolve())
                # Apply cross-platform normalization
                self.project_root = _normalize_path_cross_platform(resolved_root)
            else:
                # For relative paths, normalize but don't resolve to absolute
                self.project_root = str(path_obj)
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
            TypeError: If file_path is not a string
        """
        if not file_path:
            raise ValueError("file_path cannot be empty or None")

        if not isinstance(file_path, str):
            raise TypeError(
                f"file_path must be a string, got {type(file_path).__name__}"
            )

        # Check cache first
        if file_path in self._cache:
            logger.debug(f"Cache hit for path: {file_path}")
            return self._cache[file_path]

        # Normalize path separators first
        normalized_input = file_path.replace("\\", "/")

        # Special handling for Windows absolute paths on non-Windows systems
        if _is_windows_absolute_path(file_path) and os.name != "nt":
            # On non-Windows systems, Windows absolute paths should be treated as-is
            # Don't try to resolve them relative to project root
            logger.debug(f"Windows absolute path on non-Windows system: {file_path}")
            self._add_to_cache(file_path, file_path)
            return file_path

        path_obj = Path(normalized_input)

        # Handle Unix-style absolute paths on Windows (starting with /) FIRST
        # This must come before the is_absolute() check because Unix paths aren't
        # considered absolute on Windows by pathlib
        if (
            normalized_input.startswith("/") and os.name == "nt"
        ):  # Check if we're on Windows
            # On Windows, convert Unix-style absolute paths to Windows format
            # by prepending the current drive with proper separator
            current_drive = Path.cwd().drive
            if current_drive:
                # Remove leading slash and join with current drive
                unix_path_without_slash = normalized_input[1:]
                # Ensure proper Windows path format with backslash after drive
                resolved_path = str(
                    Path(current_drive + "\\") / unix_path_without_slash
                )
                logger.debug(
                    f"Converted Unix absolute path: {file_path} -> {resolved_path}"
                )
                # Apply cross-platform normalization
                resolved_path = _normalize_path_cross_platform(resolved_path)
                self._add_to_cache(file_path, resolved_path)
                return resolved_path
            # If no drive available, continue with normal processing

        # Check if path is absolute
        if path_obj.is_absolute():
            resolved_path = str(path_obj.resolve())
            logger.debug(f"Path already absolute: {file_path} -> {resolved_path}")
            # Apply cross-platform normalization
            resolved_path = _normalize_path_cross_platform(resolved_path)
            self._add_to_cache(file_path, resolved_path)
            return resolved_path

        # If we have a project root, resolve relative to it
        if self.project_root:
            resolved_path = str((Path(self.project_root) / normalized_input).resolve())
            logger.debug(
                f"Resolved relative path '{file_path}' to '{resolved_path}' using project root"
            )
            # Apply cross-platform normalization
            resolved_path = _normalize_path_cross_platform(resolved_path)
            self._add_to_cache(file_path, resolved_path)
            return resolved_path

        # Fallback: try to resolve relative to current working directory
        resolved_path = str(Path(normalized_input).resolve())
        logger.debug(
            f"Resolved relative path '{file_path}' to '{resolved_path}' using current working directory"
        )

        # Apply cross-platform normalization
        resolved_path = _normalize_path_cross_platform(resolved_path)

        # Cache the result
        self._add_to_cache(file_path, resolved_path)

        return resolved_path

    def _add_to_cache(self, file_path: str, resolved_path: str) -> None:
        """
        Add a resolved path to the cache.

        Args:
            file_path: Original file path
            resolved_path: Resolved absolute path
        """
        # Limit cache size to prevent memory issues
        if len(self._cache) >= self._cache_size_limit:
            # Remove oldest entries (simple FIFO)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug(f"Cache full, removed oldest entry: {oldest_key}")

        self._cache[file_path] = resolved_path
        logger.debug(f"Cached path resolution: {file_path} -> {resolved_path}")

    def clear_cache(self) -> None:
        """Clear the path resolution cache."""
        cache_size = len(self._cache)
        self._cache.clear()
        logger.info(f"Cleared path resolution cache ({cache_size} entries)")

    def get_cache_stats(self) -> dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {"size": len(self._cache), "limit": self._cache_size_limit}

    def is_relative(self, file_path: str) -> bool:
        """
        Check if a file path is relative.

        Args:
            file_path: File path to check

        Returns:
            True if the path is relative, False if absolute
        """
        return not Path(file_path).is_absolute()

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
        abs_path = Path(absolute_path)
        if not abs_path.is_absolute():
            raise ValueError(f"Path is not absolute: {absolute_path}")

        if not self.project_root:
            return absolute_path

        try:
            # Get relative path from project root using pathlib
            project_path = Path(self.project_root)

            # Normalize both paths for consistent comparison
            normalized_abs_path = _normalize_path_cross_platform(
                str(abs_path.resolve())
            )
            normalized_project_root = _normalize_path_cross_platform(
                str(project_path.resolve())
            )

            # Convert back to Path objects for relative_to calculation
            normalized_abs_path_obj = Path(normalized_abs_path)
            normalized_project_root_obj = Path(normalized_project_root)

            relative_path = str(
                normalized_abs_path_obj.relative_to(normalized_project_root_obj)
            )
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
            resolved_path_obj = Path(resolved_path)

            if not resolved_path_obj.exists():
                return False, f"File does not exist: {resolved_path}"

            # Check if it's a file (not directory)
            if not resolved_path_obj.is_file():
                return False, f"Path is not a file: {resolved_path}"

            # Check if it's a symlink (reject symlinks for security)
            try:
                if resolved_path_obj.is_symlink():
                    return False, f"Path is a symlink: {resolved_path}"
            except (OSError, AttributeError):
                # is_symlink() might not be available on all platforms
                # or might fail due to permissions, skip this check
                pass

            # Check if it's within project root (if we have one)
            if self.project_root:
                try:
                    project_path = Path(self.project_root).resolve()
                    resolved_abs_path = resolved_path_obj.resolve()
                    # Check if the resolved path is within the project root
                    resolved_abs_path.relative_to(project_path)
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
            # Use pathlib for consistent path handling, but preserve relative paths for compatibility
            path_obj = Path(project_root)
            if path_obj.is_absolute():
                resolved_root = str(path_obj.resolve())
                # Apply cross-platform normalization
                self.project_root = _normalize_path_cross_platform(resolved_root)
            else:
                # For relative paths, normalize but don't resolve to absolute
                self.project_root = str(path_obj)
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
