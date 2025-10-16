#!/usr/bin/env python3
"""
Utilities for Tree-sitter Analyzer

Provides logging, debugging, and common utility functions.
"""

import atexit
import logging
import os
import sys
import tempfile
from functools import wraps
from pathlib import Path
from typing import Any


# Configure global logger
def setup_logger(
    name: str = "tree_sitter_analyzer", level: int | str = logging.WARNING
) -> logging.Logger:
    """Setup unified logger for the project"""
    # Handle string level parameter
    if isinstance(level, str):
        level_upper = level.upper()
        if level_upper == "DEBUG":
            level = logging.DEBUG
        elif level_upper == "INFO":
            level = logging.INFO
        elif level_upper == "WARNING":
            level = logging.WARNING
        elif level_upper == "ERROR":
            level = logging.ERROR
        else:
            level = logging.WARNING  # Default fallback

    # Get log level from environment variable (only if set and not empty)
    env_level = os.environ.get("LOG_LEVEL", "").upper()
    if env_level and env_level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
        if env_level == "DEBUG":
            level = logging.DEBUG
        elif env_level == "INFO":
            level = logging.INFO
        elif env_level == "WARNING":
            level = logging.WARNING
        elif env_level == "ERROR":
            level = logging.ERROR
    # If env_level is empty or not recognized, use the passed level parameter

    logger = logging.getLogger(name)

    # Clear existing handlers if this is a test logger to ensure clean state
    if name.startswith("test_"):
        logger.handlers.clear()

    # Initialize file logging variables at function scope
    enable_file_log = (
        os.environ.get("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "").lower() == "true"
    )
    file_log_level = level  # Default to main logger level

    if not logger.handlers:  # Avoid duplicate handlers
        # Create a safe handler that writes to stderr to avoid breaking MCP stdio
        handler = SafeStreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Optional file logging for debugging when launched by clients (e.g., Cursor)
        # This helps diagnose cases where stdio is captured by the client and logs are hidden.
        # Only enabled when TREE_SITTER_ANALYZER_ENABLE_FILE_LOG is set to 'true'
        if enable_file_log:
            try:
                # Determine log directory
                log_dir = os.environ.get("TREE_SITTER_ANALYZER_LOG_DIR")
                if log_dir:
                    # Use specified directory
                    log_path = Path(log_dir) / "tree_sitter_analyzer.log"
                    # Ensure directory exists
                    Path(log_dir).mkdir(parents=True, exist_ok=True)
                else:
                    # Use system temporary directory
                    temp_dir = tempfile.gettempdir()
                    log_path = Path(temp_dir) / "tree_sitter_analyzer.log"

                # Determine file log level
                file_log_level_str = os.environ.get(
                    "TREE_SITTER_ANALYZER_FILE_LOG_LEVEL", ""
                ).upper()
                if file_log_level_str and file_log_level_str in [
                    "DEBUG",
                    "INFO",
                    "WARNING",
                    "ERROR",
                ]:
                    if file_log_level_str == "DEBUG":
                        file_log_level = logging.DEBUG
                    elif file_log_level_str == "INFO":
                        file_log_level = logging.INFO
                    elif file_log_level_str == "WARNING":
                        file_log_level = logging.WARNING
                    elif file_log_level_str == "ERROR":
                        file_log_level = logging.ERROR
                else:
                    # Use same level as main logger
                    file_log_level = level

                file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
                file_handler.setFormatter(formatter)
                file_handler.setLevel(file_log_level)
                logger.addHandler(file_handler)

                # Log the file location for debugging purposes
                if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
                    try:
                        sys.stderr.write(
                            f"[logging_setup] File logging enabled: {log_path}\n"
                        )
                    except Exception:
                        ...

            except Exception as e:
                # Never let logging configuration break runtime behavior; log to stderr if possible
                if hasattr(sys, "stderr") and hasattr(sys.stderr, "write"):
                    try:
                        sys.stderr.write(
                            f"[logging_setup] file handler init skipped: {e}\n"
                        )
                    except Exception:
                        ...

    # Set the logger level to the minimum of main level and file log level
    # This ensures that all messages that should go to any handler are processed
    final_level = level
    if enable_file_log:
        # Use the minimum level to ensure all messages reach their intended handlers
        final_level = min(level, file_log_level)

    logger.setLevel(final_level)

    # For test loggers, ensure they don't inherit from parent and force level
    if logger.name.startswith("test_"):
        logger.propagate = False
        # Force the level setting for test loggers
        logger.level = level

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
        Emit a record, safely handling closed streams and pytest capture
        """
        try:
            # Check if stream is closed before writing
            if hasattr(self.stream, "closed") and self.stream.closed:
                return

            # Check if we can write to the stream
            if not hasattr(self.stream, "write"):
                return

            # Special handling for pytest capture scenarios
            # Check if this is a pytest capture stream that might be problematic
            stream_name = getattr(self.stream, "name", "")
            if stream_name is None or "pytest" in str(type(self.stream)).lower():
                # For pytest streams, be extra cautious
                try:
                    # Just try to emit without any pre-checks
                    super().emit(record)
                    return
                except (ValueError, OSError, AttributeError, UnicodeError):
                    return

            # Additional safety checks for stream validity for non-pytest streams
            try:
                # Test if we can actually write to the stream without flushing
                # Avoid flush() as it can cause "I/O operation on closed file" in pytest
                if hasattr(self.stream, "writable") and not self.stream.writable():
                    return
            except (ValueError, OSError, AttributeError, UnicodeError):
                return

            super().emit(record)
        except (ValueError, OSError, AttributeError, UnicodeError):
            # Silently ignore I/O errors during shutdown or pytest capture
            pass
        except Exception:
            # For any other unexpected errors, silently ignore to prevent test failures
            pass


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
