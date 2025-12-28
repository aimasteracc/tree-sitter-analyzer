#!/usr/bin/env python3
"""
Performance Monitoring System for Tree-sitter Analyzer
"""

import time
from typing import Any

from ..utils import log_info, log_performance


class PerformanceMonitor:
    """Performance monitoring (simplified version)"""

    def __init__(self) -> None:
        self._last_duration: float = 0.0
        self._monitoring_active: bool = False
        self._operation_stats: dict[str, Any] = {}
        self._total_operations: int = 0

    def measure_operation(self, operation_name: str) -> "PerformanceContext":
        """Return measurement context for operation"""
        return PerformanceContext(operation_name, self)

    def get_last_duration(self) -> float:
        """Get last operation time"""
        return self._last_duration

    def _set_duration(self, duration: float) -> None:
        """Set operation time (internal use)"""
        self._last_duration = duration

    def start_monitoring(self) -> None:
        """Start performance monitoring"""
        self._monitoring_active = True
        log_info("Performance monitoring started")

    def stop_monitoring(self) -> None:
        """Stop performance monitoring"""
        self._monitoring_active = False
        log_info("Performance monitoring stopped")

    def get_operation_stats(self) -> dict[str, Any]:
        """Get operation statistics"""
        return self._operation_stats.copy()

    def get_performance_summary(self) -> dict[str, Any]:
        """Get performance summary"""
        return {
            "total_operations": self._total_operations,
            "monitoring_active": self._monitoring_active,
            "last_duration": self._last_duration,
            "operation_count": len(self._operation_stats),
        }

    def record_operation(self, operation_name: str, duration: float) -> None:
        """Record operation"""
        if self._monitoring_active:
            if operation_name not in self._operation_stats:
                self._operation_stats[operation_name] = {
                    "count": 0,
                    "total_time": 0.0,
                    "avg_time": 0.0,
                    "min_time": float("inf"),
                    "max_time": 0.0,
                }

            stats = self._operation_stats[operation_name]
            stats["count"] += 1
            stats["total_time"] += duration
            stats["avg_time"] = stats["total_time"] / stats["count"]
            stats["min_time"] = min(stats["min_time"], duration)
            stats["max_time"] = max(stats["max_time"], duration)

            self._total_operations += 1

    def clear_metrics(self) -> None:
        """Clear collected metrics"""
        self._operation_stats.clear()
        self._total_operations = 0
        self._last_duration = 0.0
        log_info("Performance metrics cleared")


class PerformanceContext:
    """Performance measurement context"""

    def __init__(self, operation_name: str, monitor: PerformanceMonitor) -> None:
        self.operation_name = operation_name
        self.monitor = monitor
        self.start_time: float = 0.0

    def __enter__(self) -> "PerformanceContext":
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        duration = time.time() - self.start_time
        self.monitor._set_duration(duration)
        self.monitor.record_operation(self.operation_name, duration)
        log_performance(self.operation_name, duration, "Operation completed")
