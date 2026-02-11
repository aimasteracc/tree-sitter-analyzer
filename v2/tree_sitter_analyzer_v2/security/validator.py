"""
Security validator for validating file paths, regexes, and resource limits.

This module provides security validation to prevent:
- Path traversal attacks
- Access outside project boundaries
- ReDoS (Regular expression Denial of Service)
- Excessive resource consumption
"""

import re
import signal
from pathlib import Path
from typing import Any


class SecurityValidator:
    """
    Security validator for file access and regex patterns.

    Validates file paths to prevent path traversal and ensures
    regex patterns are safe from ReDoS attacks.
    """

    # Known dangerous regex patterns (nested quantifiers and alternation)
    DANGEROUS_REGEX_PATTERNS = [
        r"\([^)]*\+\)[*+]",  # (a+)+ or (a+)*
        r"\([^)]*\*\)[*+]",  # (a*)+ or (a*)*
        r"\([^)]*\+\)\+",  # (a+)+
        r"\([^)]*\*\)\*",  # (a*)*
        r"\(\.\*\)[*+]",  # (.*)+  or (.*)*
        r"\([^)]*\|[^)]*\)[*+]",  # (a|b)* or (a|b)+ - alternation with quantifiers
        r"\([^)]*\+[^)]*\+[^)]*\)[*+]",  # (x+x+)* - multiple quantifiers inside
    ]

    def __init__(
        self,
        project_root: str,
        max_file_size: int = 50 * 1024 * 1024,  # 50MB default
    ):
        """
        Initialize security validator.

        Args:
            project_root: Root directory of the project
            max_file_size: Maximum allowed file size in bytes (default: 50MB)
        """
        self.project_root = Path(project_root).resolve()
        self.max_file_size = max_file_size

    def validate_file_path(self, file_path: str) -> dict[str, Any]:
        """
        Validate file path for security.

        Checks:
        - Path is within project boundaries
        - No path traversal attempts
        - File size within limits (if file exists)
        - Symlinks don't escape project

        Args:
            file_path: File path to validate

        Returns:
            Dictionary with:
                - valid: True if path is safe, False otherwise
                - normalized_path: Normalized absolute path (if valid)
                - error: Error message (if not valid)
        """
        try:
            # Convert to Path object
            path = Path(file_path)

            # Resolve to absolute path (follows symlinks)
            if path.is_absolute():
                resolved_path = path.resolve()
            else:
                # Relative path - resolve relative to project root
                resolved_path = (self.project_root / path).resolve()

            # Check if path is within project boundaries
            try:
                resolved_path.relative_to(self.project_root)
            except ValueError:
                return {
                    "valid": False,
                    "error": (
                        f"Path is outside project boundaries. "
                        f"Path: {resolved_path}, Project root: {self.project_root}"
                    ),
                }

            # Check file size if file exists
            if resolved_path.exists() and resolved_path.is_file():
                file_size = resolved_path.stat().st_size
                if file_size > self.max_file_size:
                    return {
                        "valid": False,
                        "error": (
                            f"File too large: {file_size:,} bytes "
                            f"(max: {self.max_file_size:,} bytes)"
                        ),
                    }

            return {"valid": True, "normalized_path": str(resolved_path)}

        except Exception as e:
            return {"valid": False, "error": f"Path validation error: {str(e)}"}

    def validate_regex(
        self, pattern: str, test_string: str | None = None, timeout_seconds: float = 0.1
    ) -> dict[str, Any]:
        """
        Validate regex pattern for safety.

        Checks for:
        - Invalid regex syntax
        - Known ReDoS patterns (nested quantifiers)
        - Execution timeout (catastrophic backtracking)

        Args:
            pattern: Regex pattern to validate
            test_string: Optional test string to check execution time
            timeout_seconds: Timeout for regex execution test

        Returns:
            Dictionary with:
                - valid: True if pattern is safe, False otherwise
                - error: Error message (if not valid)
                - timeout: True if pattern timed out (if applicable)
        """
        # Empty pattern is safe
        if not pattern:
            return {"valid": True}

        # Check regex syntax
        try:
            compiled = re.compile(pattern)
        except re.error as e:
            return {"valid": False, "error": f"Invalid regex syntax: {str(e)}"}

        # Check for known dangerous patterns
        for dangerous_pattern in self.DANGEROUS_REGEX_PATTERNS:
            if re.search(dangerous_pattern, pattern):
                return {
                    "valid": False,
                    "error": (
                        "Potentially dangerous regex pattern detected "
                        "(nested quantifiers can cause ReDoS)"
                    ),
                }

        # If test string provided, test execution time
        if test_string is not None:
            try:
                # Test with timeout (Unix-like systems)
                if hasattr(signal, "SIGALRM"):

                    def timeout_handler(signum: int, frame: Any) -> None:
                        raise TimeoutError("Regex execution timeout")

                    # Set timeout
                    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)  # type: ignore[attr-defined]

                    try:
                        compiled.search(test_string)
                    finally:
                        # Disable alarm
                        signal.setitimer(signal.ITIMER_REAL, 0)  # type: ignore[attr-defined]
                        signal.signal(signal.SIGALRM, old_handler)
                else:
                    # Windows or other systems - just try and see
                    # (no timeout mechanism, rely on pattern detection)
                    compiled.search(test_string)

            except TimeoutError:
                return {
                    "valid": False,
                    "error": "Regex execution timeout (potential ReDoS)",
                    "timeout": True,
                }
            except Exception as e:
                return {"valid": False, "error": f"Regex execution error: {str(e)}"}

        return {"valid": True}
