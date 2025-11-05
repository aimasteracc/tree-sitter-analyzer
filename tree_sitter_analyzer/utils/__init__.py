#!/usr/bin/env python3
"""
Utilities package for tree_sitter_analyzer.

This package contains utility modules for various functionality
including tree-sitter API compatibility and logging.
"""

# Import from tree-sitter compatibility module
# Import logging functions directly from logging module
from .logging import (
    LoggingContext,
    QuietMode,
    SafeStreamHandler,
    create_performance_logger,
    log_debug,
    log_error,
    log_info,
    log_performance,
    log_warning,
    logger,
    perf_logger,
    safe_print,
    setup_logger,
    setup_performance_logger,
    setup_safe_logging_shutdown,
    suppress_output,
)
from .tree_sitter_compat import TreeSitterQueryCompat, get_node_text_safe, log_api_info

__all__ = [
    # Tree-sitter compatibility
    "TreeSitterQueryCompat",
    "get_node_text_safe",
    "log_api_info",
    # Logging functionality
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
    "SafeStreamHandler",
    "setup_safe_logging_shutdown",
    "suppress_output",
    "logger",
    "perf_logger",
]
