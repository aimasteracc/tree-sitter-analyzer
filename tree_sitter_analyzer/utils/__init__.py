#!/usr/bin/env python3
"""
Utilities Package for Tree-sitter Analyzer

This package provides utility modules for various functionality
including tree-sitter API compatibility, logging, performance monitoring,
and encoding handling.

Architecture:
- Logging: Centralized logging configuration with multiple loggers
- Tree-sitter Compatibility: Unified API for different tree-sitter versions
- Encoding: Safe file operations with encoding detection
- Performance: Performance monitoring and metrics
- Caching: High-performance caching utilities

Features:
- Type-safe operations (PEP 484)
- Thread-safe logging
- Performance monitoring and metrics
- Safe file operations
- Tree-sitter version compatibility layer
"""

from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, Callable, Type
import logging as stdlib_logging

# Configure logging
logger = stdlib_logging.getLogger(__name__)

if TYPE_CHECKING:
    # Tree-sitter compatibility imports
    from .tree_sitter_compat import (
        TreeSitterQueryCompat,
        get_node_text_safe,
        log_api_info,
    )
    
    # Logging imports
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
        safe_print,
        setup_logger,
        setup_performance_logger,
        setup_safe_logging_shutdown,
        suppress_output,
    )
    
    # Encoding imports
    from .encoding_utils import (
        EncodingManager,
        detect_encoding,
        extract_text_slice,
        read_file_safe,
        safe_decode,
        safe_encode,
        write_file_safe,
    )


# Export for backward compatibility
__all__: List[str] = [
    # Tree-sitter compatibility
    "TreeSitterQueryCompat",
    "get_node_text_safe",
    "log_api_info",
    
    # Logging functionality
    "LoggingContext",
    "QuietMode",
    "SafeStreamHandler",
    "create_performance_logger",
    "log_debug",
    "log_info",
    "log_warning",
    "log_error",
    "log_performance",
    "safe_print",
    "setup_logger",
    "setup_performance_logger",
    "setup_safe_logging_shutdown",
    "suppress_output",
    
    # Encoding utilities
    "EncodingManager",
    "detect_encoding",
    "extract_text_slice",
    "read_file_safe",
    "safe_decode",
    "safe_encode",
    "write_file_safe",
]


# Convenience functions for quick access

def get_logging_module() -> Any:
    """
    Get the logging module (convenience function).

    Returns:
        The logging module object

    Note:
        - Provides quick access to logging functionality
        - Used for backwards compatibility
    """
    from . import logging
    return logging


def get_tree_sitter_compat_module() -> Any:
    """
    Get the tree-sitter compatibility module (convenience function).

    Returns:
        The tree_sitter compatibility module object

    Note:
        - Provides quick access to tree-sitter compatibility
        - Used for backwards compatibility
    """
    from . import tree_sitter_compat
    return tree_sitter_compat


def get_encoding_module() -> Any:
    """
    Get the encoding utilities module (convenience function).

    Returns:
        The encoding utilities module object

    Note:
        - Provides quick access to encoding functionality
        - Used for backwards compatibility
    """
    from . import encoding_utils
    return encoding_utils
