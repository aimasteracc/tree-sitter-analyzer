#!/usr/bin/env python3
"""
Utilities for Tree-sitter Analyzer

Provides logging, debugging, and common utility functions.
"""

import atexit
import logging
import sys
from functools import wraps
from typing import Any

from ._logging_helpers import (
    STREAM_EMIT_ERRORS,
    apply_test_logger_settings,
    cleanup_all_logging_handlers,
    clear_logger_handlers,
    configure_default_handlers,
    file_logging_enabled,
    resolve_configured_log_level,
    resolve_final_logger_level,
    should_skip_stream_emit,
    write_stderr_safely,
)


# Configure global logger
def setup_logger(
    name: str = "tree_sitter_analyzer", level: int | str = logging.WARNING
) -> logging.Logger:
    """Setup unified logger for the project"""
    level = resolve_configured_log_level(level)
    logger = logging.getLogger(name)

    # Clear existing handlers if this is a test logger to ensure clean state
    if name.startswith("test_"):
        clear_logger_handlers(logger)

    enable_file_log = file_logging_enabled()
    file_log_level = level  # Default to main logger level

    if not logger.handlers:  # Avoid duplicate handlers
        file_log_level = configure_default_handlers(
            logger,
            SafeStreamHandler,
            level,
            enable_file_log,
        )

    logger.setLevel(resolve_final_logger_level(level, file_log_level, enable_file_log))
    apply_test_logger_settings(logger, level)

    return logger


class SafeStreamHandler(logging.StreamHandler):
    """
    A StreamHandler that safely handles closed streams
    """

    def __init__(self, stream: Any = None) -> None:
        # Default to sys.stderr to keep stdout clean for MCP stdio
        super().__init__(stream if stream is not None else sys.stderr)

    def emit(self, record: Any) -> None:
        """
        Emit a record, safely handling closed streams and pytest capture
        """
        try:
            if should_skip_stream_emit(self.stream):
                return

            super().emit(record)
        except STREAM_EMIT_ERRORS:
            # Silently ignore I/O errors during shutdown or pytest capture
            pass  # nosec
        except Exception:
            # For any other unexpected errors, silently ignore to prevent test failures
            pass  # nosec


def setup_safe_logging_shutdown() -> None:
    """
    Setup safe logging shutdown to prevent I/O errors
    """
    # Register cleanup function
    atexit.register(cleanup_all_logging_handlers)


# Setup safe shutdown on import
setup_safe_logging_shutdown()


# Global logger instance
logger = setup_logger()


def log_info(message: str, *args: Any, **kwargs: Any) -> None:
    """Log info message"""
    try:
        logger.info(message, *args, **kwargs)
    except (ValueError, OSError) as e:
        write_stderr_safely(f"[log_info] suppressed: {e}\n")


def log_warning(message: str, *args: Any, **kwargs: Any) -> None:
    """Log warning message"""
    try:
        logger.warning(message, *args, **kwargs)
    except (ValueError, OSError) as e:
        write_stderr_safely(f"[log_warning] suppressed: {e}\n")


def log_error(message: str, *args: Any, **kwargs: Any) -> None:
    """Log error message"""
    try:
        logger.error(message, *args, **kwargs)
    except (ValueError, OSError) as e:
        write_stderr_safely(f"[log_error] suppressed: {e}\n")


def log_debug(message: str, *args: Any, **kwargs: Any) -> None:
    """Log debug message"""
    try:
        logger.debug(message, *args, **kwargs)
    except (ValueError, OSError) as e:
        write_stderr_safely(f"[log_debug] suppressed: {e}\n")


def suppress_output(func: Any) -> Any:
    """Decorator to suppress print statements in production"""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Check if we're in test/debug mode
        if getattr(sys, "_testing", False):
            return func(*args, **kwargs)

        # Redirect stdout to suppress prints
        old_stdout = sys.stdout
        try:
            sys.stdout = (
                open("/dev/null", "w") if sys.platform != "win32" else open("nul", "w")
            )
            result = func(*args, **kwargs)
        finally:
            try:
                sys.stdout.close()
            except Exception as e:
                write_stderr_safely(f"[suppress_output] stdout close suppressed: {e}\n")
            sys.stdout = old_stdout

        return result

    return wrapper


class QuietMode:
    """Context manager for quiet execution"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.old_level: int | None = None

    def __enter__(self) -> "QuietMode":
        if self.enabled:
            self.old_level = logger.level
            logger.setLevel(logging.ERROR)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.enabled and self.old_level is not None:
            logger.setLevel(self.old_level)


def safe_print(message: str | None, level: str = "info", quiet: bool = False) -> None:
    """Safe print function that can be controlled"""
    if quiet:
        return

    # Handle None message by converting to string - always call log function even for None
    msg = str(message) if message is not None else "None"

    # Use dynamic lookup to support mocking
    level_lower = level.lower()
    if level_lower == "info":
        log_info(msg)
    elif level_lower == "warning":
        log_warning(msg)
    elif level_lower == "error":
        log_error(msg)
    elif level_lower == "debug":
        log_debug(msg)
    else:
        log_info(msg)  # Default to info


def create_performance_logger(name: str) -> logging.Logger:
    """Create performance-focused logger.

    Two important invariants — observed as duplicate stderr noise in
    real VS Code MCP client logs (every tool call produced two lines:
    one ``PERF -`` line from this logger's handler, plus one
    ``tree_sitter_analyzer.performance - DEBUG -`` line because the
    record propagated up to the root logger):

    1. **No hard-coded level.** We let the logger inherit the
       configured level from the root logger (default ``WARNING`` via
       :func:`resolve_configured_log_level`). Operators who want
       per-call timings opt in via ``LOG_LEVEL=DEBUG``. Hard-coding
       ``DEBUG`` here ignored that knob and emitted timings to every
       MCP client log regardless of configuration.

    2. **Propagation off.** Even when the operator does set
       ``LOG_LEVEL=DEBUG``, the same event must not be logged twice
       — once formatted as ``PERF -`` here, once again upstream by
       the root logger's standard formatter. Setting
       ``propagate = False`` prevents the double-log without
       suppressing anything when the level is actually enabled.
    """
    perf_logger = logging.getLogger(f"{name}.performance")

    if not perf_logger.handlers:
        handler = SafeStreamHandler()
        formatter = logging.Formatter("%(asctime)s - PERF - %(message)s")
        handler.setFormatter(formatter)
        perf_logger.addHandler(handler)
        # Inherit level from root logger; stop propagation to root so
        # we don't get a second formatted copy of every PERF record.
        perf_logger.propagate = False

    return perf_logger


# Performance logger instance
perf_logger = create_performance_logger("tree_sitter_analyzer")


def log_performance(
    operation: str,
    execution_time: float | None = None,
    details: dict[Any, Any] | str | None = None,
) -> None:
    """Log performance metrics"""
    try:
        message = f"{operation}"
        if execution_time is not None:
            message += f": {execution_time:.4f}s"
        if details:
            if isinstance(details, dict):
                detail_str = ", ".join([f"{k}: {v}" for k, v in details.items()])
            else:
                detail_str = str(details)
            message += f" - {detail_str}"
        perf_logger.debug(message)  # Change to DEBUG level
    except (ValueError, OSError) as e:
        write_stderr_safely(f"[log_performance] suppressed: {e}\n")


def setup_performance_logger() -> logging.Logger:
    """Set up performance logging"""
    perf_logger = logging.getLogger("performance")

    # Add handler if not already configured
    if not perf_logger.handlers:
        handler = SafeStreamHandler()
        formatter = logging.Formatter("%(asctime)s - Performance - %(message)s")
        handler.setFormatter(formatter)
        perf_logger.addHandler(handler)
        perf_logger.setLevel(logging.INFO)

    return perf_logger


class LoggingContext:
    """Context manager for controlling logging behavior"""

    def __init__(self, enabled: bool = True, level: int | None = None):
        self.enabled = enabled
        self.level = level
        self.old_level: int | None = None
        # Use a specific logger name for testing to avoid interference
        self.target_logger = logging.getLogger("tree_sitter_analyzer")

    def __enter__(self) -> "LoggingContext":
        if self.enabled and self.level is not None:
            # Always save the current level before changing
            self.old_level = self.target_logger.level
            # Ensure we have a valid level to restore to (not NOTSET)
            if self.old_level == logging.NOTSET:
                self.old_level = logging.INFO  # Default fallback
            self.target_logger.setLevel(self.level)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.enabled and self.old_level is not None:
            # Always restore the saved level
            self.target_logger.setLevel(self.old_level)
