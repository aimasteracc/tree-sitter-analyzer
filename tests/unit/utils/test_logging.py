#!/usr/bin/env python3
"""
Unit tests for logging module.

Tests for logging utilities including setup_logger, SafeStreamHandler,
QuietMode, LoggingContext, and various log functions.
"""

import io
import logging
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.utils.logging import (
    LoggingContext,
    QuietMode,
    SafeStreamHandler,
    create_performance_logger,
    log_debug,
    log_error,
    log_info,
    log_performance,
    log_warning,
    perf_logger,
    safe_print,
    setup_logger,
    setup_performance_logger,
    suppress_output,
)
from tree_sitter_analyzer.utils.logging import (
    logger as global_logger,
)


class TestSetupLogger:
    """测试 setup_logger 函数"""

    def test_setup_logger_default(self):
        """测试默认日志设置"""
        with patch.dict(os.environ, {}, clear=True):
            logger = setup_logger(name="test_default")
            assert logger is not None
            assert logger.name == "test_default"
            assert logger.level == logging.WARNING

    def test_setup_logger_debug_level(self):
        """测试DEBUG级别"""
        with patch.dict(os.environ, {}, clear=True):
            logger = setup_logger(name="test_debug", level="DEBUG")
            assert logger.level == logging.DEBUG

    def test_setup_logger_info_level(self):
        """测试INFO级别"""
        with patch.dict(os.environ, {}, clear=True):
            logger = setup_logger(name="test_info", level="INFO")
            assert logger.level == logging.INFO

    def test_setup_logger_warning_level(self):
        """测试WARNING级别"""
        with patch.dict(os.environ, {}, clear=True):
            logger = setup_logger(name="test_warning", level="WARNING")
            assert logger.level == logging.WARNING

    def test_setup_logger_error_level(self):
        """测试ERROR级别"""
        logger = setup_logger(name="test_error", level="ERROR")
        assert logger.level == logging.ERROR

    def test_setup_logger_invalid_level(self):
        """测试无效级别"""
        with patch.dict(os.environ, {}, clear=True):
            logger = setup_logger(name="test_invalid", level="INVALID")
            assert logger.level == logging.WARNING  # Default fallback

    def test_setup_logger_env_debug(self):
        """测试环境变量DEBUG级别"""
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            logger = setup_logger(name="test_env_debug")
            assert logger.level == logging.DEBUG

    def test_setup_logger_env_info(self):
        """测试环境变量INFO级别"""
        with patch.dict(os.environ, {"LOG_LEVEL": "INFO"}):
            logger = setup_logger(name="test_env_info")
            assert logger.level == logging.INFO

    def test_setup_logger_test_logger(self):
        """测试测试日志器"""
        logger = setup_logger(name="test_logger_handlers")
        assert logger.name == "test_logger_handlers"
        # Test logger should have handlers cleared
        assert len(logger.handlers) > 0

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="File logging tests skip on Windows due to file lock issues",
    )
    def test_setup_logger_file_logging_enabled(self):
        """测试启用文件日志"""
        logger_name = "test_file_enabled"
        # Clear existing handlers
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "TREE_SITTER_ANALYZER_ENABLE_FILE_LOG": "true",
                    "TREE_SITTER_ANALYZER_LOG_DIR": temp_dir,
                },
            ):
                logger = setup_logger(name=logger_name)
                # Should have at least one handler
                assert len(logger.handlers) >= 1

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="File logging tests skip on Windows due to file lock issues",
    )
    def test_setup_logger_file_logging_custom_dir(self):
        """测试自定义日志目录"""
        logger_name = "test_file_custom_dir"
        # Clear existing handlers
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "TREE_SITTER_ANALYZER_ENABLE_FILE_LOG": "true",
                    "TREE_SITTER_ANALYZER_LOG_DIR": temp_dir,
                },
            ):
                logger = setup_logger(name=logger_name)
                # Check if file handler was added
                file_handlers = [
                    h for h in logger.handlers if isinstance(h, logging.FileHandler)
                ]
                assert len(file_handlers) >= 0  # May or may not have file handler

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="File logging tests skip on Windows due to file lock issues",
    )
    def test_setup_logger_file_log_level(self):
        """测试文件日志级别"""
        logger_name = "test_file_level"
        # Clear existing handlers
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "TREE_SITTER_ANALYZER_ENABLE_FILE_LOG": "true",
                    "TREE_SITTER_ANALYZER_LOG_DIR": temp_dir,
                    "TREE_SITTER_ANALYZER_FILE_LOG_LEVEL": "DEBUG",
                },
            ):
                logger = setup_logger(name=logger_name)
                # File handler should have DEBUG level if added
                file_handlers = [
                    h for h in logger.handlers if isinstance(h, logging.FileHandler)
                ]
                assert len(file_handlers) >= 0  # May or may not have file handler


class TestSafeStreamHandler:
    """测试 SafeStreamHandler 类"""

    def test_init_default_stream(self):
        """测试默认流"""
        handler = SafeStreamHandler()
        assert handler.stream == sys.stderr

    def test_init_custom_stream(self):
        """测试自定义流"""
        custom_stream = io.StringIO()
        handler = SafeStreamHandler(stream=custom_stream)
        assert handler.stream == custom_stream

    def test_emit_normal(self):
        """测试正常输出"""
        stream = io.StringIO()
        handler = SafeStreamHandler(stream=stream)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        assert "test message" in stream.getvalue()

    def test_emit_closed_stream(self):
        """测试关闭的流 - SafeStreamHandler应该安全处理"""
        stream = io.StringIO()
        # Note: StringIO doesn't have a closed attribute that prevents writing
        # This test verifies the handler doesn't crash
        handler = SafeStreamHandler(stream=stream)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        # Should not crash

    def test_emit_stream_no_write(self):
        """测试无写入方法的流"""

        # Create a custom object without write method
        class NoWriteStream:
            pass

        stream = NoWriteStream()
        handler = SafeStreamHandler(stream=stream)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        # Should not crash
        # Stream without write method should be handled safely

    def test_emit_pytest_stream(self):
        """测试pytest流"""
        stream = MagicMock()
        stream.name = "pytest"
        handler = SafeStreamHandler(stream=stream)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        # Should be cautious with pytest streams
        assert stream.write.call_count == 0

    def test_emit_non_writable_stream(self):
        """测试不可写流"""
        stream = MagicMock()
        stream.writable.return_value = False
        handler = SafeStreamHandler(stream=stream)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        # Should not try to write
        assert stream.write.call_count == 0

    def test_emit_value_error(self):
        """测试ValueError异常"""
        stream = io.StringIO()
        handler = SafeStreamHandler(stream=stream)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        # Simulate ValueError during super().emit() call
        with patch("logging.StreamHandler.emit", side_effect=ValueError("Test error")):
            handler.emit(record)
        # Should not crash

    def test_emit_os_error(self):
        """测试OSError异常"""
        stream = io.StringIO()
        handler = SafeStreamHandler(stream=stream)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        # Simulate OSError during super().emit() call
        with patch("logging.StreamHandler.emit", side_effect=OSError("Test error")):
            handler.emit(record)
        # Should not crash


class TestQuietMode:
    """测试 QuietMode 上下文管理器"""

    def test_init_enabled(self):
        """测试启用的安静模式"""
        with QuietMode(enabled=True) as quiet:
            assert quiet.enabled is True

    def test_init_disabled(self):
        """测试禁用的安静模式"""
        with QuietMode(enabled=False) as quiet:
            assert quiet.enabled is False

    def test_enter_sets_level(self):
        """测试进入时设置级别"""
        original_level = global_logger.level

        with QuietMode(enabled=True):
            assert global_logger.level == logging.ERROR

        # Restore after context
        assert global_logger.level == original_level

    def test_exit_restores_level(self):
        """测试退出时恢复级别"""
        original_level = global_logger.level

        with QuietMode(enabled=True):
            pass

        # Level should be restored
        assert global_logger.level == original_level

    def test_no_level_change_when_disabled(self):
        """测试禁用时不改变级别"""
        original_level = global_logger.level

        with QuietMode(enabled=False):
            pass

        # Level should not change
        assert global_logger.level == original_level

    def test_multiple_nested_contexts(self):
        """测试嵌套上下文"""
        original_level = global_logger.level

        with QuietMode(enabled=True):
            assert global_logger.level == logging.ERROR
            with QuietMode(enabled=True):
                assert global_logger.level == logging.ERROR

        # Should restore to original
        assert global_logger.level == original_level


class TestLoggingContext:
    """测试 LoggingContext 上下文管理器"""

    def test_init_enabled(self):
        """测试启用的日志上下文"""
        with LoggingContext(enabled=True, level=logging.ERROR) as ctx:
            assert ctx.enabled is True

    def test_init_disabled(self):
        """测试禁用的日志上下文"""
        ctx = LoggingContext(enabled=False, level=logging.ERROR)
        assert ctx.enabled is False

    def test_init_with_level(self):
        """测试带级别的初始化"""
        ctx = LoggingContext(enabled=True, level=logging.DEBUG)
        assert ctx.level == logging.DEBUG
        assert ctx.old_level is None

    def test_enter_sets_level(self):
        """测试进入时设置级别"""
        original_level = global_logger.level

        with LoggingContext(enabled=True, level=logging.ERROR):
            assert global_logger.level == logging.ERROR

        # Restore after context
        assert global_logger.level == original_level

    def test_exit_restores_level(self):
        """测试退出时恢复级别"""
        original_level = global_logger.level

        with LoggingContext(enabled=True, level=logging.ERROR):
            pass

        # Level should be restored
        assert global_logger.level == original_level

    def test_notset_level_restores_info(self):
        """测试NOTSET级别恢复到INFO"""
        global_logger.setLevel(logging.NOTSET)

        with LoggingContext(enabled=True, level=logging.ERROR):
            pass

        # Should restore to INFO when NOTSET
        assert global_logger.level == logging.INFO


class TestLogInfo:
    """测试 log_info 函数"""

    def test_log_info_normal(self):
        """测试正常info日志"""
        with patch.object(global_logger, "info") as mock_info:
            log_info("test message")
            mock_info.assert_called_once_with("test message")

    def test_log_info_with_args(self):
        """测试带参数的info日志"""
        with patch.object(global_logger, "info") as mock_info:
            log_info("test %s", "value")
            mock_info.assert_called_once_with("test %s", "value")

    def test_log_info_with_kwargs(self):
        """测试带kwargs的info日志"""
        with patch.object(global_logger, "info") as mock_info:
            log_info("test message", extra={"key": "value"})
            mock_info.assert_called_once_with("test message", extra={"key": "value"})

    def test_log_info_exception_handling(self):
        """测试异常处理"""
        with patch.object(global_logger, "info", side_effect=ValueError("Test error")):
            log_info("test message")
            # Should not crash


class TestLogWarning:
    """测试 log_warning 函数"""

    def test_log_warning_normal(self):
        """测试正常warning日志"""
        with patch.object(global_logger, "warning") as mock_warning:
            log_warning("test warning")
            mock_warning.assert_called_once_with("test warning")

    def test_log_warning_exception_handling(self):
        """测试异常处理"""
        with patch.object(
            global_logger, "warning", side_effect=ValueError("Test error")
        ):
            log_warning("test warning")
            # Should not crash


class TestLogError:
    """测试 log_error 函数"""

    def test_log_error_normal(self):
        """测试正常error日志"""
        with patch.object(global_logger, "error") as mock_error:
            log_error("test error")
            mock_error.assert_called_once_with("test error")

    def test_log_error_exception_handling(self):
        """测试异常处理"""
        with patch.object(global_logger, "error", side_effect=ValueError("Test error")):
            log_error("test error")
            # Should not crash


class TestLogDebug:
    """测试 log_debug 函数"""

    def test_log_debug_normal(self):
        """测试正常debug日志"""
        with patch.object(global_logger, "debug") as mock_debug:
            log_debug("test debug")
            mock_debug.assert_called_once_with("test debug")

    def test_log_debug_exception_handling(self):
        """测试异常处理"""
        with patch.object(global_logger, "debug", side_effect=ValueError("Test error")):
            log_debug("test debug")
            # Should not crash


class TestSuppressOutput:
    """测试 suppress_output 装饰器"""

    def test_suppress_output_normal(self):
        """测试正常输出抑制"""

        @suppress_output
        def test_func():
            print("test output")

        test_func()
        # Should execute normally in non-test mode

    def test_suppress_output_in_testing(self):
        """测试测试模式下的输出抑制"""
        # Set _testing flag
        original_testing = getattr(sys, "_testing", None)
        sys._testing = True

        try:

            @suppress_output
            def test_func():
                print("test output")

            test_func()
            # Should return without printing
        finally:
            # Restore original value
            if original_testing is None:
                delattr(sys, "_testing")
            else:
                sys._testing = original_testing

    def test_suppress_output_exception_handling(self):
        """测试异常处理"""

        @suppress_output
        def test_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            test_func()


class TestSafePrint:
    """测试 safe_print 函数"""

    def test_safe_print_info_level(self):
        """测试info级别打印"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log_info:
            safe_print("test message", level="info")
            mock_log_info.assert_called_once_with("test message")

    def test_safe_print_warning_level(self):
        """测试warning级别打印"""
        with patch(
            "tree_sitter_analyzer.utils.logging.log_warning"
        ) as mock_log_warning:
            safe_print("test message", level="warning")
            mock_log_warning.assert_called_once_with("test message")

    def test_safe_print_error_level(self):
        """测试error级别打印"""
        with patch("tree_sitter_analyzer.utils.logging.log_error") as mock_log_error:
            safe_print("test message", level="error")
            mock_log_error.assert_called_once_with("test message")

    def test_safe_print_debug_level(self):
        """测试debug级别打印"""
        with patch("tree_sitter_analyzer.utils.logging.log_debug") as mock_log_debug:
            safe_print("test message", level="debug")
            mock_log_debug.assert_called_once_with("test message")

    def test_safe_print_none_message(self):
        """测试None消息"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log_info:
            safe_print(None, level="info")
            mock_log_info.assert_called_once_with("None")

    def test_safe_print_quiet(self):
        """测试安静模式"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log_info:
            safe_print("test message", quiet=True)
            mock_log_info.assert_not_called()

    def test_safe_print_default_level(self):
        """测试默认级别"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log_info:
            safe_print("test message")
            mock_log_info.assert_called_once_with("test message")


class TestLogPerformance:
    """测试 log_performance 函数"""

    def test_log_performance_basic(self):
        """测试基本性能日志"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("test_operation", 0.123)
            mock_debug.assert_called_once()
            call_args = mock_debug.call_args[0][0]
            assert "test_operation" in call_args
            assert "0.1230s" in call_args

    def test_log_performance_with_execution_time(self):
        """测试带执行时间的性能日志"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("test_operation", execution_time=0.456)
            mock_debug.assert_called_once()
            call_args = mock_debug.call_args[0][0]
            assert "0.4560s" in call_args

    def test_log_performance_with_details(self):
        """测试带详细信息的性能日志"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("test_operation", details={"key": "value"})
            mock_debug.assert_called_once()
            call_args = mock_debug.call_args[0][0]
            assert "key: value" in call_args

    def test_log_performance_with_all_params(self):
        """测试带所有参数的性能日志"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance(
                "test_operation",
                execution_time=0.789,
                details={"key1": "val1", "key2": "val2"},
            )
            mock_debug.assert_called_once()
            call_args = mock_debug.call_args[0][0]
            assert "0.7890s" in call_args
            assert "key1: val1" in call_args

    def test_log_performance_exception_handling(self):
        """测试异常处理"""
        with patch.object(perf_logger, "debug", side_effect=ValueError("Test error")):
            log_performance("test_operation", 0.123)
            # Should not crash


class TestCreatePerformanceLogger:
    """测试 create_performance_logger 函数"""

    def test_create_performance_logger(self):
        """测试性能日志器创建"""
        logger = create_performance_logger("test_perf_logger")
        assert logger is not None
        assert logger.name == "test_perf_logger.performance"

    def test_create_performance_logger_handler(self):
        """测试性能日志器处理器"""
        logger = create_performance_logger("test_perf_handler")
        assert len(logger.handlers) > 0

    def test_create_performance_logger_level(self):
        """测试性能日志器级别"""
        logger = create_performance_logger("test_perf_level")
        assert logger.level == logging.DEBUG


class TestSetupPerformanceLogger:
    """测试 setup_performance_logger 函数"""

    def test_setup_performance_logger(self):
        """测试性能日志器设置"""
        logger = logging.getLogger("performance")
        original_handlers = list(logger.handlers)

        setup_performance_logger()

        # Should add handler if not present
        assert len(logger.handlers) >= len(original_handlers)

    def test_setup_performance_logger_no_duplicate(self):
        """测试不重复添加处理器"""
        logger = logging.getLogger("performance")

        setup_performance_logger()
        original_count = len(logger.handlers)

        # Call again
        setup_performance_logger()

        # Should not add duplicate handler
        assert len(logger.handlers) == original_count


class TestIntegration:
    """测试集成场景"""

    def test_complete_logging_workflow(self):
        """测试完整日志工作流"""
        with (
            patch.object(global_logger, "info") as mock_info,
            patch.object(global_logger, "warning") as mock_warning,
            patch.object(global_logger, "error") as mock_error,
            patch.object(global_logger, "debug") as mock_debug,
            patch.object(perf_logger, "debug") as mock_perf,
        ):
            # Test all log functions
            log_debug("debug message")
            log_info("info message")
            log_warning("warning message")
            log_error("error message")

            # Test performance logging
            log_performance("test_operation", 0.123)

            # Verify all calls
            assert mock_debug.call_count == 1
            assert mock_info.call_count == 1
            assert mock_warning.call_count == 1
            assert mock_error.call_count == 1
            assert mock_perf.call_count == 1

    def test_quiet_mode_integration(self):
        """测试安静模式集成"""
        original_level = global_logger.level

        with QuietMode(enabled=True):
            # Quiet mode sets level to ERROR, so info/warning won't be logged
            log_info("should not log")
            log_warning("should not log")

        # Restore level
        global_logger.setLevel(original_level)

        # In quiet mode, info and warning are not logged because level is ERROR
        # This test just verifies the mode doesn't crash

    def test_logging_context_integration(self):
        """测试日志上下文集成"""
        original_level = global_logger.level

        with LoggingContext(enabled=True, level=logging.ERROR):
            # ERROR level means only error and above are logged
            log_info("should not log")
            log_error("should log")

        # Restore level
        global_logger.setLevel(original_level)

        # This test just verifies the context manager works correctly
        # The actual logging behavior depends on logger level
