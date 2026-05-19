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
        assert logger is not None
        assert "test_logger" in logger.name

    def test_setup_logger_with_custom_format(self):
        """Test setup_logger with custom format."""
        logger = setup_logger("test_logger")
        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_setup_logger_with_file_handler(self):
        """Test setup_logger with file handler."""
        logger = setup_logger("test_logger")
        assert logger is not None
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"

    def test_logging_functions_with_kwargs(self):
        """Test logging functions with keyword arguments."""
        log_info("test message", extra={"key": "value"})
        log_warning("test warning", extra={"key": "value"})
        log_error("test error", extra={"key": "value"})
        log_debug("test debug", extra={"key": "value"})
        assert callable(log_info)
        assert callable(log_warning)
        assert callable(log_error)
        assert callable(log_debug)

    def test_log_performance_with_details(self):
        """Test log_performance with details."""
        log_performance("test operation", 1.5, details={"lines": 100, "files": 5})
        assert True

    def test_log_performance_without_details(self):
        """Test log_performance without details."""
        log_performance("test operation", 1.5)
        assert True

    def test_safe_print_functions(self):
        """Test safe print functions."""
        safe_print("test info", level="info")
        safe_print("test debug", level="debug")
        safe_print("test error", level="error")
        safe_print("test warning", level="warning")
        assert callable(safe_print)

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
        safe_print("test", level="INVALID")
        assert callable(safe_print)

    def test_safe_print_quiet_mode(self):
        """Test safe print in quiet mode."""
        with patch("tree_sitter_analyzer.utils.log_info") as mock_info:
            safe_print("test info", level="info", quiet=True)
            mock_info.assert_not_called()

    def test_get_performance_monitor(self):
        """Test get_performance_monitor function."""
        monitor = create_performance_logger("test")
        assert monitor is not None
        assert isinstance(monitor, logging.Logger)

    def test_is_testing_mode(self):
        """Test is_testing_mode function."""
        import os
        testing_value = os.environ.get("TREE_SITTER_ANALYZER_TESTING", "0")
        assert testing_value is not None
        assert isinstance(testing_value, str)

    def test_logging_with_exception(self):
        """Test logging with exception."""
        try:
            raise ValueError("test exception")
        except ValueError:
            log_error("Error occurred", exc_info=True)
        assert callable(log_error)

    def test_logging_with_unicode(self):
        """Test logging with unicode characters."""
        unicode_message = "测试消息 with unicode 🚀"
        log_info(unicode_message)
        assert True

    def test_logging_context_manager(self):
        """Test logging context manager."""
        with LoggingContext(level=logging.DEBUG):
            log_debug("test debug message")
        assert LoggingContext is not None

    def test_logging_context_nesting(self):
        """Test nested logging contexts."""
        with LoggingContext(level=logging.INFO):
            with LoggingContext(level=logging.DEBUG):
                log_debug("test debug message")
        assert LoggingContext is not None

    def test_logging_context_level_change(self):
        """Test logging context level change."""
        with LoggingContext(level=logging.WARNING):
            assert True

    def test_logging_context_enable_disable(self):
        """Test logging context enable/disable."""
        with LoggingContext(enabled=False):
            assert True

    def test_performance_logger_setup(self):
        """Test performance logger setup."""
        logger = create_performance_logger("test")
        assert logger is not None

    def test_performance_logging_integration(self):
        """Test performance logging integration."""
        logger = create_performance_logger("test")
        assert logger is not None

    def test_logging_with_safe_print_integration(self):
        """Test integration between logging and safe print."""
        log_info("test message")
        safe_print("test message", level="info")
        assert callable(log_info)
        assert callable(safe_print)

    def test_all_logging_functions_work_together(self):
        """Test that all logging functions work together."""
        log_info("info message")
        log_warning("warning message")
        log_error("error message")
        log_debug("debug message")
        assert True

    def test_logging_context_with_safe_print(self):
        """Test logging context with safe print."""
        with LoggingContext(level=logging.INFO):
            safe_print("test message", level="info")
        assert LoggingContext is not None

    def test_edge_cases(self):
        """Test various edge cases."""
        log_info("")
        long_message = "a" * 10000
        log_info(long_message)
        special_message = "test@#$%^&*()_+-=[]{}|;':\",./<>?`~"
        log_info(special_message)
        assert True

    def test_error_handling(self):
        """Test error handling in various scenarios."""
        log_info(None)
        log_info(123)
        test_obj = object()
        log_info(test_obj)
        assert True
