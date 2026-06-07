#!/usr/bin/env python3
"""
Error Handler for MCP Server

This module provides comprehensive error handling and recovery
mechanisms for the MCP server operations.
"""

import asyncio
import inspect
import logging
import traceback
from collections.abc import Callable, Iterable
from datetime import datetime
from enum import Enum
from functools import update_wrapper
from typing import Any, NoReturn

logger = logging.getLogger(__name__)


def raise_invalid_mode(
    mode: Any, valid_modes: Iterable[str], *, label: str = "mode"
) -> NoReturn:
    """Raise a ``ValueError`` that enumerates the sorted valid modes.

    Mirrors the good pattern in ``call_graph_tool``/``test_gap_tool`` so a
    bad ``mode`` argument tells the caller exactly which values are accepted.
    Callers should pass the tool's own schema ``enum`` (e.g.
    ``self.get_tool_schema()["properties"]["mode"]["enum"]``) so the valid
    set has a single source of truth rather than a second hardcoded copy.
    """
    valid = ", ".join(sorted(valid_modes))
    raise ValueError(f"Invalid {label} '{mode}'; expected one of: {valid}.")


class ErrorSeverity(Enum):
    """Error severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification"""

    FILE_ACCESS = "file_access"
    PARSING = "parsing"
    ANALYSIS = "analysis"
    NETWORK = "network"
    VALIDATION = "validation"
    RESOURCE = "resource"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class MCPError(Exception):
    """Base exception class for MCP-specific errors"""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: dict[str, Any] | None = None,
        recoverable: bool = True,
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.recoverable = recoverable
        self.timestamp = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary representation"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "details": self.details,
            "recoverable": self.recoverable,
            "timestamp": self.timestamp.isoformat(),
        }


class FileAccessError(MCPError):
    """Error related to file access operations"""

    def __init__(self, message: str, file_path: str, **kwargs: Any):
        super().__init__(
            message,
            category=ErrorCategory.FILE_ACCESS,
            details={"file_path": file_path},
            **kwargs,
        )


class ParsingError(MCPError):
    """Error related to code parsing operations"""

    def __init__(
        self,
        message: str,
        file_path: str,
        language: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(
            message,
            category=ErrorCategory.PARSING,
            details={"file_path": file_path, "language": language},
            **kwargs,
        )


class AnalysisError(MCPError):
    """Error related to code analysis operations"""

    def __init__(self, message: str, operation: str, **kwargs: Any):
        super().__init__(
            message,
            category=ErrorCategory.ANALYSIS,
            details={"operation": operation},
            **kwargs,
        )


class ValidationError(MCPError):
    """Error related to input validation"""

    def __init__(self, message: str, field: str, value: Any = None, **kwargs: Any):
        _val_str = str(value) if value is not None else None
        super().__init__(
            message,
            category=ErrorCategory.VALIDATION,
            details={"field": field, "value": _val_str},
            **kwargs,
        )


class ResourceError(MCPError):
    """Error related to resource operations"""

    def __init__(self, message: str, resource_uri: str, **kwargs: Any):
        super().__init__(
            message,
            category=ErrorCategory.RESOURCE,
            details={"resource_uri": resource_uri},
            **kwargs,
        )


# Module-level default recovery functions — lifted out of _register_default_strategies
# to avoid triple nesting (class → method → nested def).


def _recovery_file_not_found(
    error: FileNotFoundError, context: dict[str, Any]
) -> dict[str, Any]:
    """Recovery for file-not-found errors."""
    _fp = context.get("file_path", "unknown")
    return {
        "error": "File not found: " + _fp,
        "suggestion": "Please check the file path and ensure the file exists",
        "recoverable": True,
    }


def _recovery_permission(
    error: PermissionError, context: dict[str, Any]
) -> dict[str, Any]:
    """Recovery for permission errors."""
    _fp = context.get("file_path", "unknown")
    return {
        "error": "Permission denied: " + _fp,
        "suggestion": "Please check file permissions or run with appropriate privileges",
        "recoverable": False,
    }


def _recovery_value_error(error: ValueError, context: dict[str, Any]) -> dict[str, Any]:
    """Recovery for value errors."""
    return {
        "error": "Invalid value: " + str(error),
        "suggestion": "Please check input parameters and try again",
        "recoverable": True,
    }


class ErrorHandler:
    """
    Centralized error handling and recovery system

    Provides error classification, logging, recovery mechanisms,
    and error statistics for the MCP server.
    """

    def __init__(self) -> None:
        """Initialize error handler"""
        self.error_counts: dict[str, int] = {}
        self.error_history: list[Any] = []
        self.max_history_size = 1000
        self.recovery_strategies: dict[type, Any] = {}

        # Register default recovery strategies
        self._register_default_strategies()

        logger.info("Error handler initialized")

    def _register_default_strategies(self) -> None:
        """Register default error recovery strategies."""
        self.recovery_strategies.update(
            {
                FileNotFoundError: _recovery_file_not_found,
                PermissionError: _recovery_permission,
                ValueError: _recovery_value_error,
            }
        )

    def register_recovery_strategy(
        self,
        exception_type: type[Exception],
        strategy: Callable,
    ) -> None:
        """Register a custom recovery strategy for an exception type."""
        self.recovery_strategies[exception_type] = strategy
        logger.debug("Registered recovery strategy for %s", exception_type.__name__)

    def handle_error(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
        operation: str = "unknown",
    ) -> dict[str, Any]:
        """Handle an error with classification, logging, and recovery."""
        context = context or {}

        # Classify error
        if isinstance(error, MCPError):
            error_info = error.to_dict()
        else:
            error_info = self._classify_error(error, context, operation)

        # Log error
        self._log_error(error, error_info, context, operation)

        # Update statistics
        self._update_error_stats(error_info)

        # Add to history
        self._add_to_history(error_info, context, operation)

        # Attempt recovery
        recovery_info = self._attempt_recovery(error, context)
        if recovery_info:
            error_info.update(recovery_info)

        return error_info

    def _classify_error(
        self, error: Exception, context: dict[str, Any], operation: str
    ) -> dict[str, Any]:
        """Classify a generic exception into MCP error categories."""
        error_type = type(error).__name__
        message = str(error)

        # Determine category based on error type and context
        category = ErrorCategory.UNKNOWN
        severity = ErrorSeverity.MEDIUM
        recoverable = True

        if isinstance(
            error, FileNotFoundError | IsADirectoryError | NotADirectoryError
        ):
            category = ErrorCategory.FILE_ACCESS
            severity = ErrorSeverity.MEDIUM
        elif isinstance(error, PermissionError):
            category = ErrorCategory.FILE_ACCESS
            severity = ErrorSeverity.HIGH
            recoverable = False
        elif isinstance(error, ValueError | TypeError):
            category = ErrorCategory.VALIDATION
            severity = ErrorSeverity.LOW
        elif isinstance(error, OSError | IOError):
            category = ErrorCategory.FILE_ACCESS
            severity = ErrorSeverity.HIGH
        elif isinstance(error, RuntimeError | AttributeError):
            category = ErrorCategory.ANALYSIS
            severity = ErrorSeverity.MEDIUM
        elif isinstance(error, MemoryError):
            category = ErrorCategory.RESOURCE
            severity = ErrorSeverity.CRITICAL
            recoverable = False
        elif isinstance(error, asyncio.TimeoutError):
            category = ErrorCategory.NETWORK
            severity = ErrorSeverity.MEDIUM

        return {
            "error_type": error_type,
            "message": message,
            "category": category.value,
            "severity": severity.value,
            "details": context,
            "recoverable": recoverable,
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "traceback": traceback.format_exc(),
        }

    def _log_error(
        self,
        error: Exception,
        error_info: dict[str, Any],
        context: dict[str, Any],
        operation: str,
    ) -> None:
        """Log error with appropriate level based on severity."""
        severity = error_info.get("severity", "medium")
        message = "Error in " + operation + ": " + error_info["message"]
        extra_ctx = {"error_info": error_info, "context": context}
        if severity == "critical":
            logger.critical(message, extra=extra_ctx)
        elif severity == "high":
            logger.error(message, extra=extra_ctx)
        elif severity == "medium":
            logger.warning(message, extra=extra_ctx)
        else:
            logger.info(message, extra=extra_ctx)

    def _update_error_stats(self, error_info: dict[str, Any]) -> None:
        """Update error statistics."""
        error_type = error_info.get("error_type", "Unknown")
        category = error_info.get("category", "unknown")
        severity = error_info.get("severity", "medium")
        type_key = "type:" + error_type
        cat_key = "category:" + category
        sev_key = "severity:" + severity
        self.error_counts[type_key] = self.error_counts.get(type_key, 0) + 1
        self.error_counts[cat_key] = self.error_counts.get(cat_key, 0) + 1
        self.error_counts[sev_key] = self.error_counts.get(sev_key, 0) + 1

    def _add_to_history(
        self, error_info: dict[str, Any], context: dict[str, Any], operation: str
    ) -> None:
        """Add error to history with size limit."""
        history_entry = {**error_info, "context": context, "operation": operation}
        self.error_history.append(history_entry)
        if len(self.error_history) > self.max_history_size:
            _limit = self.max_history_size
            self.error_history = self.error_history[-_limit:]

    def _try_strategy(
        self,
        strategy: Callable,
        error: Exception,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Attempt one recovery strategy; return result or None on failure."""
        try:
            result = strategy(error, context)
            return result if result is not None else {}
        except Exception as recovery_error:
            logger.warning("Recovery strategy failed: %s", recovery_error)
            return None

    def _attempt_recovery(
        self, error: Exception, context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Attempt recovery using registered strategies."""
        _ts = self._try_strategy
        error_type = type(error)
        if error_type in self.recovery_strategies:
            _strat = self.recovery_strategies[error_type]
            result = _ts(_strat, error, context)
            if result is not None:
                return result
        for registered_type, strategy in self.recovery_strategies.items():
            if not isinstance(error, registered_type):
                continue
            result = _ts(strategy, error, context)
            if result is not None:
                return result
        return None

    def _count_recent_errors(self) -> int:
        """Count errors from the past hour."""
        now_ts = datetime.now()
        _ts_key = "timestamp"
        count = 0
        for e in self.error_history:
            ts = datetime.fromisoformat(e[_ts_key])
            if (now_ts - ts).seconds < 3600:
                count += 1
        return count

    def get_error_stats(self) -> dict[str, Any]:
        """Get error statistics."""
        _ec = self.error_counts
        total_errors = sum(_ec.values()) // 3
        return {
            "total_errors": total_errors,
            "error_counts": _ec.copy(),
            "recent_errors": self._count_recent_errors(),
            "history_size": len(self.error_history),
        }

    def get_recent_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent errors from history."""
        return self.error_history[-limit:] if self.error_history else []

    def clear_history(self) -> None:
        """Clear error history and reset statistics"""
        self.error_history.clear()
        self.error_counts.clear()
        logger.info("Error history and statistics cleared")


def _build_error_context(
    func: Callable[..., Any], args: tuple, kwargs: dict
) -> dict[str, Any]:
    """Build the standard error-context dict used by both wrappers."""
    return {
        "function": func.__name__,
        "args": str(args)[:200],
        "kwargs": str(kwargs)[:200],
    }


def _handle_runtime_error(
    e: RuntimeError,
    func: Callable[..., Any],
    args: tuple,
    kwargs: dict,
    operation: str,
) -> None:
    """Handle ``RuntimeError`` in async wrapper.

    Special-cases the "not fully initialized" message into a CONFIGURATION
    MCPError. All other runtime errors get logged via the registered
    handler. Always raises (caller re-raises via ``raise`` after).

    r37e4 (dogfood): lifted out of ``handle_mcp_errors`` to flatten
    nesting 6 → 3.
    """
    if "not fully initialized" in str(e):
        logger.warning("Request received before initialization complete: %s", operation)
        raise MCPError(
            "Server is still initializing. Please wait a moment and try again.",
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.LOW,
        ) from e
    error_handler = get_error_handler()
    context = _build_error_context(func, args, kwargs)
    error_handler.handle_error(e, context, operation)


def _handle_and_rethrow_as_analysis_error(
    e: Exception,
    func: Callable[..., Any],
    args: tuple,
    kwargs: dict,
    operation: str,
) -> None:
    """Log the error then wrap non-MCPError exceptions as ``AnalysisError``."""
    error_handler = get_error_handler()
    context = _build_error_context(func, args, kwargs)
    error_info = error_handler.handle_error(e, context, operation)
    if isinstance(e, MCPError):
        return
    raise AnalysisError(
        "Operation failed: " + error_info["message"],
        operation=operation,
        severity=ErrorSeverity(error_info["severity"]),
    ) from e


def _make_async_handler(func: Callable, operation: str) -> Callable:
    """Build an async error-catching wrapper around func."""

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except RuntimeError as e:
            _handle_runtime_error(e, func, args, kwargs, operation)
            raise
        except Exception as e:
            _handle_and_rethrow_as_analysis_error(e, func, args, kwargs, operation)
            raise

    return update_wrapper(wrapper, func)


def _make_sync_handler(func: Callable, operation: str) -> Callable:
    """Build a sync error-catching wrapper around func."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            _handle_and_rethrow_as_analysis_error(e, func, args, kwargs, operation)
            raise

    return update_wrapper(wrapper, func)


def handle_mcp_errors(
    operation: str = "unknown",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for automatic error handling in MCP operations."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):
            return _make_async_handler(func, operation)
        return _make_sync_handler(func, operation)

    return decorator


# Global error handler instance
_error_handler = ErrorHandler()


def get_error_handler() -> ErrorHandler:
    """Get the global error handler instance."""
    return _error_handler
