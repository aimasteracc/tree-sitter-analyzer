#!/usr/bin/env python3
"""
Performance Monitor 单元测试
"""

import time
from unittest.mock import patch

from tree_sitter_analyzer.core.performance import (
    PerformanceContext,
    PerformanceMonitor,
)


class TestPerformanceMonitor:
    """PerformanceMonitor测试类"""

    def test_init(self):
        """测试PerformanceMonitor初始化"""
        monitor = PerformanceMonitor()
        assert monitor._last_duration == 0.0
        assert monitor._monitoring_active is False
        assert monitor._operation_stats == {}
        assert monitor._total_operations == 0

    def test_measure_operation(self):
        """测试measure_operation方法"""
        monitor = PerformanceMonitor()
        context = monitor.measure_operation("test_operation")
        assert isinstance(context, PerformanceContext)
        assert context.operation_name == "test_operation"
        assert context.monitor == monitor

    def test_get_last_duration(self):
        """测试get_last_duration方法"""
        monitor = PerformanceMonitor()
        assert monitor.get_last_duration() == 0.0

    def test_set_duration_internal(self):
        """测试_set_duration内部方法"""
        monitor = PerformanceMonitor()
        monitor._set_duration(1.5)
        assert monitor.get_last_duration() == 1.5

    def test_start_monitoring(self):
        """测试start_monitoring方法"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        assert monitor._monitoring_active is True

    def test_stop_monitoring(self):
        """测试stop_monitoring方法"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        monitor.stop_monitoring()
        assert monitor._monitoring_active is False

    @patch("tree_sitter_analyzer.core.performance.log_info")
    def test_start_monitoring_logs(self, mock_log):
        """测试start_monitoring日志输出"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        mock_log.assert_called_once_with("Performance monitoring started")

    @patch("tree_sitter_analyzer.core.performance.log_info")
    def test_stop_monitoring_logs(self, mock_log):
        """测试stop_monitoring日志输出"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        monitor.stop_monitoring()
        mock_log.assert_called_with("Performance monitoring stopped")

    def test_get_operation_stats(self):
        """测试get_operation_stats方法"""
        monitor = PerformanceMonitor()
        stats = monitor.get_operation_stats()
        assert stats == {}
        assert isinstance(stats, dict)

    def test_get_performance_summary(self):
        """测试get_performance_summary方法"""
        monitor = PerformanceMonitor()
        summary = monitor.get_performance_summary()
        assert summary["total_operations"] == 0
        assert summary["monitoring_active"] is False
        assert summary["last_duration"] == 0.0
        assert summary["operation_count"] == 0

    def test_record_operation_when_monitoring_inactive(self):
        """测试monitoring inactive时不记录操作"""
        monitor = PerformanceMonitor()
        monitor.record_operation("test_op", 1.0)
        assert monitor._total_operations == 0
        assert monitor._operation_stats == {}

    def test_record_operation_when_monitoring_active(self):
        """测试monitoring active时记录操作"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        monitor.record_operation("test_op", 1.0)
        assert monitor._total_operations == 1
        assert "test_op" in monitor._operation_stats
        assert monitor._operation_stats["test_op"]["count"] == 1
        assert monitor._operation_stats["test_op"]["total_time"] == 1.0

    def test_record_operation_multiple_calls(self):
        """测试多次记录同一操作"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        monitor.record_operation("test_op", 1.0)
        monitor.record_operation("test_op", 2.0)
        monitor.record_operation("test_op", 3.0)
        assert monitor._total_operations == 3
        stats = monitor._operation_stats["test_op"]
        assert stats["count"] == 3
        assert stats["total_time"] == 6.0
        assert stats["avg_time"] == 2.0
        assert stats["min_time"] == 1.0
        assert stats["max_time"] == 3.0

    def test_record_operation_different_operations(self):
        """测试记录不同操作"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        monitor.record_operation("op1", 1.0)
        monitor.record_operation("op2", 2.0)
        assert monitor._total_operations == 2
        assert "op1" in monitor._operation_stats
        assert "op2" in monitor._operation_stats

    def test_clear_metrics(self):
        """测试clear_metrics方法"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        monitor.record_operation("test_op", 1.0)
        monitor.clear_metrics()
        assert monitor._operation_stats == {}
        assert monitor._total_operations == 0
        assert monitor._last_duration == 0.0

    @patch("tree_sitter_analyzer.core.performance.log_info")
    def test_clear_metrics_logs(self, mock_log):
        """测试clear_metrics日志输出"""
        monitor = PerformanceMonitor()
        monitor.clear_metrics()
        mock_log.assert_called_once_with("Performance metrics cleared")


class TestPerformanceContext:
    """PerformanceContext测试类"""

    def test_init(self):
        """测试PerformanceContext初始化"""
        monitor = PerformanceMonitor()
        context = PerformanceContext("test_operation", monitor)
        assert context.operation_name == "test_operation"
        assert context.monitor == monitor
        assert context.start_time == 0.0

    def test_context_manager_enter(self):
        """测试上下文管理器__enter__"""
        monitor = PerformanceMonitor()
        context = PerformanceContext("test_operation", monitor)
        result = context.__enter__()
        assert result is context
        assert context.start_time > 0

    def test_context_manager_exit(self):
        """测试上下文管理器__exit__"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        context = PerformanceContext("test_operation", monitor)
        context.__enter__()
        time.sleep(0.01)  # Small delay
        context.__exit__(None, None, None)
        # 実行時間は0以上
        assert monitor.get_last_duration() >= 0
        assert monitor._total_operations == 1

    @patch("tree_sitter_analyzer.core.performance.log_performance")
    def test_context_manager_exit_logs(self, mock_log):
        """测试上下文管理器__exit__日志输出"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        context = PerformanceContext("test_operation", monitor)
        context.__enter__()
        context.__exit__(None, None, None)
        mock_log.assert_called_once()
        args = mock_log.call_args[0]
        assert args[0] == "test_operation"
        # 実行時間は0以上
        assert args[1] >= 0
        assert args[2] == "Operation completed"

    def test_context_manager_with_exception(self):
        """测试上下文管理器处理异常"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        context = PerformanceContext("test_operation", monitor)
        context.__enter__()
        context.__exit__(ValueError, ValueError("test"), None)
        # 実行時間は0以上
        assert monitor.get_last_duration() >= 0

    def test_context_manager_usage(self):
        """测试实际使用场景"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        with monitor.measure_operation("test_operation"):
            time.sleep(0.01)
        # 実行時間は0以上
        assert monitor.get_last_duration() >= 0
        assert monitor._total_operations == 1
        assert "test_operation" in monitor._operation_stats


class TestPerformanceIntegration:
    """PerformanceMonitor集成测试"""

    def test_full_workflow(self):
        """测试完整工作流程"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()

        # 执行多个操作
        with monitor.measure_operation("operation1"):
            time.sleep(0.01)

        with monitor.measure_operation("operation2"):
            time.sleep(0.02)

        with monitor.measure_operation("operation1"):
            time.sleep(0.015)

        # 验证统计信息
        assert monitor._total_operations == 3
        assert len(monitor._operation_stats) == 2

        stats1 = monitor._operation_stats["operation1"]
        assert stats1["count"] == 2
        assert stats1["avg_time"] > 0

        stats2 = monitor._operation_stats["operation2"]
        assert stats2["count"] == 1

        # 验证摘要
        summary = monitor.get_performance_summary()
        assert summary["total_operations"] == 3
        assert summary["monitoring_active"] is True
        assert summary["operation_count"] == 2

    def test_concurrent_operations(self):
        """测试并发操作"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()

        # 模拟并发操作
        contexts = []
        for i in range(5):
            ctx = monitor.measure_operation(f"op{i}")
            ctx.__enter__()
            contexts.append(ctx)

        time.sleep(0.01)

        for ctx in contexts:
            ctx.__exit__(None, None, None)

        assert monitor._total_operations == 5
        assert len(monitor._operation_stats) == 5

    def test_reset_between_sessions(self):
        """测试会话间重置"""
        monitor = PerformanceMonitor()

        # 第一会话
        monitor.start_monitoring()
        with monitor.measure_operation("session1_op"):
            time.sleep(0.01)
        monitor.stop_monitoring()

        # 重置
        monitor.clear_metrics()

        # 第二会话
        monitor.start_monitoring()
        with monitor.measure_operation("session2_op"):
            time.sleep(0.01)

        assert monitor._total_operations == 1
        assert "session1_op" not in monitor._operation_stats
        assert "session2_op" in monitor._operation_stats
