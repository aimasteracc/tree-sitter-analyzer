#!/usr/bin/env python3
"""
Error Handler for MCP Server

This module provides comprehensive error handling and recovery
mechanisms for the MCP server operations.
"""

import asyncio
import logging
import traceback
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


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
        super().__init__(
            message,
            category=ErrorCategory.VALIDATION,
            details={
                "field": field,
                "value": str(value) if value is not None else None,
            },
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


class ErrorHandler:
    """
    Centralized error handling and recovery system

    Provides error classification, logging, recovery mechanisms,
    and error statistics for the MCP server.
    """

    def __init__(self) -> None:
        """Initialize error handler"""
        self.error_counts: dict[str, int] = {}
        self.error_history: list[dict[str, Any]] = []
        self.max_history_size = 1000
        self.recovery_strategies: dict[type[Exception], Callable] = {}

        # Register default recovery strategies
        self._register_default_strategies()

        logger.info("Error handler initialized")

    def _register_default_strategies(self) -> None:
        """Register default error recovery strategies"""

        def file_not_found_recovery(
            error: FileNotFoundError, context: dict[str, Any]
        ) -> dict[str, Any]:
            """Recovery strategy for file not found errors"""
            return {
                "error": f"File not found: {context.get('file_path', 'unknown')}",
                "suggestion": "Please check the file path and ensure the file exists",
                "recoverable": True,
            }

        def permission_error_recovery(
            error: PermissionError, context: dict[str, Any]
        ) -> dict[str, Any]:
            """Recovery strategy for permission errors"""
            return {
                "error": f"Permission denied: {context.get('file_path', 'unknown')}",
                "suggestion": "Please check file permissions or run with appropriate privileges",
                "recoverable": False,
            }

        def value_error_recovery(
            error: ValueError, context: dict[str, Any]
        ) -> dict[str, Any]:
            """Recovery strategy for value errors"""
            return {
                "error": f"Invalid value: {str(error)}",
                "suggestion": "Please check input parameters and try again",
                "recoverable": True,
            }

        self.recovery_strategies.update(
            {
                FileNotFoundError: file_not_found_recovery,
                PermissionError: permission_error_recovery,
                ValueError: value_error_recovery,
            }
        )

    def register_recovery_strategy(
        self,
        exception_type: type[Exception],
        strategy: Callable[[Exception, dict[str, Any]], dict[str, Any]],
    ) -> None:
        """
        Register a custom recovery strategy for an exception type

        Args:
            exception_type: Type of exception to handle
            strategy: Recovery function that takes (exception, context) and returns recovery info
        """
        self.recovery_strategies[exception_type] = strategy
        logger.debug(f"Registered recovery strategy for {exception_type.__name__}")

    def handle_error(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
        operation: str = "unknown",
    ) -> dict[str, Any]:
        """
        Handle an error with classification, logging, and recovery

        Args:
            error: The exception that occurred
            context: Additional context information
            operation: Name of the operation that failed

        Returns:
            Error information dictionary with recovery suggestions
        """
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
        """
        Classify a generic exception into MCP error categories

        Args:
            error: The exception to classify
            context: Error context
            operation: Operation that failed

        Returns:
            Error information dictionary
        """
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
        """
        Log error with appropriate level based on severity

        Args:
            error: The original exception
            error_info: Classified error information
            context: Error context
            operation: Operation that failed
        """
        severity = error_info.get("severity", "medium")
        message = f"Error in {operation}: {error_info['message']}"

        if severity == "critical":
            logger.critical(
                message, extra={"error_info": error_info, "context": context}
            )
        elif severity == "high":
            logger.error(message, extra={"error_info": error_info, "context": context})
        elif severity == "medium":
            logger.warning(
                message, extra={"error_info": error_info, "context": context}
            )
        else:
            logger.info(message, extra={"error_info": error_info, "context": context})

    def _update_error_stats(self, error_info: dict[str, Any]) -> None:
        """
        Update error statistics

        Args:
            error_info: Error information
        """
        error_type = error_info.get("error_type", "Unknown")
        category = error_info.get("category", "unknown")

        # Count by type
        self.error_counts[f"type:{error_type}"] = (
            self.error_counts.get(f"type:{error_type}", 0) + 1
        )

        # Count by category
        self.error_counts[f"category:{category}"] = (
            self.error_counts.get(f"category:{category}", 0) + 1
        )

        # Count by severity
        severity = error_info.get("severity", "medium")
        self.error_counts[f"severity:{severity}"] = (
            self.error_counts.get(f"severity:{severity}", 0) + 1
        )

    def _add_to_history(
        self, error_info: dict[str, Any], context: dict[str, Any], operation: str
    ) -> None:
        """
        Add error to history with size limit

        Args:
            error_info: Error information
            context: Error context
            operation: Operation that failed
        """
        history_entry = {**error_info, "context": context, "operation": operation}

        self.error_history.append(history_entry)

        # Maintain history size limit
        if len(self.error_history) > self.max_history_size:
            self.error_history = self.error_history[-self.max_history_size :]

    def _attempt_recovery(
        self, error: Exception, context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Attempt to recover from error using registered strategies

        Args:
            error: The exception to recover from
            context: Error context

        Returns:
            Recovery information or None
        """
        error_type = type(error)

        # Try exact type match first
        if error_type in self.recovery_strategies:
            try:
                result = self.recovery_strategies[error_type](error, context)
                return result if result is not None else {}
            except Exception as recovery_error:
                logger.warning(f"Recovery strategy failed: {recovery_error}")

        # Try parent class matches
        for registered_type, strategy in self.recovery_strategies.items():
            if isinstance(error, registered_type):
                try:
                    result = strategy(error, context)
                    return result if result is not None else {}
                except Exception as recovery_error:
                    logger.warning(f"Recovery strategy failed: {recovery_error}")

        return None

    def get_error_stats(self) -> dict[str, Any]:
        """
        Get error statistics

        Returns:
            Dictionary containing error statistics
        """
        total_errors = (
            sum(self.error_counts.values()) // 3
        )  # Divide by 3 because we count type, category, severity

        return {
            "total_errors": total_errors,
            "error_counts": self.error_counts.copy(),
            "recent_errors": len(
                [
                    e
                    for e in self.error_history
                    if (datetime.now() - datetime.fromisoformat(e["timestamp"])).seconds
                    < 3600
                ]
            ),
            "history_size": len(self.error_history),
        }

    def get_recent_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get recent errors from history

        Args:
            limit: Maximum number of errors to return

        Returns:
            List of recent error entries
        """
        return self.error_history[-limit:] if self.error_history else []

    def clear_history(self) -> None:
        """Clear error history and reset statistics"""
        self.error_history.clear()
        self.error_counts.clear()
        logger.info("Error history and statistics cleared")


def handle_mcp_errors(
    operation: str = "unknown",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for automatic error handling in MCP operations

    Args:
        operation: Name of the operation for logging

    Returns:
        Decorated function with error handling
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except RuntimeError as e:
                # Handle initialization errors specifically
                if "not fully initialized" in str(e):
                    logger.warning(
                        f"Request received before initialization complete: {operation}"
                    )
                    raise MCPError(
                        "Server is still initializing. Please wait a moment and try again.",
                        category=ErrorCategory.CONFIGURATION,
                        severity=ErrorSeverity.LOW,
                    ) from e
                # Handle other runtime errors normally
                error_handler = get_error_handler()
                context = {
                    "function": func.__name__,
                    "args": str(args)[:200],  # Limit length
                    "kwargs": str(kwargs)[:200],
                }
                error_info = error_handler.handle_error(e, context, operation)
                raise
            except Exception as e:
                error_handler = get_error_handler()
                context = {
                    "function": func.__name__,
                    "args": str(args)[:200],  # Limit length
                    "kwargs": str(kwargs)[:200],
                }
                error_info = error_handler.handle_error(e, context, operation)

                # Re-raise as MCPError if not already
                if not isinstance(e, MCPError):
                    raise AnalysisError(
                        f"Operation failed: {error_info['message']}",
                        operation=operation,
                        severity=ErrorSeverity(error_info["severity"]),
                    ) from e
                raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_handler = get_error_handler()
                context = {
                    "function": func.__name__,
                    "args": str(args)[:200],
                    "kwargs": str(kwargs)[:200],
                }
                error_info = error_handler.handle_error(e, context, operation)

                if not isinstance(e, MCPError):
                    raise AnalysisError(
                        f"Operation failed: {error_info['message']}",
                        operation=operation,
                        severity=ErrorSeverity(error_info["severity"]),
                    ) from e
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# Global error handler instance
_error_handler = ErrorHandler()


def get_error_handler() -> ErrorHandler:
    """
    Get the global error handler instance

    Returns:
        Global error handler
    """
    return _error_handler
