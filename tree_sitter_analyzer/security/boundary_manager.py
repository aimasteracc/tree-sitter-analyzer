#!/usr/bin/env python3
"""
Project Boundary Manager for Tree-sitter Analyzer

Provides strict project boundary control to prevent access to files
outside the designated project directory.
"""

import os
from pathlib import Path
from typing import Optional, Set

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
        
        if not os.path.exists(project_root):
            raise SecurityError(f"Project root does not exist: {project_root}")
        
        if not os.path.isdir(project_root):
            raise SecurityError(f"Project root is not a directory: {project_root}")
        
        # Store real path to prevent symlink attacks
        self.project_root = os.path.realpath(project_root)
        self.allowed_directories: Set[str] = {self.project_root}
        
        log_info(f"ProjectBoundaryManager initialized with root: {self.project_root}")

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
        
        if not os.path.exists(directory):
            raise SecurityError(f"Directory does not exist: {directory}")
        
        if not os.path.isdir(directory):
            raise SecurityError(f"Path is not a directory: {directory}")
        
        real_dir = os.path.realpath(directory)
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
            real_path = os.path.realpath(file_path)
            
            # Check against all allowed directories
            for allowed_dir in self.allowed_directories:
                if real_path.startswith(allowed_dir + os.sep) or real_path == allowed_dir:
                    log_debug(f"File path within boundaries: {file_path}")
                    return True
            
            log_warning(f"File path outside boundaries: {file_path} -> {real_path}")
            return False
            
        except Exception as e:
            log_warning(f"Boundary check error for {file_path}: {e}")
            return False

    def get_relative_path(self, file_path: str) -> Optional[str]:
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
            real_path = os.path.realpath(file_path)
            rel_path = os.path.relpath(real_path, self.project_root)
            
            # Ensure relative path doesn't start with ..
            if rel_path.startswith(".."):
                log_warning(f"Relative path calculation failed: {rel_path}")
                return None
            
            return rel_path
            
        except Exception as e:
            log_warning(f"Relative path calculation error: {e}")
            return None

    def validate_and_resolve_path(self, file_path: str) -> Optional[str]:
        """
        Validate path and return resolved absolute path if within boundaries.
        
        Args:
            file_path: File path to validate and resolve
            
        Returns:
            Resolved absolute path if valid, None otherwise
        """
        try:
            # Handle relative paths from project root
            if not os.path.isabs(file_path):
                full_path = os.path.join(self.project_root, file_path)
            else:
                full_path = file_path
            
            # Check boundaries
            if not self.is_within_project(full_path):
                return None
            
            # Return real path
            return os.path.realpath(full_path)
            
        except Exception as e:
            log_warning(f"Path validation error: {e}")
            return None

    def list_allowed_directories(self) -> Set[str]:
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
            if not os.path.exists(file_path):
                return True  # Non-existent files are safe
            
            # Check if any component in the path is a symlink
            path_parts = Path(file_path).parts
            current_path = ""
            
            for part in path_parts:
                current_path = os.path.join(current_path, part) if current_path else part
                
                if os.path.islink(current_path):
                    # Check if symlink target is within boundaries
                    target = os.path.realpath(current_path)
                    if not self.is_within_project(target):
                        log_warning(f"Unsafe symlink detected: {current_path} -> {target}")
                        return False
            
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
