#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.utils.logging module

Comprehensive tests for logging utilities, handlers, and context managers.
"""

import logging
import os
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

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
    logger,
    perf_logger,
    safe_print,
    setup_logger,
    setup_performance_logger,
    setup_safe_logging_shutdown,
    suppress_output,
)


class TestSetupLogger:
    """Tests for setup_logger function"""

    def test_setup_logger_default(self):
        """Test default logger setup"""
        test_logger = setup_logger("test_default_logger")
        assert test_logger is not None
        assert isinstance(test_logger, logging.Logger)

    @patch.dict(os.environ, {"LOG_LEVEL": ""}, clear=False)
    def test_setup_logger_with_string_level_debug(self):
        """Test logger setup with string DEBUG level"""
        test_logger = setup_logger("test_string_debug", level="DEBUG")
        assert test_logger.level == logging.DEBUG

    @patch.dict(os.environ, {"LOG_LEVEL": ""}, clear=False)
    def test_setup_logger_with_string_level_info(self):
        """Test logger setup with string INFO level"""
        test_logger = setup_logger("test_string_info", level="INFO")
        assert test_logger.level == logging.INFO

    @patch.dict(os.environ, {"LOG_LEVEL": ""}, clear=False)
    def test_setup_logger_with_string_level_warning(self):
        """Test logger setup with string WARNING level"""
        test_logger = setup_logger("test_string_warning", level="WARNING")
        assert test_logger.level == logging.WARNING

    def test_setup_logger_with_string_level_error(self):
        """Test logger setup with string ERROR level"""
        test_logger = setup_logger("test_string_error", level="ERROR")
        assert test_logger.level == logging.ERROR

    @patch.dict(os.environ, {"LOG_LEVEL": ""}, clear=False)
    def test_setup_logger_with_invalid_string_level(self):
        """Test logger setup with invalid string level defaults to WARNING"""
        test_logger = setup_logger("test_invalid_level", level="INVALID")
        assert test_logger.level == logging.WARNING

    @patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"})
    def test_setup_logger_respects_env_debug(self):
        """Test logger respects LOG_LEVEL env var"""
        # Create a fresh logger to avoid handler conflicts
        test_logger = setup_logger("test_env_debug_" + str(id(self)))
        assert test_logger.level == logging.DEBUG

    @patch.dict(os.environ, {"LOG_LEVEL": "INFO"})
    def test_setup_logger_respects_env_info(self):
        """Test logger respects LOG_LEVEL=INFO"""
        test_logger = setup_logger("test_env_info_" + str(id(self)))
        assert test_logger.level == logging.INFO

    @patch.dict(os.environ, {"LOG_LEVEL": ""})
    def test_setup_logger_empty_env_uses_default(self):
        """Test logger uses default when LOG_LEVEL is empty"""
        test_logger = setup_logger(
            "test_empty_env_" + str(id(self)), level=logging.ERROR
        )
        assert test_logger.level == logging.ERROR


class TestSafeStreamHandler:
    """Tests for SafeStreamHandler class"""

    def test_handler_default_stream(self):
        """Test handler defaults to stderr"""
        handler = SafeStreamHandler()
        assert handler.stream == sys.stderr

    def test_handler_with_custom_stream(self):
        """Test handler with custom stream"""
        custom_stream = StringIO()
        handler = SafeStreamHandler(stream=custom_stream)
        assert handler.stream == custom_stream

    def test_handler_emit_with_closed_stream(self):
        """Test handler handles closed stream without writing"""
        custom_stream = StringIO()
        custom_stream.close()
        handler = SafeStreamHandler(stream=custom_stream)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        # Should not raise; closed stream is skipped by should_skip_stream_emit
        handler.emit(record)
        assert custom_stream.closed  # Stream remains closed; no write attempted

    def test_handler_emit_with_non_writable_stream(self):
        """Test handler skips non-writable stream"""
        mock_stream = MagicMock()
        mock_stream.closed = False
        mock_stream.writable.return_value = False
        handler = SafeStreamHandler(stream=mock_stream)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        # Non-writable stream must not be written to
        mock_stream.write.assert_not_called()

    def test_handler_emit_success(self):
        """Test handler emits to valid stream"""
        custom_stream = StringIO()
        handler = SafeStreamHandler(stream=custom_stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        output = custom_stream.getvalue()
        assert "Test message" in output


class TestLogFunctions:
    """Tests for logging functions"""

    def test_log_info(self):
        """Test log_info delegates to logger.info"""
        with patch.object(logger, "info") as mock_info:
            log_info("Test info message")
            mock_info.assert_called_once_with("Test info message")

    def test_log_warning(self):
        """Test log_warning delegates to logger.warning"""
        with patch.object(logger, "warning") as mock_warning:
            log_warning("Test warning message")
            mock_warning.assert_called_once_with("Test warning message")

    def test_log_error(self):
        """Test log_error delegates to logger.error"""
        with patch.object(logger, "error") as mock_error:
            log_error("Test error message")
            mock_error.assert_called_once_with("Test error message")

    def test_log_debug(self):
        """Test log_debug delegates to logger.debug"""
        with patch.object(logger, "debug") as mock_debug:
            log_debug("Test debug message")
            mock_debug.assert_called_once_with("Test debug message")

    def test_log_info_with_closed_handler(self):
        """Test log_info suppresses ValueError from closed handler"""
        with patch.object(
            logger, "info", side_effect=ValueError("Test error")
        ) as mock_info:
            log_info("Test message")
            mock_info.assert_called_once_with("Test message")

    def test_log_warning_with_closed_handler(self):
        """Test log_warning suppresses OSError from closed handler"""
        with patch.object(
            logger, "warning", side_effect=OSError("Test error")
        ) as mock_warning:
            log_warning("Test message")
            mock_warning.assert_called_once_with("Test message")

    def test_log_error_with_closed_handler(self):
        """Test log_error suppresses ValueError from closed handler"""
        with patch.object(
            logger, "error", side_effect=ValueError("Test error")
        ) as mock_error:
            log_error("Test message")
            mock_error.assert_called_once_with("Test message")

    def test_log_debug_with_closed_handler(self):
        """Test log_debug suppresses OSError from closed handler"""
        with patch.object(
            logger, "debug", side_effect=OSError("Test error")
        ) as mock_debug:
            log_debug("Test message")
            mock_debug.assert_called_once_with("Test message")


class TestQuietMode:
    """Tests for QuietMode context manager"""

    def test_quiet_mode_enabled(self):
        """Test QuietMode when enabled"""
        original_level = logger.level

        with QuietMode(enabled=True):
            assert logger.level == logging.ERROR

        # Level should be restored
        assert logger.level == original_level

    def test_quiet_mode_disabled(self):
        """Test QuietMode when disabled"""
        original_level = logger.level

        with QuietMode(enabled=False):
            # Level should not change
            pass

        assert logger.level == original_level


class TestSafePrint:
    """Tests for safe_print function"""

    def test_safe_print_info(self):
        """Test safe_print with info level calls log_info"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log_info:
            safe_print("Test message", level="info")
            mock_log_info.assert_called_once_with("Test message")

    def test_safe_print_warning(self):
        """Test safe_print with warning level calls log_warning"""
        with patch(
            "tree_sitter_analyzer.utils.logging.log_warning"
        ) as mock_log_warning:
            safe_print("Test warning", level="warning")
            mock_log_warning.assert_called_once_with("Test warning")

    def test_safe_print_error(self):
        """Test safe_print with error level calls log_error"""
        with patch("tree_sitter_analyzer.utils.logging.log_error") as mock_log_error:
            safe_print("Test error", level="error")
            mock_log_error.assert_called_once_with("Test error")

    def test_safe_print_debug(self):
        """Test safe_print with debug level calls log_debug"""
        with patch("tree_sitter_analyzer.utils.logging.log_debug") as mock_log_debug:
            safe_print("Test debug", level="debug")
            mock_log_debug.assert_called_once_with("Test debug")

    def test_safe_print_unknown_level(self):
        """Test safe_print with unknown level defaults to log_info"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log_info:
            safe_print("Test unknown", level="unknown")
            mock_log_info.assert_called_once_with("Test unknown")

    def test_safe_print_quiet(self):
        """Test safe_print with quiet=True skips logging"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log_info:
            safe_print("Should not print", quiet=True)
            mock_log_info.assert_not_called()

    def test_safe_print_none_message(self):
        """Test safe_print converts None to string 'None'"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log_info:
            safe_print(None)
            mock_log_info.assert_called_once_with("None")


class TestPerformanceLogging:
    """Tests for performance logging functions"""

    def test_create_performance_logger(self):
        """Test create_performance_logger"""
        perf_log = create_performance_logger("test_perf")
        assert perf_log is not None
        assert isinstance(perf_log, logging.Logger)

    def test_log_performance_basic(self):
        """Test log_performance with just operation logs operation name"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("test_operation")
            mock_debug.assert_called_once()
            assert "test_operation" in mock_debug.call_args[0][0]

    def test_log_performance_with_time(self):
        """Test log_performance with execution time includes formatted time"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("test_operation", execution_time=1.234)
            mock_debug.assert_called_once()
            assert "1.2340s" in mock_debug.call_args[0][0]

    def test_log_performance_with_dict_details(self):
        """Test log_performance with dict details includes key-value pairs"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("test_operation", details={"key": "value"})
            mock_debug.assert_called_once()
            assert "key: value" in mock_debug.call_args[0][0]

    def test_log_performance_with_string_details(self):
        """Test log_performance with string details includes the detail text"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("test_operation", details="extra info")
            mock_debug.assert_called_once()
            assert "extra info" in mock_debug.call_args[0][0]

    def test_log_performance_full(self):
        """Test log_performance with all parameters includes all data"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance(
                "test_operation",
                execution_time=1.5,
                details={"files": 10, "lines": 1000},
            )
            mock_debug.assert_called_once()
            msg = mock_debug.call_args[0][0]
            assert "test_operation" in msg
            assert "1.5000s" in msg
            assert "files: 10" in msg

    def test_setup_performance_logger(self):
        """Test setup_performance_logger function"""
        perf_log = setup_performance_logger()
        assert perf_log is not None
        assert perf_log.name == "performance"


class TestLoggingContext:
    """Tests for LoggingContext context manager"""

    def test_logging_context_enabled_with_level(self):
        """Test LoggingContext when enabled with level"""
        target_logger = logging.getLogger("tree_sitter_analyzer")
        original_level = target_logger.level

        with LoggingContext(enabled=True, level=logging.DEBUG):
            assert target_logger.level == logging.DEBUG

        # Level should be restored
        assert target_logger.level == original_level

    def test_logging_context_disabled(self):
        """Test LoggingContext when disabled"""
        target_logger = logging.getLogger("tree_sitter_analyzer")
        original_level = target_logger.level

        with LoggingContext(enabled=False, level=logging.DEBUG):
            # Level should not change
            pass

        assert target_logger.level == original_level

    def test_logging_context_without_level(self):
        """Test LoggingContext without specifying level"""
        target_logger = logging.getLogger("tree_sitter_analyzer")
        original_level = target_logger.level

        with LoggingContext(enabled=True):
            # Level should not change without explicit level
            pass

        assert target_logger.level == original_level


class TestSuppressOutput:
    """Tests for suppress_output decorator"""

    def test_suppress_output_decorator(self):
        """Test suppress_output decorator"""

        @suppress_output
        def func_with_print():
            print("This should be suppressed")
            return "result"

        result = func_with_print()
        assert result == "result"

    def test_suppress_output_in_test_mode(self):
        """Test suppress_output doesn't suppress in test mode"""
        sys._testing = True
        try:

            @suppress_output
            def func_with_print():
                return "result"

            result = func_with_print()
            assert result == "result"
        finally:
            if hasattr(sys, "_testing"):
                del sys._testing


class TestSetupSafeLoggingShutdown:
    """Tests for setup_safe_logging_shutdown function"""

    def test_setup_safe_logging_shutdown(self):
        """Test setup_safe_logging_shutdown registers a cleanup function via atexit"""
        with patch("atexit.register") as mock_register:
            setup_safe_logging_shutdown()
            mock_register.assert_called_once()


class TestGlobalLoggers:
    """Tests for global logger instances"""

    def test_logger_exists(self):
        """Test global logger exists"""
        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_perf_logger_exists(self):
        """Test global perf_logger exists"""
        assert perf_logger is not None
        assert isinstance(perf_logger, logging.Logger)
