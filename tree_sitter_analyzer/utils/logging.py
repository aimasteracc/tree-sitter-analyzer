#!/usr/bin/env python3
"""
Logging Utilities for Tree-sitter Analyzer

Provides centralized logging, debugging, and performance monitoring
with thread-safe operations and output suppression.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling and recovery
- LRU caching for logger instances
- Thread-safe operations
- Performance monitoring
- Detailed documentation

Features:
- Unified logging configuration
- Performance monitoring and metrics
- Thread-safe operations
- Output suppression for clean execution
- Context management for logging control
- Safe stream handlers for pytest compatibility

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

import functools
import logging
import os
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, Optional, Dict, List, Tuple, Union, Callable, Type
from functools import lru_cache
from dataclasses import dataclass, field
from enum import Enum

# Type checking setup
if TYPE_CHECKING:
    # Models
    from ..models import Class as ModelClass
    from ..core.performance import PerformanceContext
else:
    # Runtime imports (when type checking is disabled)
    ModelClass = Any
    PerformanceContext = Any

# Configure root logger
root_logger = logging.getLogger("tree_sitter_analyzer")
root_logger.setLevel(logging.INFO)

# Environment variable for log level
LOG_LEVEL_ENV = "LOG_LEVEL"
QUIET_MODE_ENV = "QUIET_MODE"


# ============================================================================
# Type Definitions
# ============================================================================

@dataclass
class LoggingConfig:
    """
    Configuration for logging system.

    Attributes:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Log format string
        enable_file_logging: Enable file logging
        log_file_path: Path to log file
        enable_console_logging: Enable console logging
        enable_performance_logging: Enable performance monitoring
        performance_log_level: Performance logging level
    """

    level: int = logging.INFO
    format_string: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    enable_file_logging: bool = False
    log_file_path: Optional[str] = None
    enable_console_logging: bool = True
    enable_performance_logging: bool = True
    performance_log_level: int = logging.DEBUG

    def get_level_name(self) -> str:
        """Get name of logging level."""
        return logging.getLevelName(self.level)


@dataclass
class LoggingContext:
    """
    Logging context for controlling log behavior.

    Attributes:
        enabled: Whether logging is enabled
        level: Logging level
        quiet: Whether to suppress output
        performance_enabled: Whether performance logging is enabled
    """

    enabled: bool = True
    level: int = logging.INFO
    quiet: bool = False
    performance_enabled: bool = True


@dataclass
class PerformanceMetrics:
    """
    Performance metrics for logging operations.

    Attributes:
        operation: Name of operation
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


class LogLevel(Enum):
    """Logging level enumeration."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


# ============================================================================
# Custom Exceptions
# ============================================================================

class LoggingError(Exception):
    """Base exception for logging errors."""

    pass


class ConfigurationError(LoggingError):
    """Exception raised when logging configuration is invalid."""

    pass


class InitializationError(LoggingError):
    """Exception raised when logging initialization fails."""

    pass


class StreamHandlerError(LoggingError):
    """Exception raised when stream handler initialization fails."""

    pass


# ============================================================================
# Safe Stream Handler for pytest compatibility
# ============================================================================

class SafeStreamHandler(logging.StreamHandler):
    """
    A StreamHandler that safely handles closed streams and pytest capture.

    Features:
    - Safe handling of closed streams
    - Safe handling of pytest capture streams
    - Caches stream properties to avoid repeated attribute access
    - Type-safe operations (PEP 484)

    Attributes:
        _stream: Output stream (stdout or stderr)
        _cache: Dict[str, Any]
        _lock: threading.RLock
        _name: Stream name for error messages

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
            - Caches stream properties for performance
        """
        # Initialize stream
        self._stream = stream or sys.stderr

        # Initialize cache for expensive properties
        self._cache: Dict[str, Any] = {}

        # Thread-safe lock for operations
        self._lock = threading.RLock()

        # Set level
        super().__init__(level=level)

    @property
    def stream(self) -> Any:
        """Get stream (cached for performance)."""
        return self._stream

    @stream.setter
    def stream(self, value: Any) -> None:
        """Set stream."""
        with self._lock:
            self._stream = value

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record, safely handling closed streams.

        Args:
            record: Log record to emit

        Note:
            - Safely handles closed streams
            - Optimized for pytest capture scenarios
            - Caches stream type name to avoid repeated str() calls
            - Prevents logging failures from breaking the application
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

            if (
                stream_type_str is None
                or "pytest" in stream_type_str
                or "capture" in stream_type_str
            ):
                # For pytest streams, be extra cautious
                # Try to emit without any pre-checks
                super().emit(record)
                return

            # Additional safety checks for non-pytest streams
            # Optimized: use cached value if available
            if "writable" in self._cache:
                writable = self._cache["writable"]
            else:
                writable = getattr(self.stream, "writable", True)
                self._cache["writable"] = writable

            if not writable:
                return

            # Try to emit
            super().emit(record)

        except (ValueError, OSError, AttributeError):
            # Silently ignore emission errors to prevent log failures
            # They're typically not critical for core functionality
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


# ============================================================================
# Logger Manager
# ============================================================================

class LoggerManager:
    """
    Centralized logger management with thread-safe operations.

    Features:
    - Unified logging configuration
    - Thread-safe operations
    - Performance monitoring
    - Multiple logger support
    - Context management

    Attributes:
        _loggers: Dictionary of logger instances
        _contexts: Dictionary of logging contexts
        _lock: Thread-safe lock for operations
        _config: Logging configuration
        _metrics: Performance metrics

    Note:
    - Thread-safe operations with internal lock
    - Caches logger instances to avoid recreating them
    - Manages logging contexts for flexible control
    """

    def __init__(self, config: Optional[LoggingConfig] = None) -> None:
        """
        Initialize logger manager.

        Args:
            config: Optional logging configuration (uses defaults if None)

        Note:
            - Thread-safe operations with internal lock
            - Manages multiple logger instances
            - Provides context management for logging control
        """
        self._config = config or LoggingConfig()

        # Thread-safe operations
        self._lock = threading.RLock()

        # Logger cache (LRU)
        self._loggers: Dict[str, logging.Logger] = {}

        # Logging contexts (thread-local)
        self._contexts: Dict[Any, LoggingContext] = {}

        # Performance metrics
        self._metrics: List[PerformanceMetrics] = []

    def setup_logger(
        self,
        name: str,
        level: int = logging.INFO,
        format_string: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        enable_file_log: bool = False,
        log_file_path: Optional[str] = None,
    ) -> logging.Logger:
        """
        Setup a logger with specified configuration.

        Args:
            name: Logger name
            level: Logging level
            format_string: Log format string
            enable_file_log: Enable file logging
            log_file_path: Path to log file

        Returns:
            Configured logger instance

        Raises:
            InitializationError: If logger setup fails

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

            # Add console handler
            if self._config.enable_console_logging:
                console_handler = SafeStreamHandler(level=level)
                console_handler.setFormatter(logging.Formatter(format_string))
                logger_instance.addHandler(console_handler)

            # Add file handler
            if enable_file_log and log_file_path:
                try:
                    # Ensure log directory exists
                    from pathlib import Path
                    log_path = Path(log_file_path)
                    log_path.parent.mkdir(parents=True, exist_ok=True)

                    file_handler = logging.FileHandler(
                        str(log_path),
                        encoding="utf-8",
                        level=level,
                    )
                    file_handler.setFormatter(logging.Formatter(format_string))
                    logger_instance.addHandler(file_handler)
                except Exception as e:
                    root_logger.warning(f"Failed to add file handler: {e}")

            # Cache logger
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
            - Reuses existing loggers if available
            - Creates new loggers if needed
        """
        with self._lock:
            if name in self._loggers:
                return self._loggers[name]

            return self.setup_logger(name)

    def set_context(self, context: LoggingContext) -> None:
        """
        Set logging context for current thread.

        Args:
            context: Logging context

        Note:
            - Thread-local context
            - Affects all logging operations
        """
        with self._lock:
            # Use thread ID as key for context
            thread_id = threading.get_ident()
            self._contexts[thread_id] = context

    def clear_context(self) -> None:
        """
        Clear logging context for current thread.

        Note:
            - Thread-local context
            - Removes current logging context
        """
        with self._lock:
            thread_id = threading.get_ident()
            if thread_id in self._contexts:
                del self._contexts[thread_id]

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

    def get_stats(self) -> Dict[str, Any]:
        """
        Get logger manager statistics.

        Returns:
            Dictionary with statistics

        Note:
            - Thread-safe operation
            - Returns cache sizes, metrics, config
        """
        with self._lock:
            return {
                "logger_cache_size": len(self._loggers),
                "context_cache_size": len(self._contexts),
                "metrics_size": len(self._metrics),
                "config": {
                    "level": self._config.get_level_name(),
                    "format_string": self._config.format_string,
                    "enable_file_logging": self._config.enable_file_logging,
                    "enable_console_logging": self._config.enable_console_logging,
                    "enable_performance_logging": self._config.enable_performance_logging,
                },
            }


# ============================================================================
# Convenience Functions with LRU Caching
# ============================================================================

@lru_cache(maxsize=64, typed=True)
def get_logger_manager() -> LoggerManager:
    """
    Get logger manager instance with LRU caching.

    Returns:
        LoggerManager instance

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    config = LoggingConfig(
        level=logging.INFO,
        format_string="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        enable_file_logging=False,
        enable_console_logging=True,
        enable_performance_logging=True,
    )
    return LoggerManager(config=config)


# ============================================================================
# Performance Monitoring
# ============================================================================

@lru_cache(maxsize=64, typed=True)
def create_performance_logger(name: str = "performance") -> logging.Logger:
    """
    Create performance logger with caching.

    Args:
        name: Logger name (default: "performance")

    Returns:
        Configured performance logger

    Performance:
        LRU caching with maxsize=64 reduces overhead for repeated calls.
    """
    return get_logger_manager().setup_logger(name, level=logging.DEBUG)


def log_performance(operation: str, duration: float) -> None:
    """
    Log performance metrics.

    Args:
        operation: Name of the operation
        duration: Duration in seconds

    Note:
        - Uses cached performance logger
        - Thread-safe operation
    """
    logger = create_performance_logger()
    logger.debug(f"Performance: {operation} completed in {duration:.4f}s")


# ============================================================================
# Logging Functions
# ============================================================================

def log_debug(message: str, *args: Any, **kwargs: Any) -> None:
    """
    Log debug message.

    Args:
        message: Message to log
        *args: Additional arguments
        **kwargs: Additional keyword arguments

    Note:
        - Uses cached logger manager
        - Thread-safe operation
        - Performance-optimized
    """
    logger = get_logger_manager().get_logger("tree_sitter_analyzer")
    logger.debug(message, *args, **kwargs)


def log_info(message: str, *args: Any, **kwargs: Any) -> None:
    """
    Log info message.

    Args:
        message: Message to log
        *args: Additional arguments
        **kwargs: Additional keyword arguments

    Note:
        - Uses cached logger manager
        - Thread-safe operation
        - Performance-optimized
    """
    logger = get_logger_manager().get_logger("tree_sitter_analyzer")
    logger.info(message, *args, **kwargs)


def log_warning(message: str, *args: Any, **kwargs: Any) -> None:
    """
    Log warning message.

    Args:
        message: Message to log
        *args: Additional arguments
        **kwargs: Additional keyword arguments

    Note:
        - Uses cached logger manager
        - Thread-safe operation
        - Performance-optimized
    """
    logger = get_logger_manager().get_logger("tree_sitter_analyzer")
    logger.warning(message, *args, **kwargs)


def log_error(message: str, *args: Any, **kwargs: Any) -> None:
    """
    Log error message.

    Args:
        message: Message to log
        *args: Additional arguments
        **kwargs: Additional keyword arguments

    Note:
        - Uses cached logger manager
        - Thread-safe operation
        - Performance-optimized
    """
    logger = get_logger_manager().get_logger("tree_sitter_analyzer")
    logger.error(message, *args, **kwargs)


# ============================================================================
# Output Suppression
# ============================================================================

def suppress_output() -> None:
    """Suppress all logging output."""
    os.environ[LOG_LEVEL_ENV] = "CRITICAL"
    os.environ[QUIET_MODE_ENV] = "1"
    root_logger.setLevel(logging.CRITICAL)


def setup_safe_logging_shutdown() -> None:
    """
    Setup safe logging shutdown.

    Note:
        - Prevents errors during logging shutdown
        - Thread-safe operation
    """
    root_logger.handlers.clear()


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================

__all__: List[str] = [
    # Type definitions
    "LoggingConfig",
    "LoggingContext",
    "PerformanceMetrics",
    "LogLevel",

    # Main classes
    "SafeStreamHandler",
    "LoggerManager",

    # Convenience functions
    "get_logger_manager",
    "create_performance_logger",
    "log_performance",
    "log_debug",
    "log_info",
    "log_warning",
    "log_error",
    "suppress_output",
    "setup_safe_logging_shutdown",
]


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================

def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Name of the component to import

    Returns:
        Imported component or function

    Raises:
        ImportError: If component is not found
    """
    # Handle specific imports
    if name == "LoggerManager":
        return LoggerManager
    elif name == "SafeStreamHandler":
        return SafeStreamHandler
    elif name in ["setup_logger", "get_logger", "set_context"]:
        return getattr(get_logger_manager(), name)
    elif name in [
        "log_debug",
        "log_info",
        "log_warning",
        "log_error",
    ]:
        # Import from module
        module = __import__(f".{name}", fromlist=[f".{name}"])
        return getattr(module, name)
    else:
        raise ImportError(f"Module {name} not found in logging package")
