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


# MCP-specific exceptions for enhanced error handling
class MCPToolError(MCPError):
    """Raised when MCP tool execution fails."""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        input_params: dict[str, Any] | None = None,
        execution_stage: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if input_params:
            # Sanitize sensitive information from input params
            sanitized_params = self._sanitize_params(input_params)
            context["input_params"] = sanitized_params
        if execution_stage:
            context["execution_stage"] = execution_stage

        super().__init__(message, tool_name=tool_name, context=context, **kwargs)
        self.input_params = input_params
        self.execution_stage = execution_stage

    @staticmethod
    def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
        """Sanitize sensitive information from parameters."""
        sanitized = {}
        sensitive_keys = {"password", "token", "key", "secret", "auth", "credential"}

        for key, value in params.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, str) and len(value) > 100:
                sanitized[key] = value[:100] + "...[TRUNCATED]"
            else:
                sanitized[key] = value

        return sanitized


class MCPResourceError(MCPError):
    """Raised when MCP resource access fails."""

    def __init__(
        self,
        message: str,
        resource_uri: str | None = None,
        resource_type: str | None = None,
        access_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if resource_type:
            context["resource_type"] = resource_type
        if access_mode:
            context["access_mode"] = access_mode

        super().__init__(message, resource_uri=resource_uri, context=context, **kwargs)
        self.resource_type = resource_type
        self.access_mode = access_mode


class MCPTimeoutError(MCPError):
    """Raised when MCP operation times out."""

    def __init__(
        self,
        message: str,
        timeout_seconds: float | None = None,
        operation_type: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if timeout_seconds:
            context["timeout_seconds"] = timeout_seconds
        if operation_type:
            context["operation_type"] = operation_type

        super().__init__(message, context=context, **kwargs)
        self.timeout_seconds = timeout_seconds
        self.operation_type = operation_type


class MCPValidationError(ValidationError):
    """Raised when MCP input validation fails."""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        parameter_name: str | None = None,
        parameter_value: Any | None = None,
        validation_rule: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.get("context", {})
        if tool_name:
            context["tool_name"] = tool_name
        if parameter_name:
            context["parameter_name"] = parameter_name
        if validation_rule:
            context["validation_rule"] = validation_rule

        # Sanitize parameter value for logging
        if parameter_value is not None:
            if isinstance(parameter_value, str) and len(parameter_value) > 200:
                context["parameter_value"] = parameter_value[:200] + "...[TRUNCATED]"
            else:
                context["parameter_value"] = parameter_value

        super().__init__(
            message, validation_type="mcp_parameter", context=context, **kwargs
        )
        self.tool_name = tool_name
        self.parameter_name = parameter_name
        self.validation_rule = validation_rule


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
        context = kwargs.get("context", {})
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


# Enhanced error response utilities for MCP
def create_mcp_error_response(
    exception: Exception,
    tool_name: str | None = None,
    include_debug_info: bool = False,
    sanitize_sensitive: bool = True,
) -> dict[str, Any]:
    """
    Create standardized MCP error response dictionary.

    Args:
        exception: The exception to convert
        tool_name: Name of the MCP tool that failed
        include_debug_info: Whether to include debug information
        sanitize_sensitive: Whether to sanitize sensitive information

    Returns:
        MCP-compliant error response dictionary
    """
    import traceback

    response: dict[str, Any] = {
        "success": False,
        "error": {
            "type": exception.__class__.__name__,
            "message": str(exception),
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        },
    }

    # Add tool name if provided
    if tool_name:
        response["error"]["tool"] = tool_name

    # Add context if available
    if hasattr(exception, "context") and exception.context:
        context = exception.context.copy()

        # Sanitize sensitive information if requested
        if sanitize_sensitive:
            context = _sanitize_error_context(context)

        response["error"]["context"] = context

    # Add error code if available
    if hasattr(exception, "error_code"):
        response["error"]["code"] = exception.error_code

    # Add debug information if requested
    if include_debug_info:
        response["error"]["debug"] = {
            "traceback": traceback.format_exc(),
            "exception_args": list(exception.args) if exception.args else [],
        }

    # Add specific error details for known exception types
    if isinstance(exception, MCPToolError):
        response["error"]["execution_stage"] = exception.execution_stage
    elif isinstance(exception, MCPTimeoutError):
        response["error"]["timeout_seconds"] = exception.timeout_seconds
    elif isinstance(exception, FileRestrictionError):
        response["error"]["current_mode"] = exception.current_mode
        response["error"]["allowed_patterns"] = exception.allowed_patterns

    return response


def _sanitize_error_context(context: dict[str, Any]) -> dict[str, Any]:
    """Sanitize sensitive information from error context."""
    sanitized = {}
    sensitive_keys = {
        "password",
        "token",
        "key",
        "secret",
        "auth",
        "credential",
        "api_key",
        "access_token",
        "private_key",
        "session_id",
    }

    for key, value in context.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, str) and len(value) > 500:
            sanitized[key] = value[:500] + "...[TRUNCATED]"
        elif isinstance(value, (list, tuple)) and len(value) > 10:
            sanitized[key] = list(value[:10]) + ["...[TRUNCATED]"]
        elif isinstance(value, dict) and len(value) > 20:
            # Recursively sanitize nested dictionaries
            truncated_dict = dict(list(value.items())[:20])
            sanitized[key] = _sanitize_error_context(truncated_dict)
            sanitized[key]["__truncated__"] = True
        else:
            sanitized[key] = value

    return sanitized


# Async exception handling utilities for MCP tools
async def safe_execute_async(
    coro: Any,
    default_return: Any = None,
    exception_types: tuple[type[Exception], ...] = (Exception,),
    log_errors: bool = True,
    tool_name: str | None = None,
) -> Any:
    """
    Safely execute an async function with exception handling.

    Args:
        coro: Coroutine to execute
        default_return: Value to return on exception
        exception_types: Exception types to catch
        log_errors: Whether to log errors
        tool_name: Name of the tool for error context

    Returns:
        Coroutine result or default_return on exception
    """
    try:
        return await coro
    except exception_types as e:
        if log_errors:
            from .utils import log_error

            error_context = {"tool_name": tool_name} if tool_name else {}
            log_error(f"Async execution failed: {e}", extra=error_context)

        return default_return


def mcp_exception_handler(
    tool_name: str,
    include_debug: bool = False,
    sanitize_sensitive: bool = True,
) -> Any:
    """
    Decorator for MCP tool exception handling.

    Args:
        tool_name: Name of the MCP tool
        include_debug: Whether to include debug information
        sanitize_sensitive: Whether to sanitize sensitive information
    """

    def decorator(func: Any) -> Any:
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                from .utils import log_error

                # Log the error with tool context
                log_error(
                    f"MCP tool '{tool_name}' failed: {e}",
                    extra={"tool_name": tool_name, "exception_type": type(e).__name__},
                )

                # Return standardized error response
                return create_mcp_error_response(
                    e,
                    tool_name=tool_name,
                    include_debug_info=include_debug,
                    sanitize_sensitive=sanitize_sensitive,
                )

        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                from .utils import log_error

                # Log the error with tool context
                log_error(
                    f"MCP tool '{tool_name}' failed: {e}",
                    extra={"tool_name": tool_name, "exception_type": type(e).__name__},
                )

                # Return standardized error response
                return create_mcp_error_response(
                    e,
                    tool_name=tool_name,
                    include_debug_info=include_debug,
                    sanitize_sensitive=sanitize_sensitive,
                )

        # Return appropriate wrapper based on function type
        if __import__("asyncio").iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
