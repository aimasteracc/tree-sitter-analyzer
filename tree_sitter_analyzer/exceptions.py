#!/usr/bin/env python3
"""
Tree-sitter Analyzer Custom Exceptions

Unified exception handling system for consistent error management
across the entire framework.
"""

from pathlib import Path
from typing import Any


class TreeSitterAnalyzerError(Exception):
    """Base exception for all tree-sitter analyzer errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.context = context or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary format."""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context,
        }


class AnalysisError(TreeSitterAnalyzerError):
    """Raised when file analysis fails."""

    def __init__(
        self,
        message: str,
        file_path: str | Path | None = None,
        language: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if file_path:
            context["file_path"] = str(file_path)
        if language:
            context["language"] = language
        super().__init__(message, context=context, **kwargs)


class ParseError(TreeSitterAnalyzerError):
    """Raised when parsing fails."""

    def __init__(
        self,
        message: str,
        language: str | None = None,
        source_info: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if language:
            context["language"] = language
        if source_info:
            context.update(source_info)
        super().__init__(message, context=context, **kwargs)


class LanguageNotSupportedError(TreeSitterAnalyzerError):
    """Raised when a language is not supported."""

    def __init__(
        self, language: str, supported_languages: list[str] | None = None, **kwargs: Any
    ) -> None:
        message = f"Language '{language}' is not supported"
        context = kwargs.get("context", {})
        context["language"] = language
        if supported_languages:
            context["supported_languages"] = supported_languages
            message += f". Supported languages: {', '.join(supported_languages)}"
        super().__init__(message, context=context, **kwargs)


class PluginError(TreeSitterAnalyzerError):
    """Raised when plugin operations fail."""

    def __init__(
        self,
        message: str,
        plugin_name: str | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if plugin_name:
            context["plugin_name"] = plugin_name
        if operation:
            context["operation"] = operation
        super().__init__(message, context=context, **kwargs)


class QueryError(TreeSitterAnalyzerError):
    """Raised when query execution fails."""

    def __init__(
        self,
        message: str,
        query_name: str | None = None,
        query_string: str | None = None,
        language: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if query_name:
            context["query_name"] = query_name
        if query_string:
            context["query_string"] = query_string
        if language:
            context["language"] = language
        super().__init__(message, context=context, **kwargs)


class FileHandlingError(TreeSitterAnalyzerError):
    """Raised when file operations fail."""

    def __init__(
        self,
        message: str,
        file_path: str | Path | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if file_path:
            context["file_path"] = str(file_path)
        if operation:
            context["operation"] = operation
        super().__init__(message, context=context, **kwargs)


class ConfigurationError(TreeSitterAnalyzerError):
    """Raised when configuration is invalid."""

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
        config_value: Any | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if config_key:
            context["config_key"] = config_key
        if config_value is not None:
            context["config_value"] = config_value
        super().__init__(message, context=context, **kwargs)


class ValidationError(TreeSitterAnalyzerError):
    """Raised when validation fails."""

    def __init__(
        self,
        message: str,
        validation_type: str | None = None,
        invalid_value: Any | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if validation_type:
            context["validation_type"] = validation_type
        if invalid_value is not None:
            context["invalid_value"] = invalid_value
        super().__init__(message, context=context, **kwargs)


class MCPError(TreeSitterAnalyzerError):
    """Raised when MCP operations fail."""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        resource_uri: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if tool_name:
            context["tool_name"] = tool_name
        if resource_uri:
            context["resource_uri"] = resource_uri
        super().__init__(message, context=context, **kwargs)


# Exception handling utilities
def handle_exception(
    exception: Exception,
    context: dict[str, Any] | None = None,
    reraise_as: type[Exception] | None = None,
) -> None:
    """
    Handle exceptions with optional context and re-raising.

    Args:
        exception: The original exception
        context: Additional context information
        reraise_as: Exception class to re-raise as
    """
    from .utils import log_error

    # Log the original exception
    error_context = context or {}
    if hasattr(exception, "context"):
        error_context.update(exception.context)

    log_error(f"Exception handled: {exception}", extra=error_context)

    # Re-raise as different exception type if requested
    if reraise_as and not isinstance(exception, reraise_as):
        if issubclass(reraise_as, TreeSitterAnalyzerError):
            raise reraise_as(str(exception), context=error_context)
        else:
            raise reraise_as(str(exception))

    # Re-raise original exception
    raise exception


def safe_execute(
    func: Any,
    *args: Any,
    default_return: Any = None,
    exception_types: tuple[type[Exception], ...] = (Exception,),
    log_errors: bool = True,
    **kwargs: Any,
) -> Any:
    """
    Safely execute a function with exception handling.

    Args:
        func: Function to execute
        *args: Function arguments
        default_return: Value to return on exception
        exception_types: Exception types to catch
        log_errors: Whether to log errors
        **kwargs: Function keyword arguments

    Returns:
        Function result or default_return on exception
    """
    try:
        return func(*args, **kwargs)
    except exception_types as e:
        if log_errors:
            from .utils import log_error

            log_error(f"Safe execution failed for {func.__name__}: {e}")
        return default_return


def create_error_response(
    exception: Exception, include_traceback: bool = False
) -> dict[str, Any]:
    """
    Create standardized error response dictionary.

    Args:
        exception: The exception to convert
        include_traceback: Whether to include traceback

    Returns:
        Error response dictionary
    """
    import traceback

    response: dict[str, Any] = {
        "success": False,
        "error": {"type": exception.__class__.__name__, "message": str(exception)},
    }

    # Add context if available
    if hasattr(exception, "context"):
        response["error"]["context"] = exception.context

    # Add error code if available
    if hasattr(exception, "error_code"):
        response["error"]["code"] = exception.error_code

    # Add traceback if requested
    if include_traceback:
        response["error"]["traceback"] = traceback.format_exc()

    return response


# Decorator for exception handling
def handle_exceptions(
    default_return: Any = None,
    exception_types: tuple[type[Exception], ...] = (Exception,),
    reraise_as: type[Exception] | None = None,
    log_errors: bool = True,
) -> Any:
    """
    Decorator for automatic exception handling.

    Args:
        default_return: Value to return on exception
        exception_types: Exception types to catch
        reraise_as: Exception class to re-raise as
        log_errors: Whether to log errors
    """

    def decorator(func: Any) -> Any:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except exception_types as e:
                if log_errors:
                    from .utils import log_error

                    log_error(f"Exception in {func.__name__}: {e}")

                if reraise_as:
                    if issubclass(reraise_as, TreeSitterAnalyzerError):
                        raise reraise_as(str(e)) from e
                    else:
                        raise reraise_as(str(e)) from e

                return default_return

        return wrapper

    return decorator


class SecurityError(TreeSitterAnalyzerError):
    """Raised when security validation fails."""

    def __init__(
        self,
        message: str,
        security_type: str | None = None,
        file_path: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
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
        context = kwargs.get("context", {})
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
        context = kwargs.get("context", {})
        if pattern:
            context["pattern"] = pattern
        if dangerous_construct:
            context["dangerous_construct"] = dangerous_construct

        super().__init__(
            message, security_type="regex_security", context=context, **kwargs
        )
        self.pattern = pattern
        self.dangerous_construct = dangerous_construct
