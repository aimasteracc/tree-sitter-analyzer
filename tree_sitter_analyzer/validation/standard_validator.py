"""Standardized input validation."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    """Result of validation."""
    is_valid: bool
    error: str | None = None
    resolved_path: str | None = None
    value: Any = None


class StandardValidator:
    """Standardized input validator for all tools and commands."""

    ALLOWED_OUTPUT_FORMATS = {"json", "text", "toon", "table", "csv"}

    def validate_file_path(self, path: str | None, allow_absolute: bool = True, project_root: str | None = None) -> ValidationResult:
        """Validate file path for security.

        Args:
            path: The file path to validate
            allow_absolute: Whether to allow absolute paths (currently unused, for future use)
            project_root: Optional project root for relative path resolution (currently unused, for future use)

        Returns:
            ValidationResult with is_valid, error, resolved_path, and value fields
        """
        if not path:
            return ValidationResult(is_valid=False, error="File path is empty")

        if ".." in path:
            return ValidationResult(is_valid=False, error=f"Path traversal not allowed: {path}")

        try:
            path_obj = Path(path)
            resolved = path_obj.resolve()
            resolved_str = str(resolved)

            # Block access to system paths (including macOS /private symlinks)
            system_path_prefixes = [
                "/etc/",
                "/root/",
                "/private/etc/",  # macOS symlink target
                "/private/root/",  # macOS symlink target
            ]
            for prefix in system_path_prefixes:
                if resolved_str.startswith(prefix) or resolved_str == prefix.rstrip("/"):
                    return ValidationResult(is_valid=False, error=f"Access denied to system path: {path}")

            return ValidationResult(is_valid=True, resolved_path=resolved_str, value=path)
        except Exception as e:
            return ValidationResult(is_valid=False, error=str(e))

    def validate_positive_integer(self, value: Any, name: str) -> ValidationResult:
        """Validate that value is a positive integer.

        Args:
            value: The value to validate
            name: The name of the parameter (for error messages)

        Returns:
            ValidationResult with is_valid, error, and value fields
        """
        if not isinstance(value, int):
            return ValidationResult(is_valid=False, error=f"{name} must be an integer, got {type(value).__name__}")
        if value <= 0:
            return ValidationResult(is_valid=False, error=f"{name} must be positive, got {value}")
        return ValidationResult(is_valid=True, value=value)

    def validate_non_negative_integer(self, value: Any, name: str) -> ValidationResult:
        """Validate that value is a non-negative integer (>= 0).

        Args:
            value: The value to validate
            name: The name of the parameter (for error messages)

        Returns:
            ValidationResult with is_valid, error, and value fields
        """
        if not isinstance(value, int):
            return ValidationResult(is_valid=False, error=f"{name} must be an integer, got {type(value).__name__}")
        if value < 0:
            return ValidationResult(is_valid=False, error=f"{name} must be non-negative, got {value}")
        return ValidationResult(is_valid=True, value=value)

    def validate_output_format(self, format_name: str | None) -> ValidationResult:
        """Validate output format name.

        Args:
            format_name: The format name to validate

        Returns:
            ValidationResult with is_valid, error, and value fields (normalized to lowercase)
        """
        if not format_name:
            return ValidationResult(is_valid=False, error="Output format is empty")

        format_lower = format_name.lower()
        if format_lower not in self.ALLOWED_OUTPUT_FORMATS:
            allowed = ", ".join(sorted(self.ALLOWED_OUTPUT_FORMATS))
            return ValidationResult(is_valid=False, error=f"Invalid output format '{format_name}'. Allowed: {allowed}")
        return ValidationResult(is_valid=True, value=format_lower)
