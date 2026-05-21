#!/usr/bin/env python3
"""
Security Validator for Tree-sitter Analyzer

Provides unified security validation framework inspired by code-index-mcp's
ValidationHelper but enhanced for tree-sitter analyzer's requirements.
"""

import platform
import re
import stat
from pathlib import Path

try:
    import ctypes
    from ctypes import wintypes

    HAS_CTYPES = True
except ImportError:
    HAS_CTYPES = False

from ..exceptions import SecurityError
from ..utils import log_debug, log_warning
from .boundary_manager import ProjectBoundaryManager
from .regex_checker import RegexSafetyChecker

# Cache OS info at module level
IS_WINDOWS = platform.system() == "Windows"
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


def _ctypes_reparse_check(path: Path) -> bool | None:
    """Return reparse-point status via the Windows ctypes call, or ``None`` if unsupported.

    r37ay: extracted from ``_is_junction_or_reparse_point`` to flatten its
    nesting. ``None`` means "call didn't succeed, try the next method";
    a bool means "definitive answer, use it."
    """
    try:
        _kernel32 = getattr(ctypes, "windll", None)
        if not _kernel32:
            return None
        _GetFileAttributesW = _kernel32.kernel32.GetFileAttributesW
        _GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        _GetFileAttributesW.restype = wintypes.DWORD
        attributes = _GetFileAttributesW(str(path))
        if attributes == INVALID_FILE_ATTRIBUTES:
            return None
        return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)
    except (AttributeError, OSError):
        return None


def _matches_temp_file_pattern(file_name: str) -> bool:
    """Return True for filenames that look like test/temp artifacts.

    r37ay: extracted from ``_check_test_environment_access`` so the
    list of accepted patterns reads as data, not deep boolean nesting.
    """
    if file_name.startswith(("tmp", "temp")):
        return True
    if "_test_" in file_name:
        return True
    if file_name.endswith(("_test.py", "_test.js", ".tmp")):
        return True
    return False


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
        self.boundary_manager: ProjectBoundaryManager | None

        # Ensure project_root is properly resolved if provided
        if project_root:
            try:
                resolved_root = str(Path(project_root).resolve())
                self.boundary_manager = ProjectBoundaryManager(resolved_root)
                log_debug(
                    f"SecurityValidator initialized with resolved project_root: {resolved_root}"
                )
            except Exception as e:
                log_warning(
                    f"Failed to initialize ProjectBoundaryManager with {project_root}: {e}"
                )
                self.boundary_manager = None
        else:
            self.boundary_manager = None

        self.regex_checker = RegexSafetyChecker()

        log_debug(f"SecurityValidator initialized with project_root: {project_root}")

    def validate_file_path(
        self, file_path: str, base_path: str | None = None
    ) -> tuple[bool, str]:
        """Validate file path with comprehensive security checks.

        Implements multi-layer defense against path traversal attacks
        and ensures file access stays within project boundaries.

        r37ay (dogfood): the original 131-line body had every layer
        inlined. Refactor preserves all 7 layers (each name-tagged) but
        delegates Layer 7's two-pass symlink/junction sweep to
        ``_validate_symlinks_and_junctions``. NO security semantics
        changed — every check, every short-circuit, every log line is
        preserved. Layer-by-layer regression tests live under
        tests/unit/security/.
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
            is_valid, error = self._validate_windows_drive_letter(file_path)
            if not is_valid:
                return False, error

            # Layer 4: Absolute path security validation
            if Path(file_path).is_absolute() or file_path.startswith(("/", "\\")):
                is_valid, error = self._validate_absolute_path(file_path)
                if not is_valid:
                    return False, error

            # Layer 5: Path normalization and traversal check
            is_valid, error = self._validate_path_traversal(file_path)
            if not is_valid:
                return False, error

            # Layer 6: Project boundary validation
            is_valid, error = self._validate_project_boundary(file_path, base_path)
            if not is_valid:
                return False, error

            # Layer 7: Symbolic link and junction check (original + full path)
            is_valid, error = self._validate_symlinks_and_junctions(
                file_path, base_path
            )
            if not is_valid:
                return False, error

            log_debug(f"File path validation passed: {file_path}")
            return True, ""

        except Exception as e:
            log_warning(f"File path validation error: {e}")
            return False, f"Validation error: {str(e)}"

    def _validate_symlinks_and_junctions(
        self, file_path: str, base_path: str | None
    ) -> tuple[bool, str]:
        """Layer 7: reject symbolic links, Windows junctions, and reparse points.

        Two passes:
          1. The raw ``file_path`` (the user's input as-is).
          2. The resolved full path: ``base_path / normalized(file_path)`` when
             ``base_path`` is provided, else the raw ``Path(file_path)``.
        Parent-directory junctions are then checked on the full path.

        Returns ``(True, "")`` on accept; ``(False, msg)`` on first reject.
        r37ay: extracted from ``validate_file_path``; behaviour preserved.
        """
        original_path = Path(file_path)

        # Pass 1: scan the raw input itself.
        is_valid, error = self._scan_path_for_symlinks_and_junctions(
            original_path, label="original"
        )
        if not is_valid:
            return False, error

        # Pass 2: scan the full (base_path + file_path) path when base_path given.
        if base_path:
            norm_path = str(original_path)
            full_path = Path(base_path) / norm_path
            is_valid, error = self._scan_path_for_symlinks_and_junctions(
                full_path, label="full"
            )
            if not is_valid:
                return False, error
        else:
            # No base_path → reuse the original_path for the parent-dir sweep.
            full_path = original_path

        # Pass 3: parent-directory junction sweep on the resolved full path.
        return self._reject_if_parent_has_junction(full_path)

    def _scan_path_for_symlinks_and_junctions(
        self, path_obj: Path, *, label: str
    ) -> tuple[bool, str]:
        """Reject ``path_obj`` if it's a symlink, junction, or reparse point.

        Permission / OS errors are swallowed — we fall through to the
        caller's next layer (matching the pre-refactor behaviour). ``label``
        is used in the warning so we can tell "original" vs "full" pass.
        """
        try:
            if label == "original":
                log_debug(f"Checking symlink status for original path: {path_obj}")
                is_symlink = path_obj.is_symlink()
                log_debug(f"original_path.is_symlink() = {is_symlink}")
                if is_symlink:
                    log_warning(f"Symbolic link detected in original path: {path_obj}")
                    return False, "Symbolic links are not allowed"
                if path_obj.exists() and self._is_junction_or_reparse_point(path_obj):
                    log_warning(
                        f"Junction or reparse point detected in original path: {path_obj}"
                    )
                    return False, "Junctions and reparse points are not allowed"
                return True, ""

            # label == "full"
            if path_obj.is_symlink():
                log_warning(f"Symbolic link detected: {path_obj}")
                return False, "Symbolic links are not allowed"
            if path_obj.exists() and self._is_junction_or_reparse_point(path_obj):
                log_warning(f"Junction or reparse point detected: {path_obj}")
                return False, "Junctions and reparse points are not allowed"
            return True, ""

        except (OSError, PermissionError) as e:
            if label == "original":
                log_debug(f"Exception checking symlink status: {e}")
            else:
                log_warning(f"Cannot verify symlink status for: {path_obj}")
            # Pre-refactor behaviour: swallow + continue.
            return True, ""

    def _reject_if_parent_has_junction(self, full_path: Path) -> tuple[bool, str]:
        """Walk parent dirs for junctions/reparse points. OS errors → accept."""
        try:
            if self._has_junction_in_path(full_path):
                log_warning(f"Junction detected in path hierarchy: {full_path}")
                return False, "Paths containing junctions are not allowed"
        except (OSError, PermissionError):
            # Pre-refactor behaviour: swallow + continue.
            pass
        return True, ""

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

    def validate_path(
        self, path: str, base_path: str | None = None
    ) -> tuple[bool, str]:
        """
        Alias for validate_file_path for backward compatibility.

        Args:
            path: Path to validate
            base_path: Optional base path for relative path validation

        Returns:
            Tuple of (is_valid, error_message)
        """
        return self.validate_file_path(path, base_path)

    def is_safe_path(self, path: str, base_path: str | None = None) -> bool:
        """
        Check if a path is safe (backward compatibility method).

        Args:
            path: Path to check
            base_path: Optional base path for relative path validation

        Returns:
            True if path is safe, False otherwise
        """
        is_valid, _ = self.validate_file_path(path, base_path)
        return is_valid

    def _is_junction_or_reparse_point(self, path: Path) -> bool:
        """Check if a path is a Windows junction or reparse point.

        r37ay: split into two helpers (``_ctypes_reparse_check`` + stat
        fallback) so nesting drops from 7 to ≤3. Behaviour preserved —
        we still try ctypes first, then stat, then return False.
        """
        if not IS_WINDOWS:
            return False

        try:
            if HAS_CTYPES:
                ctypes_result = _ctypes_reparse_check(path)
                if ctypes_result is not None:
                    return ctypes_result

            if path.exists():
                path_stat = path.stat()
                return bool(
                    getattr(path_stat, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                )
        except Exception:
            # If any error occurs, assume it's not a junction for safety.
            return False

        return False

    def _has_junction_in_path(self, path: Path) -> bool:
        """
        Check if any parent directory in the path is a junction.

        Args:
            path: Path to check

        Returns:
            True if any parent directory is a junction
        """
        try:
            current_path = path.resolve() if path.exists() else path

            # Check each parent directory
            for parent in current_path.parents:
                if self._is_junction_or_reparse_point(parent):
                    return True

        except Exception:
            # If any error occurs, assume no junctions for safety
            pass  # nosec

        return False

    def _validate_windows_drive_letter(self, file_path: str) -> tuple[bool, str]:
        """
        Validate Windows drive letter on non-Windows systems.

        Args:
            file_path: File path to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        import platform

        if (
            len(file_path) > 1
            and file_path[1] == ":"
            and platform.system() != "Windows"
        ):
            return (
                False,
                f"Windows drive letters are not allowed on {platform.system()} system",
            )

        return True, ""

    def _validate_absolute_path(self, file_path: str) -> tuple[bool, str]:
        """
        Validate absolute path with project boundary and test environment checks.

        Args:
            file_path: Absolute file path to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        log_debug(f"Processing absolute path: {file_path}")

        # Check project boundaries first (highest priority)
        if self.boundary_manager and self.boundary_manager.project_root:
            if not self.boundary_manager.is_within_project(file_path):
                return False, "Absolute path must be within project directory"
            log_debug("Absolute path is within project boundaries")
            return True, ""

        # If no project boundaries, check test environment allowances
        is_test_allowed, error = self._check_test_environment_access(file_path)
        if not is_test_allowed:
            return False, error

        log_debug("Absolute path allowed in test environment")
        return True, ""

    def _check_test_environment_access(self, file_path: str) -> tuple[bool, str]:
        """Check if absolute path access is allowed in test/development environment.

        Allows access to system temporary directories when no project boundaries
        are configured, which is common in test environments.

        r37ay (dogfood): tool flagged this at nesting depth 8 (L547). Splits the
        body into 3 helpers: env detection, temp-dir membership, fallback temp
        sandbox. Behaviour preserved.
        """
        import tempfile

        try:
            if self._is_test_environment_active():
                log_debug("Test environment detected - allowing temporary file access")
                if self._path_under_test_temp_dirs(file_path):
                    return True, ""
                if _matches_temp_file_pattern(Path(file_path).name):
                    log_debug(
                        "Temporary test file pattern detected - allowed in test environment"
                    )
                    return True, ""

            # Fallback to original temp directory check.
            temp_dir = Path(tempfile.gettempdir()).resolve()
            real_path = Path(file_path).resolve()
            log_debug(f"Checking test environment access: {real_path} under {temp_dir}")
            real_path.relative_to(temp_dir)
            log_debug(
                "Path is under system temp directory - allowed in test environment"
            )
            return True, ""

        except ValueError:
            return False, "Absolute file paths are not allowed"
        except Exception as e:
            log_debug(f"Error in test environment check: {e}")
            return False, "Absolute file paths are not allowed"

    @staticmethod
    def _is_test_environment_active() -> bool:
        """Return True if pytest/CI/GitHub-Actions/test-arg env markers are present."""
        import os

        if "pytest" in os.environ.get("_", ""):
            return True
        if "PYTEST_CURRENT_TEST" in os.environ:
            return True
        if "CI" in os.environ:
            return True
        if "GITHUB_ACTIONS" in os.environ:
            return True
        argv = getattr(getattr(os, "sys", None), "argv", [])
        if hasattr(os, "sys") and any("test" in arg.lower() for arg in argv):
            return True
        return False

    def _path_under_test_temp_dirs(self, file_path: str) -> bool:
        """Return True if ``file_path`` resolves under any common temp directory."""
        import tempfile

        candidate_dirs = [Path(tempfile.gettempdir()).resolve()]
        for raw in ("/tmp", "/var/tmp"):  # nosec — sandbox allowlist
            p = Path(raw)
            if p.exists():
                candidate_dirs.append(p.resolve())

        real_path = Path(file_path).resolve()
        log_debug(f"Checking test environment access: {real_path}")
        for temp_dir in candidate_dirs:
            if not temp_dir.exists():
                continue
            try:
                real_path.relative_to(temp_dir)
                log_debug(
                    f"Path is under temp directory {temp_dir} - allowed in test environment"
                )
                return True
            except ValueError:
                continue
        return False

    def _validate_path_traversal(self, file_path: str) -> tuple[bool, str]:
        """
        Validate file path for directory traversal attempts.

        Args:
            file_path: File path to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        norm_path = str(Path(file_path))

        # Check for various path traversal patterns
        traversal_patterns = ["..\\", "../", ".."]

        if any(
            pattern in norm_path for pattern in traversal_patterns[:2]
        ) or norm_path.startswith(traversal_patterns[2]):
            log_warning(f"Path traversal attempt detected: {file_path} -> {norm_path}")
            return False, "Directory traversal not allowed"

        return True, ""

    def _validate_project_boundary(
        self, file_path: str, base_path: str | None
    ) -> tuple[bool, str]:
        """
        Validate file path against project boundaries when base_path is provided.

        Args:
            file_path: File path to validate
            base_path: Base path for relative path validation

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not (self.boundary_manager and base_path):
            return True, ""

        norm_path = str(Path(file_path))
        full_path = str(Path(base_path) / norm_path)

        if not self.boundary_manager.is_within_project(full_path):
            return (False, "Access denied. File path must be within project directory")

        return True, ""
