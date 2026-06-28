"""Security-related exception types."""

from pathlib import Path
from typing import Any

from .core import TreeSitterAnalyzerError


class SecurityError(TreeSitterAnalyzerError):
    """Raised when security validation fails."""

    def __init__(
        self,
        message: str,
        security_type: str | None = None,
        file_path: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if security_type:
            context["security_type"] = security_type
        if file_path:
            context["file_path"] = str(file_path)

        super().__init__(message, context=context, **kwargs)
        self.security_type = security_type
        self.file_path = str(file_path) if file_path else None


class PathTraversalError(SecurityError):
    """Raised when path traversal attack is detected."""

    def __init__(
        self,
        message: str,
        attempted_path: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if attempted_path:
            context["attempted_path"] = attempted_path

        super().__init__(
            message, security_type="path_traversal", context=context, **kwargs
        )
        self.attempted_path = attempted_path


class RegexSecurityError(SecurityError):
    """Raised when unsafe regex pattern is detected."""

    def __init__(
        self,
        message: str,
        pattern: str | None = None,
        dangerous_construct: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if pattern:
            context["pattern"] = pattern
        if dangerous_construct:
            context["dangerous_construct"] = dangerous_construct

        super().__init__(
            message, security_type="regex_security", context=context, **kwargs
        )
        self.pattern = pattern
        self.dangerous_construct = dangerous_construct


class FileRestrictionError(SecurityError):
    """Raised when file access is restricted by mode or security policy."""

    def __init__(
        self,
        message: str,
        file_path: str | Path | None = None,
        current_mode: str | None = None,
        allowed_patterns: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if current_mode:
            context["current_mode"] = current_mode
        if allowed_patterns:
            context["allowed_patterns"] = allowed_patterns

        super().__init__(
            message,
            security_type="file_restriction",
            file_path=file_path,
            context=context,
            **kwargs,
        )
        self.current_mode = current_mode
        self.allowed_patterns = allowed_patterns
