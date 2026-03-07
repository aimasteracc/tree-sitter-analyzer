#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.core.memory_monitor module.

Phase 3 Performance Enhancement Tests.
"""

import threading
import time
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.core.memory_monitor import PSUTIL_AVAILABLE, MemoryMonitor


class TestMemoryMonitor:
    """Test cases for MemoryMonitor class."""

    @pytest.fixture
    def monitor(self) -> MemoryMonitor:
        """Create a MemoryMonitor instance for testing."""
        return MemoryMonitor(
            memory_threshold_mb=100,  # Low threshold for testing
            check_interval_seconds=1,
        )

    @pytest.fixture
    def monitor_with_callback(self) -> MemoryMonitor:
        """Create a MemoryMonitor with eviction callback."""
        callback = MagicMock()
        return MemoryMonitor(
            memory_threshold_mb=100,
            check_interval_seconds=1,
            on_evict_callback=callback,
        )

    def test_initialization(self, monitor: MemoryMonitor) -> None:
        """Test MemoryMonitor initialization."""
        assert monitor._memory_threshold_mb == 100
        assert monitor._check_interval_seconds == 1
        assert monitor._monitoring is False
        assert monitor._monitor_thread is None

    def test_get_stats(self, monitor: MemoryMonitor) -> None:
        """Test statistics retrieval."""
        stats = monitor.get_stats()

        assert "checks" in stats
        assert "evictions_triggered" in stats
        assert "peak_memory_mb" in stats
        assert "current_memory_mb" in stats
        assert "threshold_mb" in stats
        assert "monitoring_active" in stats
        assert "psutil_available" in stats

        assert stats["threshold_mb"] == 100
        assert stats["monitoring_active"] is False
        assert stats["psutil_available"] == PSUTIL_AVAILABLE

    def test_check_memory_pressure(self, monitor: MemoryMonitor) -> None:
        """Test memory pressure checking."""
        is_high, current_mb = monitor.check_memory_pressure()

        assert isinstance(is_high, bool)
        assert isinstance(current_mb, float)
        assert current_mb >= 0

        # Check that stats were updated
        stats = monitor.get_stats()
        assert stats["checks"] == 1

    def test_get_memory_usage_mb(self, monitor: MemoryMonitor) -> None:
        """Test memory usage retrieval."""
        usage = monitor.get_memory_usage_mb()

        assert isinstance(usage, float)
        assert usage >= 0

    def test_get_system_memory_info(self, monitor: MemoryMonitor) -> None:
        """Test system memory info retrieval."""
        info = monitor.get_system_memory_info()

        assert isinstance(info, dict)
        assert "total_mb" in info
        assert "available_mb" in info
        assert "used_mb" in info
        assert "percent" in info

    def test_eviction_callback(self, monitor_with_callback: MemoryMonitor) -> None:
        """Test eviction callback is called."""
        monitor_with_callback.trigger_eviction(0.3)

        monitor_with_callback._on_evict_callback.assert_called_once_with(0.3)

        stats = monitor_with_callback.get_stats()
        assert stats["evictions_triggered"] == 1

    def test_eviction_no_callback(self, monitor: MemoryMonitor) -> None:
        """Test eviction without callback (should not raise)."""
        monitor.trigger_eviction(0.3)  # Should not raise

        stats = monitor.get_stats()
        assert stats["evictions_triggered"] == 0

    def test_start_stop_monitoring(self, monitor_with_callback: MemoryMonitor) -> None:
        """Test starting and stopping monitoring."""
        # Start monitoring
        monitor_with_callback.start_monitoring()
        assert monitor_with_callback._monitoring is True
        assert monitor_with_callback._monitor_thread is not None

        # Wait a bit for some checks
        time.sleep(0.5)

        # Stop monitoring
        monitor_with_callback.stop_monitoring()
        assert monitor_with_callback._monitoring is False

        stats = monitor_with_callback.get_stats()
        assert stats["monitoring_active"] is False

    def test_double_start(self, monitor: MemoryMonitor) -> None:
        """Test that double start is safe."""
        monitor.start_monitoring()
        monitor.start_monitoring()  # Should be idempotent

        assert monitor._monitoring is True
        monitor.stop_monitoring()

    def test_peak_memory_tracking(self, monitor: MemoryMonitor) -> None:
        """Test peak memory is tracked."""
        initial_peak = monitor.get_stats()["peak_memory_mb"]

        # Check memory multiple times
        for _ in range(3):
            monitor.check_memory_pressure()

        stats = monitor.get_stats()
        assert stats["peak_memory_mb"] >= initial_peak

    def test_eviction_ratio_calculation(self) -> None:
        """Test eviction ratio is calculated correctly."""
        callback = MagicMock()

        # Create monitor with very low threshold to trigger eviction
        monitor = MemoryMonitor(
            memory_threshold_mb=1,  # Very low to guarantee trigger
            check_interval_seconds=1,
            on_evict_callback=callback,
        )

        # Trigger eviction manually
        monitor.trigger_eviction(0.5)

        callback.assert_called_once_with(0.5)


class TestMemoryMonitorEdgeCases:
    """Edge case tests for MemoryMonitor."""

    def test_callback_exception_handling(self) -> None:
        """Test that callback exceptions are handled."""
        failing_callback = MagicMock(side_effect=RuntimeError("Test error"))

        monitor = MemoryMonitor(
            memory_threshold_mb=100,
            on_evict_callback=failing_callback,
        )

        # Should not raise
        monitor.trigger_eviction(0.3)

        # Stats should still be updated
        stats = monitor.get_stats()
        assert stats["evictions_triggered"] == 1

    def test_zero_threshold(self) -> None:
        """Test monitor with zero threshold."""
        monitor = MemoryMonitor(memory_threshold_mb=0)

        # Should always detect high memory
        is_high, _ = monitor.check_memory_pressure()
        assert is_high is True

    def test_concurrent_access(self) -> None:
        """Test thread safety of statistics."""
        monitor = MemoryMonitor(memory_threshold_mb=1000)
        monitor.start_monitoring()

        errors = []

        def check_repeatedly():
            try:
                for _ in range(10):
                    monitor.check_memory_pressure()
                    stats = monitor.get_stats()
                    assert isinstance(stats, dict)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=check_repeatedly) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        monitor.stop_monitoring()

        assert len(errors) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
