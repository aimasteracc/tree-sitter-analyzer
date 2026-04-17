"""
Incremental analysis cache for tree-sitter-analyzer.

This module provides caching for analysis results to avoid re-parsing
and re-analyzing unchanged files across queries.
"""

from tree_sitter_analyzer.cache.incremental_cache import (
    CachedAnalysis,
    CacheEntry,
    CacheKey,
    IncrementalCacheManager,
)

__all__ = [
    "CacheEntry",
    "CacheKey",
    "CachedAnalysis",
    "IncrementalCacheManager",
]
