#!/usr/bin/env python3
"""
Project Boundary Manager for Tree-sitter Analyzer

Provides strict project boundary control to prevent access to files
outside the designated project directory.
"""

from pathlib import Path

from ..exceptions import SecurityError
from ..utils import log_debug, log_info, log_warning


class ProjectBoundaryManager:
    """
    Project boundary manager for access control.

    This class enforces strict boundaries around project directories
    to prevent unauthorized file access outside the project scope.

    Features:
    - Real path resolution for symlink protection
    - Configurable allowed directories
    - Comprehensive boundary checking
    - Audit logging for security events
    """

    def __init__(self, project_root: str) -> None:
        """
        Initialize project boundary manager.

        Args:
            project_root: Root directory of the project

        Raises:
            SecurityError: If project root is invalid
        """
        if not project_root:
            raise SecurityError("Project root cannot be empty")

        project_path = Path(project_root)
        if not project_path.exists():
            raise SecurityError(f"Project root does not exist: {project_root}")

        if not project_path.is_dir():
            raise SecurityError(f"Project root is not a directory: {project_root}")

        # Store real path to prevent symlink attacks
        self.project_root = str(project_path.resolve())
        self.allowed_directories: set[str] = {self.project_root}

        log_debug(f"ProjectBoundaryManager initialized with root: {self.project_root}")

    def add_allowed_directory(self, directory: str) -> None:
        """
        Add an additional allowed directory.

        Args:
            directory: Directory path to allow access to

        Raises:
            SecurityError: If directory is invalid
        """
        if not directory:
            raise SecurityError("Directory cannot be empty")

        dir_path = Path(directory)
        if not dir_path.exists():
            raise SecurityError(f"Directory does not exist: {directory}")

        if not dir_path.is_dir():
            raise SecurityError(f"Path is not a directory: {directory}")

        real_dir = str(dir_path.resolve())
        self.allowed_directories.add(real_dir)

        log_info(f"Added allowed directory: {real_dir}")

    def is_within_project(self, file_path: str) -> bool:
        """
        Check if file path is within project boundaries.

        Args:
            file_path: File path to check

        Returns:
            True if path is within allowed boundaries
        """
        try:
            if not file_path:
                log_warning("Empty file path provided to boundary check")
                return False

            # Resolve real path to handle symlinks
            real_path = str(Path(file_path).resolve())

            # Check against all allowed directories
            for allowed_dir in self.allowed_directories:
                # Use pathlib to check if path is within allowed directory
                try:
                    Path(real_path).relative_to(Path(allowed_dir))
                    log_debug(f"File path within boundaries: {file_path}")
                    return True
                except ValueError:
                    # Path is not within this allowed directory, continue checking
                    continue

            log_warning(f"File path outside boundaries: {file_path} -> {real_path}")
            return False

        except Exception as e:
            log_warning(f"Boundary check error for {file_path}: {e}")
            return False

    def get_relative_path(self, file_path: str) -> str | None:
        """
        Get relative path from project root if within boundaries.

        Args:
            file_path: File path to convert

        Returns:
            Relative path from project root, or None if outside boundaries
        """
        if not self.is_within_project(file_path):
            return None

        try:
            real_path = Path(file_path).resolve()
            try:
                rel_path = real_path.relative_to(Path(self.project_root))
                rel_path = str(rel_path)
            except ValueError:
                # Path is not relative to project root
                log_warning(f"Path not relative to project root: {file_path}")
                return None

            # Ensure relative path doesn't start with ..
            if rel_path.startswith(".."):
                log_warning(f"Relative path calculation failed: {rel_path}")
                return None

            return rel_path

        except Exception as e:
            log_warning(f"Relative path calculation error: {e}")
            return None

    def validate_and_resolve_path(self, file_path: str) -> str | None:
        """
        Validate path and return resolved absolute path if within boundaries.

        Args:
            file_path: File path to validate and resolve

        Returns:
            Resolved absolute path if valid, None otherwise
        """
        try:
            # Handle relative paths from project root
            file_path_obj = Path(file_path)
            if not file_path_obj.is_absolute():
                full_path = Path(self.project_root) / file_path
            else:
                full_path = file_path_obj

            # Check boundaries
            if not self.is_within_project(str(full_path)):
                return None

            # Return real path
            return str(full_path.resolve())

        except Exception as e:
            log_warning(f"Path validation error: {e}")
            return None

    def list_allowed_directories(self) -> set[str]:
        """
        Get list of all allowed directories.

        Returns:
            Set of allowed directory paths
        """
        return self.allowed_directories.copy()

    def is_symlink_safe(self, file_path: str) -> bool:
        """
        Check if file path is safe from symlink attacks.

        Args:
            file_path: File path to check

        Returns:
            True if path is safe from symlink attacks
        """
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                return True  # Non-existent files are safe

            # If the fully resolved path is within project boundaries, we treat it as safe.
            # This makes the check tolerant to system-level symlinks like
            # /var -> /private/var on macOS runners.
            resolved = str(file_path_obj.resolve())
            if self.is_within_project(resolved):
                return True

            # Otherwise, inspect each path component symlink to ensure no hop jumps outside
            # the allowed directories.
            path_parts = file_path_obj.parts
            current_path = Path()

            for part in path_parts:
                current_path = current_path / part if current_path.parts else Path(part)

                if current_path.is_symlink():
                    target = str(current_path.resolve())
                    if not self.is_within_project(target):
                        log_warning(
                            f"Unsafe symlink detected: {current_path} -> {target}"
                        )
                        return False

            # If no unsafe hop found, consider safe
            return True

        except Exception as e:
            log_warning(f"Symlink safety check error: {e}")
            return False

    def audit_access(self, file_path: str, operation: str) -> None:
        """
        Log file access for security auditing.

        Args:
            file_path: File path being accessed
            operation: Type of operation (read, write, analyze, etc.)
        """
        is_within = self.is_within_project(file_path)
        status = "ALLOWED" if is_within else "DENIED"

        log_info(f"AUDIT: {status} {operation} access to {file_path}")

        if not is_within:
            log_warning(f"SECURITY: Unauthorized access attempt to {file_path}")

    def __str__(self) -> str:
        """String representation of boundary manager."""
        return f"ProjectBoundaryManager(root={self.project_root}, allowed_dirs={len(self.allowed_directories)})"

    def __repr__(self) -> str:
        """Detailed representation of boundary manager."""
        return (
            f"ProjectBoundaryManager("
            f"project_root='{self.project_root}', "
            f"allowed_directories={self.allowed_directories}"
            f")"
        )
