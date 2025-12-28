#!/usr/bin/env python3
"""
Unit tests for split core components (TDD)
"""

import time

from tree_sitter_analyzer.core.performance import PerformanceMonitor
from tree_sitter_analyzer.core.request import AnalysisRequest


class TestCoreComponents:
    """Test suite for split core components"""

    def test_analysis_request_creation(self):
        """Test AnalysisRequest creation and defaults"""
        request = AnalysisRequest(file_path="test.py")
        assert request.file_path == "test.py"
        assert request.language is None
        assert request.include_complexity is True
        assert request.format_type == "json"

    def test_analysis_request_from_mcp(self):
        """Test AnalysisRequest conversion from MCP arguments"""
        args = {
            "file_path": "src/main.py",
            "language": "python",
            "include_complexity": False,
        }
        request = AnalysisRequest.from_mcp_arguments(args)
        assert request.file_path == "src/main.py"
        assert request.language == "python"
        assert request.include_complexity is False

    def test_performance_monitor_basic(self):
        """Test PerformanceMonitor basic functionality"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()

        with monitor.measure_operation("test_op"):
            time.sleep(0.01)

        stats = monitor.get_operation_stats()
        assert "test_op" in stats
        assert stats["test_op"]["count"] == 1
        assert stats["test_op"]["total_time"] > 0

        summary = monitor.get_performance_summary()
        assert summary["total_operations"] == 1
        assert summary["monitoring_active"] is True

    def test_performance_monitor_clear(self):
        """Test PerformanceMonitor metric clearing"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        with monitor.measure_operation("test_op"):
            pass

        monitor.clear_metrics()
        summary = monitor.get_performance_summary()
        assert summary["total_operations"] == 0
        assert summary["operation_count"] == 0
