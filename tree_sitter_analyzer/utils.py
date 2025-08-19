#!/usr/bin/env python3
"""
Utilities for Tree-sitter Analyzer

Provides logging, debugging, and common utility functions.
"""

import atexit
import logging
import os
import sys
from functools import wraps
from typing import Any


# Configure global logger
def setup_logger(
    name: str = "tree_sitter_analyzer", level: int = logging.WARNING
) -> logging.Logger:
    """Setup unified logger for the project"""
    # Get log level from environment variable
    env_level = os.environ.get("LOG_LEVEL", "").upper()
    if env_level == "DEBUG":
        level = logging.DEBUG
    elif env_level == "INFO":
        level = logging.INFO
    elif env_level == "WARNING":
        level = logging.WARNING
    elif env_level == "ERROR":
        level = logging.ERROR

    logger = logging.getLogger(name)

    if not logger.handlers:  # Avoid duplicate handlers
        # Create a safe handler that writes to stderr to avoid breaking MCP stdio
        handler = SafeStreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Also log to a local file for debugging when launched by clients (e.g., Cursor)
        # This helps diagnose cases where stdio is captured by the client and logs are hidden.
        try:
            file_handler = logging.FileHandler(
                "cursor_mcp_server.log", encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            # Never let logging configuration break runtime behavior; log to stderr if possible
            if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
                try:
                    sys.stderr.write(
                        f"[logging_setup] file handler init skipped: {e}\n"
                    )
                except Exception:
                    ...

        logger.setLevel(level)

    return logger


class SafeStreamHandler(logging.StreamHandler):
    """
    A StreamHandler that safely handles closed streams
    """

    def __init__(self, stream=None):
        # Default to sys.stderr to keep stdout clean for MCP stdio
        super().__init__(stream if stream is not None else sys.stderr)

    def emit(self, record: Any) -> None:
        """
        Emit a record, safely handling closed streams
        """
        try:
            # Check if stream is closed before writing
            if hasattr(self.stream, "closed") and self.stream.closed:
                return

            # Check if we can write to the stream
            if not hasattr(self.stream, "write"):
                return

            super().emit(record)
        except (ValueError, OSError, AttributeError):
            # Silently ignore I/O errors during shutdown
            pass
        except Exception:
            # For any other unexpected errors, use handleError
            self.handleError(record)


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
                            try:
                                sys.stderr.write(
                                    f"[logging_cleanup] handler close/remove skipped: {e}\n"
                                )
                            except Exception:
                                ...
        except Exception as e:
            if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
                try:
                    sys.stderr.write(f"[logging_cleanup] cleanup skipped: {e}\n")
                except Exception:
                    ...

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
            try:
                sys.stderr.write(f"[log_info] suppressed: {e}\n")
            except Exception:
                ...


def log_warning(message: str, *args: Any, **kwargs: Any) -> None:
    """Log warning message"""
    try:
        logger.warning(message, *args, **kwargs)
    except (ValueError, OSError) as e:
        if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
            try:
                sys.stderr.write(f"[log_warning] suppressed: {e}\n")
            except Exception:
                ...


def log_error(message: str, *args: Any, **kwargs: Any) -> None:
    """Log error message"""
    try:
        logger.error(message, *args, **kwargs)
    except (ValueError, OSError) as e:
        if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
            try:
                sys.stderr.write(f"[log_error] suppressed: {e}\n")
            except Exception:
                ...


def log_debug(message: str, *args: Any, **kwargs: Any) -> None:
    """Log debug message"""
    try:
        logger.debug(message, *args, **kwargs)
    except (ValueError, OSError) as e:
        if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
            try:
                sys.stderr.write(f"[log_debug] suppressed: {e}\n")
            except Exception:
                ...


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
                    try:
                        sys.stderr.write(
                            f"[suppress_output] stdout close suppressed: {e}\n"
                        )
                    except Exception:
                        ...
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


def safe_print(message: str, level: str = "info", quiet: bool = False) -> None:
    """Safe print function that can be controlled"""
    if quiet:
        return

    level_map = {
        "info": log_info,
        "warning": log_warning,
        "error": log_error,
        "debug": log_debug,
    }

    log_func = level_map.get(level.lower(), log_info)
    log_func(message)


def create_performance_logger(name: str) -> logging.Logger:
    """Create performance-focused logger"""
    perf_logger = logging.getLogger(f"{name}.performance")

    if not perf_logger.handlers:
        handler = SafeStreamHandler()
        formatter = logging.Formatter("%(asctime)s - PERF - %(message)s")
        handler.setFormatter(formatter)
        perf_logger.addHandler(handler)
        perf_logger.setLevel(logging.DEBUG)  # Change to DEBUG level

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
        if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
            try:
                sys.stderr.write(f"[log_performance] suppressed: {e}\n")
            except Exception:
                ...


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
        self.target_logger = (
            logging.getLogger()
        )  # Use root logger for compatibility with tests

    def __enter__(self) -> "LoggingContext":
        if self.enabled and self.level is not None:
            self.old_level = self.target_logger.level
            self.target_logger.setLevel(self.level)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.enabled and self.old_level is not None:
            self.target_logger.setLevel(self.old_level)
