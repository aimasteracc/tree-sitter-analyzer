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


# 向后兼容的统一服务入口。core 服务改为调用时延迟导入：导入本包会拉起
# core 解析栈（tree_sitter / chardet），曾使 MCP ``initialize`` 前多加载数十个模块。
def _core_services_available() -> bool:
    """调用时探测 core 缓存服务能否导入；不可用时兼容入口返回 None。"""
    try:
        from ...core.cache_service import CacheService  # noqa: F401
    except ImportError:
        return False
    return True


class BackwardCompatibleCacheManager:
    """Backward compatible cache manager wrapper"""

    def __init__(self) -> None:
        from ...core.cache_service import CacheService as UnifiedCacheService

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
    """返回统一缓存服务的兼容包装；core 服务不可用时返回 None。"""
    if not _core_services_available():
        return None
    return BackwardCompatibleCacheManager()


def get_performance_monitor() -> Any:
    """返回统一性能监视器；core 服务不可用时返回 None。"""
    if not _core_services_available():
        return None
    from ...core.performance import PerformanceMonitor

    return PerformanceMonitor()


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
    "format_for_file_output",
    "apply_output_format",
    "get_formatter",
    # Backward compatibility
    "get_cache_manager",
    "get_performance_monitor",
    # Module metadata
    "MCP_UTILS_CAPABILITIES",
]
