"""MCP error response and decorator helpers."""

from typing import Any

from ._exceptions_mcp_types import MCPTimeoutError, MCPToolError
from ._exceptions_sanitization import _sanitize_error_context
from ._exceptions_security import FileRestrictionError


def create_mcp_error_response(
    exception: Exception,
    tool_name: str | None = None,
    include_debug_info: bool = False,
    sanitize_sensitive: bool = True,
) -> dict[str, Any]:
    """Create standardized MCP error response dictionary."""
    import traceback
    from datetime import datetime, timezone

    error: dict[str, Any] = {
        "type": exception.__class__.__name__,
        "message": str(exception),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if tool_name:
        error["tool"] = tool_name

    _attach_context(error, exception, sanitize_sensitive)

    if hasattr(exception, "error_code"):
        error["code"] = exception.error_code

    if include_debug_info:
        error["debug"] = {
            "traceback": traceback.format_exc(),
            "exception_args": list(exception.args) if exception.args else [],
        }

    _attach_exception_details(error, exception)
    return {"success": False, "error": error}


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
        def _handle_error(e: Exception) -> dict[str, Any]:
            from .utils import log_error

            log_error(
                f"MCP tool '{tool_name}' failed: {e}",
                extra={"tool_name": tool_name, "exception_type": type(e).__name__},
            )
            return create_mcp_error_response(
                e,
                tool_name=tool_name,
                include_debug_info=include_debug,
                sanitize_sensitive=sanitize_sensitive,
            )

        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return _handle_error(e)

        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return _handle_error(e)

        import inspect

        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper

    return decorator


def _attach_context(
    error: dict[str, Any], exception: Exception, sanitize_sensitive: bool
) -> None:
    if not (hasattr(exception, "context") and exception.context):
        return
    ctx = exception.context.copy()
    error["context"] = _sanitize_error_context(ctx) if sanitize_sensitive else ctx


def _attach_exception_details(error: dict[str, Any], exception: Exception) -> None:
    """Attach type-specific details from known exception types to error dict."""
    if isinstance(exception, MCPToolError):
        error["execution_stage"] = exception.execution_stage
    elif isinstance(exception, MCPTimeoutError):
        error["timeout_seconds"] = exception.timeout_seconds
    elif isinstance(exception, FileRestrictionError):
        error["current_mode"] = exception.current_mode
        error["allowed_patterns"] = exception.allowed_patterns
