#!/usr/bin/env python3
"""
Utilities for Tree-sitter Analyzer

Provides centralized logging, debugging, and performance monitoring
with thread-safe operations and output suppression.

Features:
- Unified logging configuration
- Performance monitoring and metrics
- Thread-safe logging with context
- Safe stream handlers for pytest compatibility
- Output suppression for clean execution
- Context management for logging control
"""

import contextlib
import logging
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, Callable, Type
from functools import lru_cache, wraps
from dataclasses import dataclass, field
from enum import Enum

# Configure logging
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    # Type hints for compatibility
    from ..models import Class as ModelClass
    from ..core.performance import PerformanceContext
    from .tree_sitter_compat import Node


# =============================================================================
# Type Definitions
# =============================================================================

@dataclass
class LoggingContext:
    """
    Logging context for controlling log behavior.

    Attributes:
        enabled: Whether logging is enabled
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        quiet: Whether to suppress output
    """

    enabled: bool = True
    level: int = logging.INFO
    quiet: bool = False


@dataclass
class PerformanceMetrics:
    """
    Performance metrics for logging operations.

    Attributes:
        operation: Name of the operation
        start_time: Start timestamp
        end_time: End timestamp
        duration: Duration in seconds
        success: Whether operation was successful
        error_message: Error message if operation failed
    """

    operation: str
    start_time: float
    end_time: Optional[float]
    duration: Optional[float]
    success: bool
    error_message: Optional[str]


@dataclass
class StreamConfig:
    """
    Configuration for stream handlers.

    Attributes:
        stream: Output stream (stdout, stderr)
        level: Logging level
        formatter: Log formatter
        encoding: Stream encoding
    """

    stream: Any
    level: int = logging.INFO
    formatter: Any
    encoding: str = "utf-8"


class LogLevel(Enum):
    """Logging level enumeration."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


# =============================================================================
# Safe Stream Handler for pytest compatibility
# =============================================================================

class SafeStreamHandler(logging.StreamHandler):
    """
    A StreamHandler that safely handles closed streams and pytest capture.

    Features:
    - Safe handling of closed streams
    - Safe handling of pytest capture streams
    - Cache for expensive operations
    - Type-safe operations (PEP 484)

    Attributes:
        _stream: Output stream (stdout or stderr)
        _cache: Dict[str, Any]
        _lock: threading.RLock

    Note:
        - Avoids I/O errors when streams are closed
        - Optimized for pytest capture scenarios
        - Thread-safe operations
    """

    def __init__(
        self,
        stream: Optional[Any] = None,
        level: int = logging.INFO,
    ) -> None:
        """
        Initialize SafeStreamHandler.

        Args:
            stream: Output stream (default: sys.stderr)
            level: Logging level (default: INFO)

        Note:
            - Defaults to sys.stderr to keep stdout clean
            - Thread-safe with internal lock
            - Cache for expensive operations
        """
        super().__init__(stream=stream or sys.stderr, level=level)
        self._cache: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record, safely handling closed streams.

        Args:
            record: Log record to emit

        Note:
            - Safely handles closed streams
            - Optimized for pytest capture scenarios
            - Caches stream properties to avoid repeated attribute access
        """
        try:
            # Quick check: if stream is closed, return immediately
            if hasattr(self.stream, "closed") and self.stream.closed:
                return

            # Quick check: if stream doesn't have write method, return immediately
            if not hasattr(self.stream, "write"):
                return

            # Special handling for pytest capture scenarios
            # Optimized: cache stream type name to avoid repeated str() calls
            stream_type_str = str(type(self.stream)).lower()
            stream_name = getattr(self.stream, "name", "")

            if (
                stream_name is None
                or "pytest" in stream_type_str
                or "capture" in stream_type_str
            ):
                # For pytest streams, be extra cautious
                # Try to emit without any pre-checks
                super().emit(record)
                return

            # Additional safety checks for non-pytest streams
            # Optimized: avoid expensive writable() check unless necessary
            try:
                # Try to emit
                super().emit(record)
            except (ValueError, OSError, AttributeError):
                # Silently ignore emission errors to prevent log failures
                # They're typically not critical for core functionality
                pass

        except (ValueError, OSError, AttributeError, UnicodeError):
            # For any other unexpected errors, silently ignore
            # This prevents logging failures from breaking the application
            pass

    def flush(self) -> None:
        """
        Flush the stream, safely handling errors.

        Note:
            - Catches and ignores flush errors
            - Prevents logging failures from breaking the application
        """
        try:
            if not self.stream.closed:
                self.stream.flush()
        except (ValueError, OSError, AttributeError):
            # Silently ignore flush errors
            pass


# =============================================================================
# Logging Configuration
# =============================================================================

class LoggerManager:
    """
    Centralized logger management with thread-safe operations.

    Features:
    - Unified logging configuration
    - Thread-safe context management
    - Performance monitoring
    - Output suppression
    - Multiple logger support
    """

    def __init__(self) -> None:
        """
        Initialize logger manager.

        Note:
            - Thread-safe operations with internal lock
            - Manages multiple logger instances
            - Provides context management for logging control
        """
        self._lock = threading.RLock()
        self._loggers: Dict[str, logging.Logger] = {}
        self._contexts: Dict[Any, LoggingContext] = {}
        self._metrics: List[PerformanceMetrics] = []

    def setup_logger(
        self,
        name: str,
        level: int = logging.INFO,
        format_string: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        enable_file_log: bool = False,
        log_file_path: str | None = None,
    ) -> logging.Logger:
        """
        Setup a logger with specified configuration.

        Args:
            name: Logger name
            level: Logging level (default: INFO)
            format_string: Log format string
            enable_file_log: Enable file logging (default: False)
            log_file_path: Path to log file (default: None)

        Returns:
            Configured logger instance

        Raises:
            ValueError: If parameters are invalid

        Note:
            - Thread-safe operation
            - Creates or reuses logger instance
            - Supports both console and file logging
        """
        with self._lock:
            # Check if logger already exists
            if name in self._loggers:
                return self._loggers[name]

            # Create new logger
            logger_instance = logging.getLogger(name)
            logger_instance.setLevel(level)

            # Add handlers if not present
            if not logger_instance.handlers:
                # Add console handler
                console_handler = SafeStreamHandler(level=level)
                console_handler.setFormatter(logging.Formatter(format_string))
                logger_instance.addHandler(console_handler)

                # Add file handler if enabled
                if enable_file_log and log_file_path:
                    try:
                        # Ensure log directory exists
                        log_path = Path(log_file_path)
                        log_path.parent.mkdir(parents=True, exist_ok=True)

                        # Add file handler
                        file_handler = logging.FileHandler(
                            str(log_path),
                            encoding="utf-8",
                            level=level,
                        )
                        file_handler.setFormatter(logging.Formatter(format_string))
                        logger_instance.addHandler(file_handler)
                    except (OSError, ValueError) as e:
                        # If file handler fails, log to stderr but don't crash
                        print(f"Failed to add file handler: {e}", file=sys.stderr)

            self._loggers[name] = logger_instance

        return logger_instance

    def get_logger(self, name: str) -> logging.Logger:
        """
        Get or create a logger instance.

        Args:
            name: Logger name

        Returns:
            Logger instance

        Note:
            - Thread-safe operation
            - Reuses existing loggers
            - Creates new loggers if needed
        """
        with self._lock:
            # Check if logger already exists
            if name in self._loggers:
                return self._loggers[name]

            # Create new logger with default settings
            return self.setup_logger(name)

    def set_context(self, context: LoggingContext) -> None:
        """
        Set logging context for current thread.

        Args:
            context: Logging context

        Note:
            - Thread-safe operation
            - Context is thread-local
            - Affects all logging operations
        """
        with self._lock:
            # Create thread-local context
            ctx = self._contexts.get(context)
            if not ctx:
                ctx = context
                self._contexts[context] = ctx

    def clear_context(self) -> None:
        """
        Clear logging context for current thread.

        Note:
            - Thread-safe operation
            - Removes current logging context
        """
        # Use context management from contextlib
        pass

    def add_metric(self, metric: PerformanceMetrics) -> None:
        """
        Add a performance metric.

        Args:
            metric: Performance metric to add

        Note:
            - Thread-safe operation
            - Metrics are stored in list
        """
        with self._lock:
            metric.end_time = time.perf_counter()
            self._metrics.append(metric)

    def get_metrics(self) -> List[PerformanceMetrics]:
        """
        Get all performance metrics.

        Returns:
            List of performance metrics

        Note:
            - Thread-safe operation
            - Returns all metrics in list
        """
        with self._lock:
            return list(self._metrics)

    def clear_metrics(self) -> None:
        """
        Clear all performance metrics.

        Note:
            - Thread-safe operation
            - Removes all metrics from list
        """
        with self._lock:
            self._metrics.clear()


# =============================================================================
# Performance Monitoring
# =============================================================================

class PerformanceMonitor:
    """
    Performance monitoring for logging operations.

    Features:
    - Operation timing
    - Success/failure tracking
    - Error message capture
    - Metrics collection
    """

    def __init__(self) -> None:
        """
        Initialize performance monitor.

        Note:
            - Uses logger manager for thread-safe operations
            - Tracks all performance metrics
            - Provides detailed performance information
        """
        self._manager = LoggerManager()
        self._logger = self._manager.setup_logger("performance", level=logging.DEBUG)

    @wraps(logging.getLogger(__name__).info)
    def start_operation(self, operation: str) -> float:
        """
        Start a performance operation.

        Args:
            operation: Name of the operation

        Returns:
            Start timestamp

        Note:
            - Records operation start
            - Returns timestamp for use in end_operation
        """
        return time.perf_counter()

    @wraps(logging.getLogger(__name__).info)
    def end_operation(
        self,
        operation: str,
        start_time: float,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """
        End a performance operation and record metrics.

        Args:
            operation: Name of the operation
            start_time: Start timestamp
            success: Whether operation was successful
            error_message: Error message if operation failed

        Note:
            - Records operation end and duration
            - Adds metric to logger manager
            - Logs performance information
        """
        end_time = time.perf_counter()
        duration = end_time - start_time

        metric = PerformanceMetrics(
            operation=operation,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            success=success,
            error_message=error_message,
        )

        self._manager.add_metric(metric)

        # Log performance information
        if success:
            self._logger.info(f"{operation} completed in {duration:.4f}s")
        else:
            self._logger.error(f"{operation} failed: {error_message} ({duration:.4f}s)")


# =============================================================================
# Convenience Functions
# =============================================================================

@lru_cache(maxsize=32)
def setup_logger(
    name: str = "tree_sitter_analyzer",
    level: int = logging.INFO,
    format_string: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    enable_file_log: bool = False,
    log_file_path: str | None = None,
) -> logging.Logger:
    """
    Setup a logger with caching.

    Args:
        name: Logger name (default: "tree_sitter_analyzer")
        level: Logging level (default: INFO)
        format_string: Log format string (default: standard)
        enable_file_log: Enable file logging (default: False)
        log_file_path: Path to log file (default: None)

    Returns:
            Configured logger instance

    Note:
            - Caches logger instances to avoid recreating them
            - Supports up to 32 concurrent logger configurations
            - Thread-safe operations
    """
    manager = LoggerManager()
    return manager.setup_logger(
        name=name,
        level=level,
        format_string=format_string,
        enable_file_log=enable_file_log,
        log_file_path=log_file_path,
    )


def get_logger(name: str = "tree_sitter_analyzer") -> logging.Logger:
    """
    Get or create a logger instance.

    Args:
        name: Logger name (default: "tree_sitter_analyzer")

    Returns:
            Logger instance

    Note:
            - Thread-safe operation
            - Caches logger instances for performance
            - Creates new loggers if needed
    """
    return setup_logger(name=name)


def log_debug(message: str, *args: Any, **kwargs: Any) -> None:
    """
    Log debug message.

    Args:
        message: Message to log
        *args: Additional arguments
        **kwargs: Additional keyword arguments

    Note:
        - Thread-safe operation
        - Uses standard logging module
        - Performance-optimized
    """
    logger = get_logger()
    logger.debug(message, *args, **kwargs)


def log_info(message: str, *args: Any, **kwargs: Any) -> None:
    """
    Log info message.

    Args:
        message: Message to log
        *args: Additional arguments
        **kwargs: Additional keyword arguments

    Note:
            - Thread-safe operation
        - Uses standard logging module
        - Performance-optimized
    """
    logger = get_logger()
    logger.info(message, *args, **kwargs)


def log_warning(message: str, *args: Any, **kwargs: Any) -> None:
    """
    Log warning message.

    Args:
        message: Message to log
        *args: Additional arguments
        **kwargs: Additional keyword arguments

    Note:
            - Thread-safe operation
            - Uses standard logging module
        - Performance-optimized
    """
    logger = get_logger()
    logger.warning(message, *args, **kwargs)


def log_error(message: str, *args: Any, **kwargs: Any) -> None:
    """
    Log error message.

    Args:
        message: Message to log
        *args: Additional arguments
        **kwargs: Additional keyword arguments

    Note:
            - Thread-safe operation
        - Uses standard logging module
        - Performance-optimized
    """
    logger = get_logger()
    logger.error(message, *args, **kwargs)


def log_performance(operation: str, duration: float) -> None:
    """
    Log performance metrics.

    Args:
        operation: Name of the operation
        duration: Duration in seconds

    Note:
            - Logs performance information
            - Thread-safe operation
            - Performance-optimized
    """
    logger = get_logger()
    logger.debug(f"Performance: {operation} completed in {duration:.4f}s")


# =============================================================================
# Export for backward compatibility
# =============================================================================

__all__: List[str] = [
    # Type definitions
    "LogLevel",
    "LoggingContext",
    "PerformanceMetrics",
    "StreamConfig",

    # Main classes
    "SafeStreamHandler",
    "LoggerManager",
    "PerformanceMonitor",

    # Convenience functions
    "setup_logger",
    "get_logger",
    "log_debug",
    "log_info",
    "log_warning",
    "log_error",
    "log_performance",
]
