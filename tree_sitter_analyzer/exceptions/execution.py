"""Exception handling and execution helpers."""

from typing import Any

from .core import TreeSitterAnalyzerError


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

    error_context = context or {}
    if hasattr(exception, "context"):
        error_context.update(exception.context)

    log_error(f"Exception handled: {exception}", extra=error_context)

    if reraise_as and not isinstance(exception, reraise_as):
        if issubclass(reraise_as, TreeSitterAnalyzerError):
            raise reraise_as(str(exception), context=error_context)
        raise reraise_as(str(exception))

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
            from ..utils import log_error

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

    if hasattr(exception, "context"):
        response["error"]["context"] = exception.context

    if hasattr(exception, "error_code"):
        response["error"]["code"] = exception.error_code

    if include_traceback:
        response["error"]["traceback"] = traceback.format_exc()

    return response


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
                return _handle_decorated_exception(
                    e, func.__name__, default_return, reraise_as, log_errors
                )

        return wrapper

    return decorator


def _handle_decorated_exception(
    exception: Exception,
    func_name: str,
    default_return: Any,
    reraise_as: type[Exception] | None,
    log_errors: bool,
) -> Any:
    if log_errors:
        _log_decorated_exception(func_name, exception)
    if reraise_as:
        _raise_as(reraise_as, exception)
    return default_return


def _log_decorated_exception(func_name: str, exception: Exception) -> None:
    from .utils import log_error

    log_error(f"Exception in {func_name}: {exception}")


def _raise_as(reraise_as: type[Exception], exception: Exception) -> None:
    raise reraise_as(str(exception)) from exception


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
            from ..utils import log_error

            error_context = {"tool_name": tool_name} if tool_name else {}
            log_error(f"Async execution failed: {e}", extra=error_context)

        return default_return
