#!/usr/bin/env python3
"""
Enhanced Cache Service with Memory Monitoring

Extends the base CacheService with:
- Memory-based automatic eviction
- Integration with CachePrewarmer
- Enhanced statistics

Phase 3 Performance Enhancement.
"""

import threading
from typing import Any, Callable, Optional

from cachetools import LRUCache, TTLCache

from ..utils import log_debug, log_info, log_warning
from .cache_prewarming import CachePrewarmer
from .cache_service import CacheEntry, CacheService
from .memory_monitor import MemoryMonitor


class EnhancedCacheService(CacheService):
    """
    Enhanced cache service with memory monitoring and prewarming.
    
    Extends CacheService with:
    - Automatic memory-based eviction
    - Cache prewarming integration
    - Enhanced statistics including memory usage
    
    Attributes:
        _memory_monitor: Memory monitoring service
        _prewarmer: Cache prewarming service
        _on_evict_callback: External eviction callback
    """
    
    def __init__(
        self,
        l1_maxsize: int = 100,
        l2_maxsize: int = 1000,
        l3_maxsize: int = 10000,
        ttl_seconds: int = 3600,
        memory_threshold_mb: int = 512,
        enable_monitoring: bool = True,
        enable_prewarming: bool = True,
    ) -> None:
        """
        Initialize enhanced cache service.
        
        Args:
            l1_maxsize: Maximum size of L1 cache
            l2_maxsize: Maximum size of L2 cache
            l3_maxsize: Maximum size of L3 cache
            ttl_seconds: Default TTL (seconds)
            memory_threshold_mb: Memory threshold for eviction
            enable_monitoring: Enable memory monitoring
            enable_prewarming: Enable cache prewarming
        """
        # Initialize base cache service
        super().__init__(
            l1_maxsize=l1_maxsize,
            l2_maxsize=l2_maxsize,
            l3_maxsize=l3_maxsize,
            ttl_seconds=ttl_seconds,
        )
        
        self._memory_threshold_mb = memory_threshold_mb
        self._on_evict_callback: Optional[Callable[[float], None]] = None
        
        # Initialize memory monitor
        self._memory_monitor: Optional[MemoryMonitor] = None
        if enable_monitoring:
            self._memory_monitor = MemoryMonitor(
                memory_threshold_mb=memory_threshold_mb,
                check_interval_seconds=30,
                on_evict_callback=self._handle_memory_pressure,
            )
            self._memory_monitor.start_monitoring()
            log_info(f"Memory monitoring started (threshold: {memory_threshold_mb}MB)")
        
        # Initialize cache prewarmer
        self._prewarmer: Optional[CachePrewarmer] = None
        if enable_prewarming:
            self._prewarmer = CachePrewarmer(
                max_prewarm_files=50,
                min_access_count=3,
            )
            # Set callback to preload into cache
            self._prewarmer.set_prewarm_callback(self._prewarm_file)
            log_debug("Cache prewarming enabled")
    
    def _handle_memory_pressure(self, eviction_ratio: float) -> None:
        """
        Handle memory pressure by evicting cache entries.
        
        Args:
            eviction_ratio: Fraction of cache to evict
        """
        log_warning(
            f"Memory pressure detected, evicting {eviction_ratio:.1%} of cache"
        )
        
        with self._lock:
            # Calculate number of entries to evict from each tier
            l1_evict = max(1, int(len(self._l1_cache) * eviction_ratio))
            l2_evict = max(1, int(len(self._l2_cache) * eviction_ratio))
            l3_evict = max(1, int(len(self._l3_cache) * eviction_ratio))
            
            # Evict from L3 first (least frequently accessed)
            self._evict_oldest(self._l3_cache, l3_evict)
            
            # Then from L2
            self._evict_oldest(self._l2_cache, l2_evict)
            
            # Finally from L1 if needed
            if eviction_ratio > 0.5:
                self._evict_oldest(self._l1_cache, l1_evict)
            
            self._stats["evictions"] += l1_evict + l2_evict + l3_evict
        
        # Call external callback if set
        if self._on_evict_callback:
            try:
                self._on_evict_callback(eviction_ratio)
            except Exception as e:
                log_warning(f"Eviction callback error: {e}")
    
    def _evict_oldest(self, cache: Any, count: int) -> None:
        """
        Evict oldest entries from a cache.
        
        Args:
            cache: Cache to evict from
            count: Number of entries to evict
        """
        if not hasattr(cache, 'popitem'):
            return
        
        for _ in range(min(count, len(cache))):
            try:
                cache.popitem(last=False)  # Evict oldest
            except KeyError:
                break
    
    async def _prewarm_file(self, file_path: str) -> None:
        """
        Prewarm a file into cache.
        
        Args:
            file_path: Path to file to prewarm
        """
        # This is a placeholder - actual implementation would load and cache
        # the file analysis result
        log_debug(f"Prewarming file: {file_path}")
        # In real implementation, would call analysis engine here
    
    def set_eviction_callback(self, callback: Callable[[float], None]) -> None:
        """
        Set callback for memory-based evictions.
        
        Args:
            callback: Function to call with eviction ratio
        """
        self._on_evict_callback = callback
    
    def record_file_access(self, file_path: str, load_time_ms: float = 0.0) -> None:
        """
        Record file access for prewarming analysis.
        
        Args:
            file_path: Path to accessed file
            load_time_ms: Time taken to load file
        """
        if self._prewarmer:
            self._prewarmer.record_access(file_path, load_time_ms)
    
    async def prewarm_cache(self) -> dict[str, Any]:
        """
        Prewarm cache with predicted files.
        
        Returns:
            Prewarming results
        """
        if not self._prewarmer:
            return {"status": "prewarming_disabled", "files_prewarmed": 0}
        
        return await self._prewarmer.prewarm_cache()
    
    def get_enhanced_stats(self) -> dict[str, Any]:
        """
        Get enhanced statistics including memory and prewarming.
        
        Returns:
            Dictionary with comprehensive statistics
        """
        base_stats = self.get_stats()
        
        enhanced = {
            **base_stats,
            "memory_monitoring": {},
            "prewarming": {},
        }
        
        # Add memory monitoring stats
        if self._memory_monitor:
            enhanced["memory_monitoring"] = self._memory_monitor.get_stats()
        
        # Add prewarming stats
        if self._prewarmer:
            enhanced["prewarming"] = self._prewarmer.get_stats()
        
        return enhanced
    
    def clear(self) -> None:
        """Clear all caches and reset statistics."""
        super().clear()
        
        if self._prewarmer:
            self._prewarmer.clear_patterns()
    
    def shutdown(self) -> None:
        """Shutdown enhanced cache service."""
        if self._memory_monitor:
            self._memory_monitor.stop_monitoring()
            log_info("Memory monitoring stopped")
        
        self.clear()
        log_info("Enhanced cache service shutdown complete")
    
    def __del__(self) -> None:
        """Destructor - ensure cleanup."""
        try:
            self.shutdown()
        except Exception:
            pass


# Singleton instance
_enhanced_cache_service: Optional[EnhancedCacheService] = None
_service_lock = threading.Lock()


def get_enhanced_cache_service(
    memory_threshold_mb: int = 512,
    **kwargs: Any,
) -> EnhancedCacheService:
    """
    Get or create enhanced cache service singleton.
    
    Args:
        memory_threshold_mb: Memory threshold in MB
        **kwargs: Additional arguments for EnhancedCacheService
    
    Returns:
        EnhancedCacheService singleton instance
    """
    global _enhanced_cache_service
    
    with _service_lock:
        if _enhanced_cache_service is None:
            _enhanced_cache_service = EnhancedCacheService(
                memory_threshold_mb=memory_threshold_mb,
                **kwargs,
            )
        return _enhanced_cache_service
