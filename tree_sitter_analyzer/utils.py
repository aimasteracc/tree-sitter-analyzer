#!/usr/bin/env python3
"""
Utilities for Tree-sitter Analyzer

Provides logging, debugging, and common utility functions.
"""

import atexit
import contextlib
import logging
import sys
from functools import wraps
from typing import Any

# Import the new unified logging manager
from .logging_manager import get_logger_manager


def setup_logger(
    name: str = "tree_sitter_analyzer", level: int | str = logging.WARNING
) -> logging.Logger:
    """
    Setup unified logger for the project using LoggerManager

    This function now delegates to the LoggerManager for unified logging
    while maintaining backward compatibility with the existing API.

    Args:
        name: Logger name
        level: Log level (string or int)

    Returns:
        Configured logger instance
    """
    # Use the unified logger manager
    logger_manager = get_logger_manager()
    return logger_manager.get_logger(name, level)


def setup_safe_logging_shutdown() -> None:
    """
    Setup safe logging shutdown to prevent I/O errors
    """

    def cleanup_logging() -> None:
        """Clean up logging handlers safely"""
        try:
            # Get all loggers
            loggers = [logging.getLogger()] + [
                logging.getLogger(name) for name in logging.Logger.manager.loggerDict
            ]

            for logger in loggers:
                for handler in logger.handlers[:]:
                    try:
                        handler.close()
                        logger.removeHandler(handler)
                    except Exception as e:
                        if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
                            with contextlib.suppress(Exception):
                                sys.stderr.write(
                                    f"[logging_cleanup] handler close/remove skipped: {e}\n"
                                )
        except Exception as e:
            if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
                with contextlib.suppress(Exception):
                    sys.stderr.write(f"[logging_cleanup] cleanup skipped: {e}\n")

    # Register cleanup function
    atexit.register(cleanup_logging)


# Setup safe shutdown on import
setup_safe_logging_shutdown()


# Global logger instance
logger = setup_logger()


def log_info(message: str, *args: Any, **kwargs: Any) -> None:
    """Log info message"""
    try:
        logger.info(message, *args, **kwargs)
    except (ValueError, OSError) as e:
        if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
            with contextlib.suppress(Exception):
                sys.stderr.write(f"[log_info] suppressed: {e}\n")


def log_warning(message: str, *args: Any, **kwargs: Any) -> None:
    """Log warning message"""
    try:
        logger.warning(message, *args, **kwargs)
    except (ValueError, OSError) as e:
        if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
            with contextlib.suppress(Exception):
                sys.stderr.write(f"[log_warning] suppressed: {e}\n")


def log_error(message: str, *args: Any, **kwargs: Any) -> None:
    """Log error message"""
    try:
        logger.error(message, *args, **kwargs)
    except (ValueError, OSError) as e:
        if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
            with contextlib.suppress(Exception):
                sys.stderr.write(f"[log_error] suppressed: {e}\n")


def log_debug(message: str, *args: Any, **kwargs: Any) -> None:
    """Log debug message"""
    try:
        logger.debug(message, *args, **kwargs)
    except (ValueError, OSError) as e:
        if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
            with contextlib.suppress(Exception):
                sys.stderr.write(f"[log_debug] suppressed: {e}\n")


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
                if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
                    with contextlib.suppress(Exception):
                        sys.stderr.write(
                            f"[suppress_output] stdout close suppressed: {e}\n"
                        )
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
    """
    Create performance-focused logger using unified LoggerManager

    Args:
        name: Base name for the performance logger

    Returns:
        Configured performance logger
    """
    logger_manager = get_logger_manager()
    perf_logger_name = f"{name}.performance"
    return logger_manager.get_logger(perf_logger_name, logging.DEBUG)


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
        perf_logger.debug(message)
    except (ValueError, OSError) as e:
        if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
            with contextlib.suppress(Exception):
                sys.stderr.write(f"[log_performance] suppressed: {e}\n")


def setup_performance_logger() -> logging.Logger:
    """
    Set up performance logging (unified with create_performance_logger)

    Returns:
        Performance logger instance
    """
    # Delegate to the unified create_performance_logger
    return create_performance_logger("performance")


class LoggingContext:
    """Context manager for controlling logging behavior"""

    def __init__(self, enabled: bool = True, level: int | None = None):
        self.enabled = enabled
        self.level = level
        self.old_level: int | None = None
        # Use root logger for compatibility with existing tests
        self.target_logger = logging.getLogger()

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
