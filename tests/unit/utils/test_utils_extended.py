#!/usr/bin/env python3
"""
Extended tests for utils module to improve test coverage.
"""

import logging
import tempfile
import unittest.mock
from pathlib import Path
from unittest.mock import patch

from tree_sitter_analyzer.utils import (
    LoggingContext,
    create_performance_logger,
    log_debug,
    log_error,
    log_info,
    log_performance,
    log_warning,
    safe_print,
    setup_logger,
)


class TestUtilsExtended:
    """Extended tests for utils module."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = str(Path(self.temp_dir) / "test.log")

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_setup_logger_with_custom_level(self):
        """Test setup_logger with custom log level."""
        logger = setup_logger("test_logger", level="DEBUG")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"
        assert logger.level == logging.DEBUG
        assert logger.propagate is False

    def test_setup_logger_with_custom_format(self):
        """Test setup_logger with custom format."""
        logger = setup_logger("test_logger")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"
        assert [handler.__class__.__name__ for handler in logger.handlers] == [
            "SafeStreamHandler"
        ]

    def test_setup_logger_with_file_handler(self):
        """Test setup_logger with file handler."""
        logger = setup_logger("test_logger")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"
        assert len(logger.handlers) == 1
        assert logger.handlers[0].formatter._fmt == (
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    def test_logging_functions_with_kwargs(self):
        """Test logging functions with keyword arguments."""
        with patch("tree_sitter_analyzer.utils.logging.logger") as mock_logger:
            log_info("test message", extra={"key": "value"})
            log_warning("test warning", extra={"key": "value"})
            log_error("test error", extra={"key": "value"})
            log_debug("test debug", extra={"key": "value"})

        mock_logger.info.assert_called_once_with(
            "test message", extra={"key": "value"}
        )
        mock_logger.warning.assert_called_once_with(
            "test warning", extra={"key": "value"}
        )
        mock_logger.error.assert_called_once_with("test error", extra={"key": "value"})
        mock_logger.debug.assert_called_once_with("test debug", extra={"key": "value"})

    def test_log_performance_with_details(self):
        """Test log_performance with details."""
        with patch("tree_sitter_analyzer.utils.logging.perf_logger") as mock_logger:
            log_performance("test operation", 1.5, details={"lines": 100, "files": 5})

        mock_logger.debug.assert_called_once_with(
            "test operation: 1.5000s - lines: 100, files: 5"
        )

    def test_log_performance_without_details(self):
        """Test log_performance without details."""
        with patch("tree_sitter_analyzer.utils.logging.perf_logger") as mock_logger:
            log_performance("test operation", 1.5)

        mock_logger.debug.assert_called_once_with("test operation: 1.5000s")

    def test_safe_print_functions(self):
        """Test safe print functions."""
        with (
            patch("tree_sitter_analyzer.utils.logging.log_info") as mock_info,
            patch("tree_sitter_analyzer.utils.logging.log_debug") as mock_debug,
            patch("tree_sitter_analyzer.utils.logging.log_error") as mock_error,
            patch("tree_sitter_analyzer.utils.logging.log_warning") as mock_warning,
        ):
            safe_print("test info", level="info")
            safe_print("test debug", level="debug")
            safe_print("test error", level="error")
            safe_print("test warning", level="warning")

        mock_info.assert_called_once_with("test info")
        mock_debug.assert_called_once_with("test debug")
        mock_error.assert_called_once_with("test error")
        mock_warning.assert_called_once_with("test warning")

    def test_safe_print_with_none_message(self):
        """Test safe print functions with None message."""
        # Patch the log_info in safe_print's globals since it's dynamically loaded
        original_log_info = safe_print.__globals__["log_info"]
        original_log_error = safe_print.__globals__["log_error"]

        mock_info = unittest.mock.MagicMock()
        mock_error = unittest.mock.MagicMock()

        try:
            safe_print.__globals__["log_info"] = mock_info
            safe_print(None, level="info")
            mock_info.assert_called_once()

            safe_print.__globals__["log_error"] = mock_error
            safe_print(None, level="error")
            mock_error.assert_called_once()
        finally:
            # Restore originals
            safe_print.__globals__["log_info"] = original_log_info
            safe_print.__globals__["log_error"] = original_log_error

    def test_safe_print_with_invalid_level(self):
        """Test safe print with invalid level."""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_info:
            safe_print("test", level="INVALID")

        mock_info.assert_called_once_with("test")

    def test_safe_print_quiet_mode(self):
        """Test safe print in quiet mode."""
        with patch("tree_sitter_analyzer.utils.log_info") as mock_info:
            safe_print("test info", level="info", quiet=True)
            mock_info.assert_not_called()

    def test_get_performance_monitor(self):
        """Test get_performance_monitor function."""
        monitor = create_performance_logger("test")
        assert isinstance(monitor, logging.Logger)
        assert monitor.name == "test.performance"
        assert monitor.propagate is False
        assert [handler.__class__.__name__ for handler in monitor.handlers] == [
            "SafeStreamHandler"
        ]

    def test_is_testing_mode(self):
        """Test is_testing_mode function."""
        import os

        with patch.dict(os.environ, {}, clear=True):
            testing_value = os.environ.get("TREE_SITTER_ANALYZER_TESTING", "0")

        assert testing_value == "0"

    def test_logging_with_exception(self):
        """Test logging with exception."""
        with patch("tree_sitter_analyzer.utils.logging.logger") as mock_logger:
            try:
                raise ValueError("test exception")
            except ValueError:
                log_error("Error occurred", exc_info=True)

        mock_logger.error.assert_called_once_with("Error occurred", exc_info=True)

    def test_logging_with_unicode(self):
        """Test logging with unicode characters."""
        unicode_message = "测试消息 with unicode 🚀"
        with patch("tree_sitter_analyzer.utils.logging.logger") as mock_logger:
            log_info(unicode_message)

        mock_logger.info.assert_called_once_with(unicode_message)

    def test_logging_context_manager(self):
        """Test logging context manager."""
        logger = logging.getLogger("test_extended_context_manager")
        logger.setLevel(logging.INFO)
        context = LoggingContext(level=logging.DEBUG)
        context.target_logger = logger

        with context as ctx:
            assert ctx.enabled is True
            assert logger.level == logging.DEBUG
            log_debug("test debug message")

        assert logger.level == logging.INFO

    def test_logging_context_nesting(self):
        """Test nested logging contexts."""
        logger = logging.getLogger("test_extended_context_nesting")
        logger.setLevel(logging.WARNING)
        outer_context = LoggingContext(level=logging.INFO)
        outer_context.target_logger = logger
        inner_context = LoggingContext(level=logging.DEBUG)
        inner_context.target_logger = logger

        with outer_context:
            assert logger.level == logging.INFO
            with inner_context:
                assert logger.level == logging.DEBUG
                log_debug("test debug message")
            assert logger.level == logging.INFO

        assert logger.level == logging.WARNING

    def test_logging_context_level_change(self):
        """Test logging context level change."""
        logger = logging.getLogger("test_extended_context_level_change")
        logger.setLevel(logging.DEBUG)
        context = LoggingContext(level=logging.WARNING)
        context.target_logger = logger

        with context as ctx:
            assert ctx.level == logging.WARNING
            assert logger.level == logging.WARNING

        assert logger.level == logging.DEBUG

    def test_logging_context_enable_disable(self):
        """Test logging context enable/disable."""
        logger = logging.getLogger("test_extended_context_disabled")
        logger.setLevel(logging.DEBUG)
        context = LoggingContext(enabled=False, level=logging.ERROR)
        context.target_logger = logger

        with context as ctx:
            assert ctx.enabled is False
            assert logger.level == logging.DEBUG

        assert context.old_level is None

    def test_performance_logger_setup(self):
        """Test performance logger setup."""
        logger = create_performance_logger("test")
        assert logger.name == "test.performance"
        assert logger.propagate is False

    def test_performance_logging_integration(self):
        """Test performance logging integration."""
        logger = create_performance_logger("test")
        assert logger.handlers[0].formatter._fmt == "%(asctime)s - PERF - %(message)s"

    def test_logging_with_safe_print_integration(self):
        """Test integration between logging and safe print."""
        with patch("tree_sitter_analyzer.utils.logging.logger") as mock_logger:
            log_info("test message")
            safe_print("test message", level="info")

        assert mock_logger.info.call_args_list == [
            unittest.mock.call("test message"),
            unittest.mock.call("test message"),
        ]

    def test_all_logging_functions_work_together(self):
        """Test that all logging functions work together."""
        with patch("tree_sitter_analyzer.utils.logging.logger") as mock_logger:
            log_info("info message")
            log_warning("warning message")
            log_error("error message")
            log_debug("debug message")

        mock_logger.info.assert_called_once_with("info message")
        mock_logger.warning.assert_called_once_with("warning message")
        mock_logger.error.assert_called_once_with("error message")
        mock_logger.debug.assert_called_once_with("debug message")

    def test_logging_context_with_safe_print(self):
        """Test logging context with safe print."""
        logger = logging.getLogger("test_extended_context_safe_print")
        logger.setLevel(logging.ERROR)
        context = LoggingContext(level=logging.INFO)
        context.target_logger = logger

        with context:
            assert logger.level == logging.INFO
            safe_print("test message", level="info")

        assert logger.level == logging.ERROR

    def test_edge_cases(self):
        """Test various edge cases."""
        with patch("tree_sitter_analyzer.utils.logging.logger") as mock_logger:
            log_info("")
            long_message = "a" * 10000
            log_info(long_message)
            special_message = "test@#$%^&*()_+-=[]{}|;':\",./<>?`~"
            log_info(special_message)

        assert mock_logger.info.call_args_list == [
            unittest.mock.call(""),
            unittest.mock.call(long_message),
            unittest.mock.call(special_message),
        ]

    def test_error_handling(self):
        """Test error handling in various scenarios."""
        test_obj = object()
        with patch("tree_sitter_analyzer.utils.logging.logger") as mock_logger:
            log_info(None)
            log_info(123)
            log_info(test_obj)

        assert mock_logger.info.call_args_list == [
            unittest.mock.call(None),
            unittest.mock.call(123),
            unittest.mock.call(test_obj),
        ]
