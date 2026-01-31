#!/usr/bin/env python3
"""
Utilities Package for Tree-sitter Analyzer

This package provides centralized utility modules for logging, encoding,
performance monitoring, and other cross-cutting concerns.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive documentation
- Centralized imports for backward compatibility

Architecture:
- Modular design with clear separation of concerns
- Type-safe operations with PEP 484 compliance
- Thread-safe operations where applicable

Modules:
- logging: Centralized logging configuration
- encoding: Safe file operations with detection
- performance: Performance monitoring and metrics

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

from typing import TYPE_CHECKING, Any

# Type checking setup
if TYPE_CHECKING:
    # Tree-sitter compatibility
    # Encoding imports
    from ..encoding_utils import (
        ANYIO_AVAILABLE,
        CHARDET_AVAILABLE,
        detect_encoding,
        read_file_safe,
    )

    # Logging imports
    from .logging import (
        LoggingConfig,
        LoggingContext,
        create_performance_logger,
        log_debug,
        log_error,
        log_info,
        log_performance,
        log_warning,
        safe_print,
        setup_logger,
        setup_safe_logging_shutdown,
    )
    from .tree_sitter_compat import (
        TreeSitterQueryCompat,
        get_node_text_safe,
        log_api_info,
    )
else:
    # Runtime imports (when type checking is disabled)
    # Tree-sitter compatibility
    # Encoding imports
    from ..encoding_utils import (
        ANYIO_AVAILABLE,
        CHARDET_AVAILABLE,
        detect_encoding,
        read_file_safe,
    )

    # Logging imports
    from .logging import (
        LoggingConfig,
        LoggingContext,
        create_performance_logger,
        log_debug,
        log_error,
        log_info,
        log_performance,
        log_warning,
        setup_logger,
        setup_safe_logging_shutdown,
    )
    from .tree_sitter_compat import (
        TreeSitterQueryCompat,
        get_node_text_safe,
        log_api_info,
    )

# Version information
__version__: str = "1.10.5"
__author__: str = "aisheng.yu"
__email__: str = "aimasteracc@gmail.com"


# ============================================================================
# Public API
# ============================================================================

__all__: list[str] = [
    # Version
    "__version__",
    "__author__",
    "__email__",
    # Tree-sitter compatibility
    "TreeSitterQueryCompat",
    "get_node_text_safe",
    "log_api_info",
    # Logging functionality
    "LoggingConfig",
    "LoggingContext",
    "log_debug",
    "log_info",
    "log_warning",
    "log_error",
    "log_performance",
    "safe_print",
    "setup_logger",
    "create_performance_logger",
    "setup_safe_logging_shutdown",
    # Encoding utilities
    "read_file_safe",
    "detect_encoding",
    "CHARDET_AVAILABLE",
    "ANYIO_AVAILABLE",
]


# ============================================================================
# Convenience Functions
# ============================================================================


def get_logging_module() -> Any:
    """
    Get logging module (convenience function).

    Returns:
        The logging module object
    """
    from . import logging as logging_module

    return logging_module


def get_tree_sitter_compat_module() -> Any:
    """
    Get tree-sitter compatibility module (convenience function).

    Returns:
        The tree-sitter compatibility module object
    """
    from .. import tree_sitter_compat as compat_module

    return compat_module


def get_encoding_module() -> Any:
    """
    Get encoding utilities module (convenience function).

    Returns:
        The encoding utilities module object
    """
    from .. import encoding_utils as encoding_module

    return encoding_module


def get_performance_logger() -> Any:
    """
    Get performance logger (convenience function).

    Returns:
        Performance logger instance
    """
    return create_performance_logger("tree_sitter_analyzer.utils")


# ============================================================================
# Module-level exports for backward compatibility
# ============================================================================


def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Name of the module, class, or function to import

    Returns:
        Imported module, class, or function

    Raises:
        ImportError: If the requested component is not found
    """
    # Handle specific imports first
    if name in [
        "TreeSitterQueryCompat",
        "get_node_text_safe",
        "log_api_info",
    ]:
        from .tree_sitter_compat import (
            TreeSitterQueryCompat,
            get_node_text_safe,
            log_api_info,
        )

        if name == "TreeSitterQueryCompat":
            return TreeSitterQueryCompat
        elif name == "get_node_text_safe":
            return get_node_text_safe
        elif name == "log_api_info":
            return log_api_info

    # Handle logging imports
    elif name in [
        "LoggerConfig",
        "LoggingContext",
        "QuietMode",
        "log_debug",
        "log_info",
        "log_warning",
        "log_error",
        "log_performance",
        "setup_logger",
        "create_performance_logger",
        "safe_print",
        "setup_safe_logging_shutdown",
        "suppress_output",
    ]:
        from .logging import (
            LoggerConfig,
            LoggingContext,
            QuietMode,
            create_performance_logger,
            log_debug,
            log_error,
            log_info,
            log_performance,
            log_warning,
            safe_print,
            setup_logger,
            setup_safe_logging_shutdown,
            suppress_output,
        )

        if name == "LoggerConfig":
            return LoggerConfig
        elif name == "LoggingContext":
            return LoggingContext
        elif name == "QuietMode":
            return QuietMode
        elif name == "log_debug":
            return log_debug
        elif name == "log_info":
            return log_info
        elif name == "log_warning":
            return log_warning
        elif name == "log_error":
            return log_error
        elif name == "log_performance":
            return log_performance
        elif name == "setup_logger":
            return setup_logger
        elif name == "create_performance_logger":
            return create_performance_logger
        elif name == "safe_print":
            return safe_print
        elif name == "setup_safe_logging_shutdown":
            return setup_safe_logging_shutdown
        elif name == "suppress_output":
            return suppress_output

    # Handle encoding imports
    elif name in [
        "EncodingManager",
        "detect_encoding",
        "extract_text_slice",
        "read_file_safe",
        "safe_decode",
        "safe_encode",
        "write_file_safe",
        "EncodingManagerType",
        "FilePath",
        "TextEncoding",
        "DecodedText",
        "read_file_safe_streaming",
        "clear_encoding_cache",
        "get_encoding_cache_size",
    ]:
        from ..encoding_utils import (
            EncodingManager,
            clear_encoding_cache,
            detect_encoding,
            extract_text_slice,
            get_encoding_cache_size,
            read_file_safe,
            read_file_safe_streaming,
            safe_decode,
            safe_encode,
            write_file_safe,
        )

        if name == "EncodingManager":
            return EncodingManager
        elif name == "detect_encoding":
            return detect_encoding
        elif name == "extract_text_slice":
            return extract_text_slice
        elif name == "read_file_safe":
            return read_file_safe
        elif name == "safe_decode":
            return safe_decode
        elif name == "safe_encode":
            return safe_encode
        elif name == "write_file_safe":
            return write_file_safe
        elif name == "read_file_safe_streaming":
            return read_file_safe_streaming
        elif name == "clear_encoding_cache":
            return clear_encoding_cache
        elif name == "get_encoding_cache_size":
            return get_encoding_cache_size

    # Default behavior
    try:
        # Try to import from current package
        module = __import__(f".{name}", fromlist=["__name__"])
        return module
    except ImportError:
        raise ImportError(f"Module {name} not found in utils package") from None
