#!/usr/bin/env python3
"""
Memory Monitoring Service

Provides memory usage monitoring and automatic cache eviction based on
memory pressure. Helps prevent OOM errors and maintains optimal performance.

Phase 3 Performance Enhancement.
"""

import threading
import time
from collections.abc import Callable

from ..utils import log_debug, log_info, log_warning

# Try to import psutil for memory monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    log_debug("psutil not available, using basic memory monitoring")


class MemoryMonitor:
    """
    Memory usage monitor with automatic cache eviction.

    Monitors system memory usage and triggers cache eviction when
    memory pressure exceeds configured thresholds.

    Attributes:
        _memory_threshold_mb: Memory threshold in MB for eviction
        _check_interval_seconds: How often to check memory
        _on_evict_callback: Callback to trigger cache eviction
        _monitoring: Whether monitoring is active
        _monitor_thread: Background monitoring thread
    """

    def __init__(
        self,
        memory_threshold_mb: int = 512,
        check_interval_seconds: int = 10,
        on_evict_callback: Callable[[float], None] | None = None,
    ) -> None:
        """
        Initialize memory monitor.

        Args:
            memory_threshold_mb: Memory threshold in MB before eviction
            check_interval_seconds: Interval between memory checks
            on_evict_callback: Callback(eviction_ratio) when memory is high
        """
        self._memory_threshold_mb = memory_threshold_mb
        self._check_interval_seconds = check_interval_seconds
        self._on_evict_callback = on_evict_callback
        self._monitoring = False
        self._monitor_thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Statistics
        self._stats = {
            "checks": 0,
            "evictions_triggered": 0,
            "total_evicted_mb": 0.0,
            "peak_memory_mb": 0.0,
        }

        log_debug(
            f"MemoryMonitor initialized: threshold={memory_threshold_mb}MB, "
            f"interval={check_interval_seconds}s"
        )

    def get_memory_usage_mb(self) -> float:
        """
        Get current process memory usage in MB.

        Returns:
            Memory usage in megabytes
        """
        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process()
                return float(process.memory_info().rss) / (1024 * 1024)
            except Exception as e:
                log_debug(f"Failed to get memory via psutil: {e}")

        # Fallback: use basic sys module
        # This gives less accurate results but works without psutil
        try:
            import resource  # Unix only
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        except Exception:
            # Windows or other platforms
            return 0.0

    def get_system_memory_info(self) -> dict:
        """
        Get system-wide memory information.

        Returns:
            Dictionary with total, available, used, percent
        """
        if PSUTIL_AVAILABLE:
            try:
                mem = psutil.virtual_memory()
                return {
                    "total_mb": mem.total / (1024 * 1024),
                    "available_mb": mem.available / (1024 * 1024),
                    "used_mb": mem.used / (1024 * 1024),
                    "percent": mem.percent,
                }
            except Exception:
                pass

        return {
            "total_mb": 0.0,
            "available_mb": 0.0,
            "used_mb": 0.0,
            "percent": 0.0,
        }

    def check_memory_pressure(self) -> tuple[bool, float]:
        """
        Check if memory usage exceeds threshold.

        Returns:
            Tuple of (is_pressure_high, current_usage_mb)
        """
        current_mb = self.get_memory_usage_mb()
        self._stats["checks"] += 1

        # Update peak memory
        if current_mb > self._stats["peak_memory_mb"]:
            self._stats["peak_memory_mb"] = current_mb

        is_high = current_mb > self._memory_threshold_mb
        return is_high, current_mb

    def trigger_eviction(self, eviction_ratio: float = 0.3) -> None:
        """
        Trigger cache eviction via callback.

        Args:
            eviction_ratio: Fraction of cache to evict (0.0-1.0)
        """
        if self._on_evict_callback:
            try:
                current_mb = self.get_memory_usage_mb()
                self._on_evict_callback(eviction_ratio)
                self._stats["evictions_triggered"] += 1
                self._stats["total_evicted_mb"] += current_mb * eviction_ratio

                log_info(
                    f"Memory eviction triggered: ratio={eviction_ratio:.1%}, "
                    f"current_memory={current_mb:.1f}MB"
                )
            except Exception as e:
                log_warning(f"Failed to trigger eviction: {e}")

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._monitoring:
            try:
                is_high, current_mb = self.check_memory_pressure()

                if is_high:
                    # Calculate eviction ratio based on how much over threshold
                    overage = current_mb - self._memory_threshold_mb
                    overage_ratio = min(overage / self._memory_threshold_mb, 0.5)
                    self.trigger_eviction(overage_ratio + 0.1)

                time.sleep(self._check_interval_seconds)
            except Exception as e:
                log_debug(f"Error in memory monitoring: {e}")
                time.sleep(self._check_interval_seconds)

    def start_monitoring(self) -> None:
        """Start background memory monitoring."""
        with self._lock:
            if self._monitoring:
                return

            self._monitoring = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="MemoryMonitor"
            )
            self._monitor_thread.start()
            log_info("Memory monitoring started")

    def stop_monitoring(self) -> None:
        """Stop background memory monitoring."""
        with self._lock:
            self._monitoring = False
            if self._monitor_thread:
                self._monitor_thread.join(timeout=5)
                self._monitor_thread = None
            log_info("Memory monitoring stopped")

    def get_stats(self) -> dict:
        """
        Get memory monitoring statistics.

        Returns:
            Dictionary with monitoring stats
        """
        return {
            **self._stats,
            "current_memory_mb": self.get_memory_usage_mb(),
            "threshold_mb": self._memory_threshold_mb,
            "monitoring_active": self._monitoring,
            "psutil_available": PSUTIL_AVAILABLE,
        }
