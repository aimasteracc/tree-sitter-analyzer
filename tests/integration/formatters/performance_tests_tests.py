"""Performance test classes - actual pytest test cases.

Helper classes (PerformanceMetrics, ScalabilityTestResult, PerformanceBaseline,
PerformanceProfiler, PerformanceTester, FormatPerformanceTester) are in
performance_tests_helpers.py.
"""

import pytest

from tests.integration.formatters.performance_tests_helpers import (
    PerformanceMetrics,
    PerformanceProfiler,
    PerformanceTester,
)


class TestPerformanceProfiler:
    """Tests for PerformanceProfiler."""

    def test_start_stop_profiling(self):
        profiler = PerformanceProfiler()
        profiler.start_profiling()
        metrics = profiler.stop_profiling()
        assert "execution_time_ms" in metrics
        assert isinstance(metrics["execution_time_ms"], (int, float))
        assert "memory_usage_mb" in metrics
        assert "peak_memory_mb" in metrics

    def test_stop_without_start_raises(self):
        profiler = PerformanceProfiler()
        with pytest.raises(RuntimeError, match="Profiling not started"):
            profiler.stop_profiling()

    def test_start_profiling_resets_baseline(self):
        profiler = PerformanceProfiler()
        profiler.start_profiling()
        assert isinstance(profiler.baseline_memory, (int, float))
        assert isinstance(profiler.start_time, float)


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics dataclass."""

    def test_metrics_creation(self):
        from datetime import datetime, timezone

        metrics = PerformanceMetrics(
            test_name="test",
            execution_time_ms=100.0,
            memory_usage_mb=10.0,
            peak_memory_mb=15.0,
            cpu_usage_percent=50.0,
            throughput_ops_per_sec=10.0,
            file_size_bytes=1024,
            element_count=5,
            format_type="full",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=True,
        )
        assert metrics.test_name == "test"
        assert metrics.execution_time_ms == 100.0
        assert metrics.success is True
        assert metrics.error_message is None

    def test_metrics_with_error(self):
        from datetime import datetime, timezone

        metrics = PerformanceMetrics(
            test_name="fail",
            execution_time_ms=0,
            memory_usage_mb=0,
            peak_memory_mb=0,
            cpu_usage_percent=0,
            throughput_ops_per_sec=0,
            file_size_bytes=0,
            element_count=0,
            format_type="full",
            timestamp=datetime.now(timezone.utc).isoformat(),
            success=False,
            error_message="boom",
        )
        assert metrics.success is False
        assert metrics.error_message == "boom"


class TestPerformanceTesterHelpers:
    """Tests for PerformanceTester helper methods."""

    def test_estimate_element_count_with_list(self):
        tester = PerformanceTester()
        assert tester._estimate_element_count([1, 2, 3]) == 3

    def test_estimate_element_count_with_string(self):
        tester = PerformanceTester()
        result = tester._estimate_element_count("line1\nline2\nline3")
        assert isinstance(result, int)
        assert result == 3

    def test_estimate_element_count_with_scalar(self):
        tester = PerformanceTester()
        assert tester._estimate_element_count(42) == 1

    def test_calculate_scalability_factor_single(self):
        tester = PerformanceTester()
        assert tester._calculate_scalability_factor([100], [1.0]) == 1.0

    def test_calculate_scalability_factor_linear(self):
        tester = PerformanceTester()
        factor = tester._calculate_scalability_factor([100, 200, 400], [1.0, 2.0, 4.0])
        assert isinstance(factor, float)
