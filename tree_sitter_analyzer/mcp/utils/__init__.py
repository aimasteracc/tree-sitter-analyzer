#!/usr/bin/env python3
"""
MCP Utils Module

This module provides utility functions and classes for the MCP server
including error handling and other utilities.

Note: Cache and performance monitoring functionality has been moved to
the unified core services for better architecture.
"""

from typing import Any

# Export main utility classes and functions
from .error_handler import (
    AnalysisError,
    ErrorCategory,
    ErrorHandler,
    ErrorSeverity,
    FileAccessError,
    MCPError,
    ParsingError,
    ResourceError,
    ValidationError,
    get_error_handler,
    handle_mcp_errors,
)

# Export format helper utilities
from .format_helper import (
    apply_output_format,
    format_as_json,
    format_as_toon,
    format_for_file_output,
    format_output,
    get_formatter,
)

# Export path resolver utilities
from .path_resolver import PathResolver, resolve_path

# Module metadata
__author__ = "Tree-Sitter Analyzer Team"

# MCP Utils capabilities
MCP_UTILS_CAPABILITIES = {
    "version": "1.1.0",
    "features": [
        "Comprehensive Error Handling",
        "Unified Core Services Integration",
        "Cross-Platform Path Resolution",
    ],
    "deprecated_features": [
        "LRU Cache with TTL (moved to core.cache_service)",
        "Performance Monitoring (moved to core.analysis_engine)",
    ],
}

# Import unified services for backward compatibility
try:
    from ...core.cache_service import CacheService as UnifiedCacheService

    # Provide backward compatibility aliases
    class BackwardCompatibleCacheManager:
        """Backward compatible cache manager wrapper"""

        def __init__(self) -> None:
            self._cache_service = UnifiedCacheService()

        def clear_all_caches(self) -> None:
            """Backward compatibility: clear all caches"""
            return self._cache_service.clear()

        def get_cache_stats(self) -> dict[str, Any]:
            """Backward compatibility: get cache statistics"""
            return self._cache_service.get_stats()

        def __getattr__(self, name: str) -> Any:
            """Delegate other methods to the cache service"""
            return getattr(self._cache_service, name)

    def get_cache_manager() -> Any:
        """Backward compatibility: Get unified cache service"""
        return BackwardCompatibleCacheManager()

    def get_performance_monitor() -> Any:
        """Backward compatibility: Get unified performance monitor"""
        from ...core.performance import PerformanceMonitor

        return PerformanceMonitor()

except ImportError:
    # Fallback if core services are not available
    def get_cache_manager() -> Any:
        """Fallback cache manager"""
        return None

    def get_performance_monitor() -> Any:
        """Fallback performance monitor"""
        return None


__all__ = [
    # Error handling
    "ErrorHandler",
    "MCPError",
    "FileAccessError",
    "ParsingError",
    "AnalysisError",
    "ValidationError",
    "ResourceError",
    "ErrorSeverity",
    "ErrorCategory",
    "handle_mcp_errors",
    "get_error_handler",
    # Path resolution
    "PathResolver",
    "resolve_path",
    # Format helpers
    "format_output",
    "format_as_json",
    "format_as_toon",
    "format_for_file_output",
    "apply_output_format",
    "get_formatter",
    # Backward compatibility
    "get_cache_manager",
    "get_performance_monitor",
    # Module metadata
    "MCP_UTILS_CAPABILITIES",
]
