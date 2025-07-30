#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Utils Module

This module provides utility functions and classes for the MCP server
including error handling and other utilities.

Note: Cache and performance monitoring functionality has been moved to
the unified core services for better architecture.
"""

from typing import Any, Dict

# Module metadata
__version__ = "2.0.0"
__author__ = "Tree-Sitter Analyzer Team"

# MCP Utils capabilities
MCP_UTILS_CAPABILITIES = {
    "version": "2.0.0",
    "features": [
        "Comprehensive Error Handling",
        "Unified Core Services Integration",
    ],
    "deprecated_features": [
        "LRU Cache with TTL (moved to core.cache_service)",
        "Performance Monitoring (moved to core.analysis_engine)",
    ],
}

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

# Import unified services for backward compatibility
try:
    from ...core.cache_service import CacheService as UnifiedCacheService
    from ...core.analysis_engine import UnifiedAnalysisEngine
    
    # Provide backward compatibility aliases
    class BackwardCompatibleCacheManager:
        """Backward compatible cache manager wrapper"""
        def __init__(self):
            self._cache_service = UnifiedCacheService()
        
        def clear_all_caches(self):
            """Backward compatibility: clear all caches"""
            return self._cache_service.clear()
        
        def get_cache_stats(self):
            """Backward compatibility: get cache statistics"""
            return self._cache_service.get_stats()
        
        def __getattr__(self, name):
            """Delegate other methods to the cache service"""
            return getattr(self._cache_service, name)
    
    def get_cache_manager():
        """Backward compatibility: Get unified cache service"""
        return BackwardCompatibleCacheManager()
    
    def get_performance_monitor():
        """Backward compatibility: Get unified analysis engine for performance monitoring"""
        return UnifiedAnalysisEngine()
        
except ImportError:
    # Fallback if core services are not available
    def get_cache_manager():
        """Fallback cache manager"""
        return None
    
    def get_performance_monitor():
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
    # Backward compatibility
    "get_cache_manager",
    "get_performance_monitor",
    # Module metadata
    "MCP_UTILS_CAPABILITIES",
]
