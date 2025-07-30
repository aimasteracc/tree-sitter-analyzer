#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utilities for Tree-sitter Analyzer

Provides logging, debugging, and common utility functions.
"""

import logging
import sys
from functools import wraps
from typing import Any, Optional


# Configure global logger
def setup_logger(
    name: str = "tree_sitter_analyzer", level: int = logging.INFO
) -> logging.Logger:
    """Setup unified logger for the project"""
    import os
    
    # 環境変数からログレベルを取得
    env_level = os.environ.get('LOG_LEVEL', '').upper()
    if env_level == 'DEBUG':
        level = logging.DEBUG
    elif env_level == 'INFO':
        level = logging.INFO
    elif env_level == 'WARNING':
        level = logging.WARNING
    elif env_level == 'ERROR':
        level = logging.ERROR
    
    logger = logging.getLogger(name)

    if not logger.handlers:  # Avoid duplicate handlers
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)

    return logger


# Global logger instance
logger = setup_logger()


def log_info(message: str, *args: Any, **kwargs: Any) -> None:
    """Log info message"""
    logger.info(message, *args, **kwargs)


def log_warning(message: str, *args: Any, **kwargs: Any) -> None:
    """Log warning message"""
    logger.warning(message, *args, **kwargs)


def log_error(message: str, *args: Any, **kwargs: Any) -> None:
    """Log error message"""
    logger.error(message, *args, **kwargs)


def log_debug(message: str, *args: Any, **kwargs: Any) -> None:
    """Log debug message"""
    logger.debug(message, *args, **kwargs)


def suppress_output(func: Any) -> Any:
    """Decorator to suppress print statements in production"""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Check if we're in test/debug mode
        if getattr(sys, "_testing", False):
            return func(*args, **kwargs)

        # Redirect stdout to suppress prints
        old_stdout = sys.stdout
        sys.stdout = (
            open("/dev/null", "w") if sys.platform != "win32" else open("nul", "w")
        )

        try:
            result = func(*args, **kwargs)
        finally:
            sys.stdout.close()
            sys.stdout = old_stdout

        return result

    return wrapper


class QuietMode:
    """Context manager for quiet execution"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.old_level: Optional[int] = None

    def __enter__(self) -> "QuietMode":
        if self.enabled:
            self.old_level = logger.level
            logger.setLevel(logging.ERROR)
        return self  # type: ignore

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
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - PERF - %(message)s")
        handler.setFormatter(formatter)
        perf_logger.addHandler(handler)
        perf_logger.setLevel(logging.INFO)

    return perf_logger


# Performance logger instance
perf_logger = create_performance_logger("tree_sitter_analyzer")


def log_performance(
    operation: str,
    execution_time: Optional[float] = None,
    details: Optional[dict] = None,
) -> None:
    """Log performance metrics"""
    message = f"{operation}"
    if execution_time is not None:
        message += f": {execution_time:.4f}s"
    if details:
        if isinstance(details, dict):
            detail_str = ", ".join([f"{k}: {v}" for k, v in details.items()])
        else:
            detail_str = str(details)
        message += f" - {detail_str}"
    perf_logger.info(message)


def setup_performance_logger() -> logging.Logger:
    """Set up performance logging"""
    perf_logger = logging.getLogger("performance")

    # Add handler if not already configured
    if not perf_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - Performance - %(message)s")
        handler.setFormatter(formatter)
        perf_logger.addHandler(handler)
        perf_logger.setLevel(logging.INFO)

    return perf_logger


class LoggingContext:
    """Context manager for controlling logging behavior"""

    def __init__(self, enabled: bool = True, level: Optional[int] = None):
        self.enabled = enabled
        self.level = level
        self.old_level: Optional[int] = None
        self.target_logger = (
            logging.getLogger()
        )  # Use root logger for compatibility with tests

    def __enter__(self) -> "LoggingContext":
        if self.enabled and self.level is not None:
            self.old_level = self.target_logger.level
            self.target_logger.setLevel(self.level)
        return self  # type: ignore

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.enabled and self.old_level is not None:
            self.target_logger.setLevel(self.old_level)
