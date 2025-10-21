#!/usr/bin/env python3
"""
Utilities package for tree_sitter_analyzer.

This package contains utility modules for various functionality
including tree-sitter API compatibility.
"""

# Import from tree-sitter compatibility module
from .tree_sitter_compat import TreeSitterQueryCompat, get_node_text_safe, log_api_info
from typing import Any
import logging


# Re-export logging functions from the parent utils module
# We need to import these dynamically to avoid circular imports
def _import_logging_functions() -> tuple:
    """Dynamically import logging functions to avoid circular imports."""
    import importlib.util
    import os

    # Import the utils.py file from the parent directory
    parent_dir = os.path.dirname(os.path.dirname(__file__))
    utils_path = os.path.join(parent_dir, "utils.py")
    spec = importlib.util.spec_from_file_location(
        "tree_sitter_analyzer_utils", utils_path
    )
    if spec and spec.loader:
        utils_module = importlib.util.module_from_spec(spec)
        if utils_module:
            spec.loader.exec_module(utils_module)

    return (
        utils_module.setup_logger,
        utils_module.log_debug,
        utils_module.log_error,
        utils_module.log_warning,
        utils_module.log_info,
        utils_module.log_performance,
        utils_module.QuietMode,
        utils_module.safe_print,
        utils_module.LoggingContext,
        utils_module.setup_performance_logger,
        utils_module.create_performance_logger,
    )


# Import logging functions
try:
    (
        setup_logger,
        log_debug,
        log_error,
        log_warning,
        log_info,
        log_performance,
        QuietMode,
        safe_print,
        LoggingContext,
        setup_performance_logger,
        create_performance_logger,
    ) = _import_logging_functions()
except Exception:
    # Fallback logging functions if import fails
    def setup_logger(
        name: str = "tree_sitter_analyzer", level: int = 30
    ) -> "logging.Logger":
        import logging

        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(level)
        return logger

    def log_debug(msg: str, *args: Any, **kwargs: Any) -> None:
        pass

    def log_error(msg: str, *args: Any, **kwargs: Any) -> None:
        print(f"ERROR: {msg}", *args)

    def log_warning(msg: str, *args: Any, **kwargs: Any) -> None:
        print(f"WARNING: {msg}", *args)

    def log_info(msg: str, *args: Any, **kwargs: Any) -> None:
        print(f"INFO: {msg}", *args)

    def log_performance(
        operation: str, execution_time: float | None = None, details: str | None = None
    ) -> None:
        pass

    # Fallback QuietMode class
    class _FallbackQuietMode:
        def __init__(self, enabled: bool = True) -> None:
            self.enabled = enabled

        def __enter__(self) -> "_FallbackQuietMode":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    # Fallback LoggingContext class
    class _FallbackLoggingContext:
        def __init__(self, enabled: bool = True, level: int | None = None) -> None:
            self.enabled = enabled
            self.level = level

        def __enter__(self) -> "_FallbackLoggingContext":
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    def setup_performance_logger() -> "logging.Logger":
        import logging

        return logging.getLogger("performance")

    def create_performance_logger(name: str) -> "logging.Logger":
        import logging

        return logging.getLogger(f"{name}.performance")

    def safe_print(message: str, level: str = "info", quiet: bool = False) -> None:
        if not quiet:
            print(message)


__all__ = [
    "TreeSitterQueryCompat",
    "get_node_text_safe",
    "log_api_info",
    "setup_logger",
    "log_debug",
    "log_error",
    "log_warning",
    "log_info",
    "log_performance",
    "QuietMode",
    "safe_print",
    "LoggingContext",
    "setup_performance_logger",
    "create_performance_logger",
]
