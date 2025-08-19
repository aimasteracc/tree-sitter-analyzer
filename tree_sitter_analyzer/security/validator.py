#!/usr/bin/env python3
"""
Security Validator for Tree-sitter Analyzer

Provides unified security validation framework inspired by code-index-mcp's
ValidationHelper but enhanced for tree-sitter analyzer's requirements.
"""

import re
from pathlib import Path

from ..exceptions import SecurityError
from ..utils import log_debug, log_warning
from .boundary_manager import ProjectBoundaryManager
from .regex_checker import RegexSafetyChecker


class SecurityValidator:
    """
    Unified security validation framework.

    This class provides comprehensive security validation for file paths,
    regex patterns, and other user inputs to prevent security vulnerabilities.

    Features:
    - Multi-layer path traversal protection
    - Project boundary enforcement
    - ReDoS attack prevention
    - Input sanitization
    """

    def __init__(self, project_root: str | None = None) -> None:
        """
        Initialize security validator.

        Args:
            project_root: Optional project root directory for boundary checks
        """
        self.boundary_manager = (
            ProjectBoundaryManager(project_root) if project_root else None
        )
        self.regex_checker = RegexSafetyChecker()

        log_debug(f"SecurityValidator initialized with project_root: {project_root}")

    def validate_file_path(
        self, file_path: str, base_path: str | None = None
    ) -> tuple[bool, str]:
        """
        Validate file path with comprehensive security checks.

        Implements multi-layer defense against path traversal attacks
        and ensures file access stays within project boundaries.

        Args:
            file_path: File path to validate
            base_path: Optional base path for relative path validation

        Returns:
            Tuple of (is_valid, error_message)

        Example:
            >>> validator = SecurityValidator("/project/root")
            >>> is_valid, error = validator.validate_file_path("src/main.py")
            >>> assert is_valid
        """
        try:
            # Layer 1: Basic input validation
            if not file_path or not isinstance(file_path, str):
                return False, "File path must be a non-empty string"

            # Layer 2: Null byte injection check
            if "\x00" in file_path:
                log_warning(f"Null byte detected in file path: {file_path}")
                return False, "File path contains null bytes"

            # Layer 3: Windows drive letter check (only on non-Windows systems)
            # Check if we're on Windows by checking for drive letter support
            import platform

            if (
                len(file_path) > 1
                and file_path[1] == ":"
                and platform.system() != "Windows"
            ):
                return False, "Windows drive letters are not allowed on this system"

            # Layer 4: Absolute path check (cross-platform)
            if Path(file_path).is_absolute() or file_path.startswith(("/", "\\")):
                # If project boundaries are configured, enforce them strictly
                if self.boundary_manager and self.boundary_manager.project_root:
                    if not self.boundary_manager.is_within_project(file_path):
                        return False, "Absolute path must be within project directory"
                    # Within project
                    return True, ""
                else:
                    # In test/dev contexts without project boundaries, allow absolute
                    # paths under system temp folder only (safe sandbox)
                    import tempfile

                    temp_dir = Path(tempfile.gettempdir()).resolve()
                    real_path = Path(file_path).resolve()
                    try:
                        real_path.relative_to(temp_dir)
                        return True, ""
                    except ValueError:
                        pass
                    return False, "Absolute file paths are not allowed"

            # Layer 5: Path normalization and traversal check
            norm_path = str(Path(file_path))
            if "..\\" in norm_path or "../" in norm_path or norm_path.startswith(".."):
                log_warning(f"Path traversal attempt detected: {file_path}")
                return False, "Directory traversal not allowed"

            # Layer 6: Project boundary validation
            if self.boundary_manager and base_path:
                if not self.boundary_manager.is_within_project(
                    str(Path(base_path) / norm_path)
                ):
                    return (
                        False,
                        "Access denied. File path must be within project directory",
                    )

            # Layer 7: Symbolic link check (if file exists)
            if base_path:
                full_path = Path(base_path) / norm_path
                if full_path.exists() and full_path.is_symlink():
                    log_warning(f"Symbolic link detected: {full_path}")
                    return False, "Symbolic links are not allowed"

            log_debug(f"File path validation passed: {file_path}")
            return True, ""

        except Exception as e:
            log_warning(f"File path validation error: {e}")
            return False, f"Validation error: {str(e)}"

    def validate_directory_path(
        self, dir_path: str, must_exist: bool = True
    ) -> tuple[bool, str]:
        """
        Validate directory path for security and existence.

        Args:
            dir_path: Directory path to validate
            must_exist: Whether directory must exist

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Basic validation using file path validator
            is_valid, error = self.validate_file_path(dir_path)
            if not is_valid:
                return False, error

            # Check if path exists and is directory
            if must_exist:
                dir_path_obj = Path(dir_path)
                if not dir_path_obj.exists():
                    return False, f"Directory does not exist: {dir_path}"

                if not dir_path_obj.is_dir():
                    return False, f"Path is not a directory: {dir_path}"

            log_debug(f"Directory path validation passed: {dir_path}")
            return True, ""

        except Exception as e:
            log_warning(f"Directory path validation error: {e}")
            return False, f"Validation error: {str(e)}"

    def validate_regex_pattern(self, pattern: str) -> tuple[bool, str]:
        """
        Validate regex pattern for ReDoS attack prevention.

        Args:
            pattern: Regex pattern to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        return self.regex_checker.validate_pattern(pattern)

    def sanitize_input(self, user_input: str, max_length: int = 1000) -> str:
        """
        Sanitize user input by removing dangerous characters.

        Args:
            user_input: Input string to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized input string

        Raises:
            SecurityError: If input is too long or contains dangerous content
        """
        if not isinstance(user_input, str):
            raise SecurityError("Input must be a string")

        if len(user_input) > max_length:
            raise SecurityError(f"Input too long: {len(user_input)} > {max_length}")

        # Remove null bytes and control characters
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", user_input)

        # Remove HTML/XML tags for XSS prevention
        sanitized = re.sub(r"<[^>]*>", "", sanitized)

        # Remove potentially dangerous characters
        sanitized = re.sub(r'[<>"\']', "", sanitized)

        # Log if sanitization occurred
        if sanitized != user_input:
            log_warning("Input sanitization performed")

        return sanitized

    def validate_glob_pattern(self, pattern: str) -> tuple[bool, str]:
        """
        Validate glob pattern for safe file matching.

        Args:
            pattern: Glob pattern to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Basic input validation
            if not pattern or not isinstance(pattern, str):
                return False, "Pattern must be a non-empty string"

            # Check for dangerous patterns
            dangerous_patterns = [
                "..",  # Path traversal
                "//",  # Double slashes
                "\\\\",  # Double backslashes
            ]

            for dangerous in dangerous_patterns:
                if dangerous in pattern:
                    return False, f"Dangerous pattern detected: {dangerous}"

            # Validate length
            if len(pattern) > 500:
                return False, "Pattern too long"

            log_debug(f"Glob pattern validation passed: {pattern}")
            return True, ""

        except Exception as e:
            log_warning(f"Glob pattern validation error: {e}")
            return False, f"Validation error: {str(e)}"
