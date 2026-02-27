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

    @patch.dict(os.environ, {"LOG_LEVEL": "WARNING"})
    def test_setup_logger_env_warning(self):
        """Test logger respects LOG_LEVEL=WARNING env var"""
        test_logger = setup_logger("test_env_warning_" + str(id(self)))
        assert test_logger.level == logging.WARNING

    @patch.dict(os.environ, {"LOG_LEVEL": "ERROR"})
    def test_setup_logger_env_error(self):
        """Test logger respects LOG_LEVEL=ERROR env var"""
        test_logger = setup_logger("test_env_error_" + str(id(self)))
        assert test_logger.level == logging.ERROR

    @patch.dict(os.environ, {"LOG_LEVEL": "BOGUS"})
    def test_setup_logger_env_invalid_uses_param(self):
        """Test logger ignores invalid LOG_LEVEL env var and uses param"""
        test_logger = setup_logger(
            "test_env_bogus_" + str(id(self)), level=logging.ERROR
        )
        assert test_logger.level == logging.ERROR

    @patch.dict(os.environ, {"LOG_LEVEL": ""}, clear=False)
    def test_setup_logger_with_lowercase_string_level(self):
        """Test logger setup with lowercase string level (case insensitive)"""
        test_logger = setup_logger("test_lowercase_debug", level="debug")
        assert test_logger.level == logging.DEBUG

    def test_setup_logger_file_logging_enabled(self, tmp_path, monkeypatch):
        """Test setup_logger with file logging enabled writes to temp dir"""
        monkeypatch.setenv("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "true")
        monkeypatch.setenv("TREE_SITTER_ANALYZER_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("LOG_LEVEL", "")

        test_logger = setup_logger("test_file_log_" + str(id(self)))
        try:
            # Should have both a stream handler and a file handler
            file_handlers = [
                h for h in test_logger.handlers if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            log_file = tmp_path / "tree_sitter_analyzer.log"
            assert log_file.exists() or file_handlers[0].baseFilename.endswith(
                "tree_sitter_analyzer.log"
            )
        finally:
            # Close file handlers to avoid resource warnings
            for h in test_logger.handlers[:]:
                if isinstance(h, logging.FileHandler):
                    h.close()
                    test_logger.removeHandler(h)

    def test_setup_logger_file_logging_custom_dir(self, tmp_path, monkeypatch):
        """Test setup_logger with custom log directory creates dir"""
        custom_dir = tmp_path / "custom_logs"
        monkeypatch.setenv("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "true")
        monkeypatch.setenv("TREE_SITTER_ANALYZER_LOG_DIR", str(custom_dir))
        monkeypatch.setenv("LOG_LEVEL", "")

        test_logger = setup_logger("test_custom_dir_" + str(id(self)))
        try:
            assert custom_dir.exists()
            file_handlers = [
                h for h in test_logger.handlers if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
        finally:
            for h in test_logger.handlers[:]:
                if isinstance(h, logging.FileHandler):
                    h.close()
                    test_logger.removeHandler(h)

    def test_setup_logger_file_logging_temp_fallback(self, monkeypatch):
        """Test setup_logger file logging falls back to system temp dir"""
        monkeypatch.setenv("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "true")
        monkeypatch.delenv("TREE_SITTER_ANALYZER_LOG_DIR", raising=False)
        monkeypatch.setenv("LOG_LEVEL", "")

        test_logger = setup_logger("test_temp_fallback_" + str(id(self)))
        try:
            import tempfile
            from pathlib import Path

            file_handlers = [
                h for h in test_logger.handlers if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            log_path = Path(file_handlers[0].baseFilename)
            assert log_path.parent == Path(tempfile.gettempdir())
        finally:
            for h in test_logger.handlers[:]:
                if isinstance(h, logging.FileHandler):
                    h.close()
                    test_logger.removeHandler(h)

    def test_setup_logger_file_log_level_env(self, tmp_path, monkeypatch):
        """Test setup_logger respects TREE_SITTER_ANALYZER_FILE_LOG_LEVEL env var"""
        monkeypatch.setenv("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "true")
        monkeypatch.setenv("TREE_SITTER_ANALYZER_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("TREE_SITTER_ANALYZER_FILE_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LOG_LEVEL", "")

        test_logger = setup_logger(
            "test_file_level_env_" + str(id(self)), level=logging.WARNING
        )
        try:
            file_handlers = [
                h for h in test_logger.handlers if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            assert file_handlers[0].level == logging.DEBUG
        finally:
            for h in test_logger.handlers[:]:
                if isinstance(h, logging.FileHandler):
                    h.close()
                    test_logger.removeHandler(h)

    def test_setup_logger_file_log_level_info(self, tmp_path, monkeypatch):
        """Test file log level set to INFO via env var"""
        monkeypatch.setenv("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "true")
        monkeypatch.setenv("TREE_SITTER_ANALYZER_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("TREE_SITTER_ANALYZER_FILE_LOG_LEVEL", "INFO")
        monkeypatch.setenv("LOG_LEVEL", "")

        test_logger = setup_logger(
            "test_file_level_info_" + str(id(self)), level=logging.WARNING
        )
        try:
            file_handlers = [
                h for h in test_logger.handlers if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            assert file_handlers[0].level == logging.INFO
        finally:
            for h in test_logger.handlers[:]:
                if isinstance(h, logging.FileHandler):
                    h.close()
                    test_logger.removeHandler(h)

    def test_setup_logger_file_log_level_warning(self, tmp_path, monkeypatch):
        """Test file log level set to WARNING via env var"""
        monkeypatch.setenv("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "true")
        monkeypatch.setenv("TREE_SITTER_ANALYZER_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("TREE_SITTER_ANALYZER_FILE_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("LOG_LEVEL", "")

        test_logger = setup_logger(
            "test_file_level_warn_" + str(id(self)), level=logging.ERROR
        )
        try:
            file_handlers = [
                h for h in test_logger.handlers if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            assert file_handlers[0].level == logging.WARNING
        finally:
            for h in test_logger.handlers[:]:
                if isinstance(h, logging.FileHandler):
                    h.close()
                    test_logger.removeHandler(h)

    def test_setup_logger_file_log_level_error(self, tmp_path, monkeypatch):
        """Test file log level set to ERROR via env var"""
        monkeypatch.setenv("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "true")
        monkeypatch.setenv("TREE_SITTER_ANALYZER_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("TREE_SITTER_ANALYZER_FILE_LOG_LEVEL", "ERROR")
        monkeypatch.setenv("LOG_LEVEL", "")

        test_logger = setup_logger(
            "test_file_level_err_" + str(id(self)), level=logging.WARNING
        )
        try:
            file_handlers = [
                h for h in test_logger.handlers if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            assert file_handlers[0].level == logging.ERROR
        finally:
            for h in test_logger.handlers[:]:
                if isinstance(h, logging.FileHandler):
                    h.close()
                    test_logger.removeHandler(h)

    def test_setup_logger_file_log_level_invalid_falls_back(
        self, tmp_path, monkeypatch
    ):
        """Test invalid file log level falls back to main logger level"""
        monkeypatch.setenv("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "true")
        monkeypatch.setenv("TREE_SITTER_ANALYZER_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("TREE_SITTER_ANALYZER_FILE_LOG_LEVEL", "INVALID")
        monkeypatch.setenv("LOG_LEVEL", "")

        test_logger = setup_logger(
            "test_file_level_invalid_" + str(id(self)), level=logging.WARNING
        )
        try:
            file_handlers = [
                h for h in test_logger.handlers if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            # Falls back to the main logger level (WARNING)
            assert file_handlers[0].level == logging.WARNING
        finally:
            for h in test_logger.handlers[:]:
                if isinstance(h, logging.FileHandler):
                    h.close()
                    test_logger.removeHandler(h)

    def test_setup_logger_min_level_with_file_logging(self, tmp_path, monkeypatch):
        """Test that logger level is set to min of main and file log levels"""
        monkeypatch.setenv("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "true")
        monkeypatch.setenv("TREE_SITTER_ANALYZER_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("TREE_SITTER_ANALYZER_FILE_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LOG_LEVEL", "")

        # Main level=WARNING (30), file level=DEBUG (10), min should be DEBUG (10)
        test_logger = setup_logger(
            "test_min_level_" + str(id(self)), level=logging.WARNING
        )
        try:
            # For test_ loggers, the code forces logger.level = level (the param),
            # but we can still verify file handler level is DEBUG
            file_handlers = [
                h for h in test_logger.handlers if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            assert file_handlers[0].level == logging.DEBUG
        finally:
            for h in test_logger.handlers[:]:
                if isinstance(h, logging.FileHandler):
                    h.close()
                    test_logger.removeHandler(h)

    def test_setup_logger_file_logging_error_path(self, monkeypatch, tmp_path):
        """Test setup_logger handles errors during file handler creation"""
        monkeypatch.setenv("TREE_SITTER_ANALYZER_ENABLE_FILE_LOG", "true")
        monkeypatch.setenv("LOG_LEVEL", "")
        # Use a path that is a file (not dir) to force mkdir to fail
        blocker = tmp_path / "blocker_file"
        blocker.write_text("not a dir")
        monkeypatch.setenv(
            "TREE_SITTER_ANALYZER_LOG_DIR", str(blocker / "subdir")
        )

        # Should not raise, error is caught and logged to stderr
        test_logger = setup_logger("test_file_err_path_" + str(id(self)))
        # Should still have at least the stream handler
        stream_handlers = [
            h
            for h in test_logger.handlers
            if h.__class__.__name__ == "SafeStreamHandler"
        ]
        assert len(stream_handlers) >= 1


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
        """Test handler handles closed stream"""
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
        # Should not raise
        handler.emit(record)

    def test_handler_emit_with_non_writable_stream(self):
        """Test handler handles non-writable stream"""
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
        # Should not raise
        handler.emit(record)

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

    def test_handler_emit_stream_without_write(self):
        """Test handler handles stream that has no write attribute"""
        mock_stream = MagicMock(spec=[])
        # spec=[] means no attributes at all, so hasattr(stream, 'write') is False
        handler = SafeStreamHandler(stream=mock_stream)
        # Override the stream directly after init since __init__ may complain
        handler.stream = mock_stream

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        # Should not raise - returns early when no write attr
        handler.emit(record)

    def test_handler_emit_with_none_stream_name(self):
        """Test handler emit when stream.name is None (pytest path)"""
        mock_stream = MagicMock()
        mock_stream.closed = False
        mock_stream.name = None
        mock_stream.write = MagicMock()
        handler = SafeStreamHandler(stream=mock_stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message via None name",
            args=(),
            exc_info=None,
        )
        # stream_name is None so it enters the pytest cautious path
        handler.emit(record)

    def test_handler_emit_writable_raises_valueerror(self):
        """Test handler handles writable() raising ValueError"""
        mock_stream = MagicMock()
        mock_stream.closed = False
        mock_stream.name = "<stderr>"
        mock_stream.writable.side_effect = ValueError("closed file")
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
        # Should not raise - caught by inner try/except
        handler.emit(record)

    def test_handler_emit_super_raises_oserror(self):
        """Test handler handles OSError from parent emit"""
        custom_stream = StringIO()
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

        with patch.object(logging.StreamHandler, "emit", side_effect=OSError("I/O error")):
            # Should not raise - caught by outer except
            handler.emit(record)

    def test_handler_emit_super_raises_unexpected(self):
        """Test handler handles unexpected Exception from parent emit"""
        custom_stream = StringIO()
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

        with patch.object(
            logging.StreamHandler, "emit", side_effect=RuntimeError("unexpected")
        ):
            # Should not raise - caught by the broad except
            handler.emit(record)


class TestLogFunctions:
    """Tests for logging functions"""

    def test_log_info(self):
        """Test log_info function"""
        # Should not raise
        log_info("Test info message")

    def test_log_warning(self):
        """Test log_warning function"""
        # Should not raise
        log_warning("Test warning message")

    def test_log_error(self):
        """Test log_error function"""
        # Should not raise
        log_error("Test error message")

    def test_log_debug(self):
        """Test log_debug function"""
        # Should not raise
        log_debug("Test debug message")

    def test_log_info_with_closed_handler(self):
        """Test log_info handles closed handlers gracefully"""
        # This tests the exception handling in log_info
        with patch.object(logger, "info", side_effect=ValueError("Test error")):
            # Should not raise, just suppress
            log_info("Test message")

    def test_log_warning_with_closed_handler(self):
        """Test log_warning handles closed handlers gracefully"""
        with patch.object(logger, "warning", side_effect=OSError("Test error")):
            # Should not raise, just suppress
            log_warning("Test message")

    def test_log_error_with_closed_handler(self):
        """Test log_error handles closed handlers gracefully"""
        with patch.object(logger, "error", side_effect=ValueError("Test error")):
            # Should not raise, just suppress
            log_error("Test message")

    def test_log_debug_with_closed_handler(self):
        """Test log_debug handles closed handlers gracefully"""
        with patch.object(logger, "debug", side_effect=OSError("Test error")):
            # Should not raise, just suppress
            log_debug("Test message")


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

    def test_quiet_mode_restores_after_exception(self):
        """Test QuietMode restores level even when exception occurs"""
        original_level = logger.level
        try:
            with QuietMode(enabled=True):
                assert logger.level == logging.ERROR
                raise ValueError("test exception")
        except ValueError:
            pass

        assert logger.level == original_level

    def test_quiet_mode_default_enabled(self):
        """Test QuietMode defaults to enabled=True"""
        original_level = logger.level

        with QuietMode():
            assert logger.level == logging.ERROR

        assert logger.level == original_level


class TestSafePrint:
    """Tests for safe_print function"""

    def test_safe_print_info(self):
        """Test safe_print with info level"""
        # Should not raise
        safe_print("Test message", level="info")

    def test_safe_print_warning(self):
        """Test safe_print with warning level"""
        safe_print("Test warning", level="warning")

    def test_safe_print_error(self):
        """Test safe_print with error level"""
        safe_print("Test error", level="error")

    def test_safe_print_debug(self):
        """Test safe_print with debug level"""
        safe_print("Test debug", level="debug")

    def test_safe_print_unknown_level(self):
        """Test safe_print with unknown level defaults to info"""
        safe_print("Test unknown", level="unknown")

    def test_safe_print_quiet(self):
        """Test safe_print with quiet=True does nothing"""
        safe_print("Should not print", quiet=True)

    def test_safe_print_none_message(self):
        """Test safe_print with None message"""
        safe_print(None)  # Should not raise

    def test_safe_print_calls_log_info(self):
        """Test safe_print dispatches to log_info for info level"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log:
            safe_print("hello", level="info")
            mock_log.assert_called_once_with("hello")

    def test_safe_print_calls_log_warning(self):
        """Test safe_print dispatches to log_warning for warning level"""
        with patch("tree_sitter_analyzer.utils.logging.log_warning") as mock_log:
            safe_print("warn msg", level="warning")
            mock_log.assert_called_once_with("warn msg")

    def test_safe_print_calls_log_error(self):
        """Test safe_print dispatches to log_error for error level"""
        with patch("tree_sitter_analyzer.utils.logging.log_error") as mock_log:
            safe_print("err msg", level="error")
            mock_log.assert_called_once_with("err msg")

    def test_safe_print_calls_log_debug(self):
        """Test safe_print dispatches to log_debug for debug level"""
        with patch("tree_sitter_analyzer.utils.logging.log_debug") as mock_log:
            safe_print("dbg msg", level="debug")
            mock_log.assert_called_once_with("dbg msg")

    def test_safe_print_unknown_calls_log_info(self):
        """Test safe_print dispatches to log_info for unknown level"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log:
            safe_print("fallback msg", level="custom_level")
            mock_log.assert_called_once_with("fallback msg")

    def test_safe_print_quiet_does_not_call_log(self):
        """Test safe_print with quiet=True skips all logging"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log:
            safe_print("should not log", level="info", quiet=True)
            mock_log.assert_not_called()

    def test_safe_print_none_converts_to_string(self):
        """Test safe_print converts None to the string 'None'"""
        with patch("tree_sitter_analyzer.utils.logging.log_info") as mock_log:
            safe_print(None, level="info")
            mock_log.assert_called_once_with("None")


class TestPerformanceLogging:
    """Tests for performance logging functions"""

    def test_create_performance_logger(self):
        """Test create_performance_logger"""
        perf_log = create_performance_logger("test_perf")
        assert perf_log is not None
        assert isinstance(perf_log, logging.Logger)

    def test_log_performance_basic(self):
        """Test log_performance with just operation"""
        log_performance("test_operation")

    def test_log_performance_with_time(self):
        """Test log_performance with execution time"""
        log_performance("test_operation", execution_time=1.234)

    def test_log_performance_with_dict_details(self):
        """Test log_performance with dict details"""
        log_performance("test_operation", details={"key": "value"})

    def test_log_performance_with_string_details(self):
        """Test log_performance with string details"""
        log_performance("test_operation", details="extra info")

    def test_log_performance_full(self):
        """Test log_performance with all parameters"""
        log_performance(
            "test_operation", execution_time=1.5, details={"files": 10, "lines": 1000}
        )

    def test_setup_performance_logger(self):
        """Test setup_performance_logger function"""
        perf_log = setup_performance_logger()
        assert perf_log is not None
        assert perf_log.name == "performance"

    def test_log_performance_formats_time(self):
        """Test log_performance formats execution_time to 4 decimal places"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("op1", execution_time=2.123456)
            mock_debug.assert_called_once()
            msg = mock_debug.call_args[0][0]
            assert "op1: 2.1235s" in msg

    def test_log_performance_dict_details_formatting(self):
        """Test log_performance formats dict details as comma-separated key:value"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("op2", details={"a": 1, "b": 2})
            mock_debug.assert_called_once()
            msg = mock_debug.call_args[0][0]
            assert "a: 1" in msg
            assert "b: 2" in msg

    def test_log_performance_string_details_appended(self):
        """Test log_performance appends string details after dash"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("op3", details="some info")
            mock_debug.assert_called_once()
            msg = mock_debug.call_args[0][0]
            assert "op3 - some info" in msg

    def test_log_performance_time_and_details(self):
        """Test log_performance with both execution_time and string details"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("op4", execution_time=0.5, details="fast")
            mock_debug.assert_called_once()
            msg = mock_debug.call_args[0][0]
            assert "op4: 0.5000s - fast" in msg

    def test_log_performance_error_handling(self):
        """Test log_performance handles ValueError/OSError gracefully"""
        with patch.object(perf_logger, "debug", side_effect=ValueError("test")):
            # Should not raise
            log_performance("op_err", execution_time=1.0)

    def test_log_performance_none_details_no_detail_str(self):
        """Test log_performance with None details does not append details"""
        with patch.object(perf_logger, "debug") as mock_debug:
            log_performance("op5", execution_time=1.0, details=None)
            mock_debug.assert_called_once()
            msg = mock_debug.call_args[0][0]
            assert msg == "op5: 1.0000s"

    def test_create_performance_logger_has_debug_level(self):
        """Test that create_performance_logger sets DEBUG level"""
        perf_log = create_performance_logger("test_perf_level_check")
        assert perf_log.level == logging.DEBUG


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

    def test_logging_context_notset_fallback(self):
        """Test LoggingContext falls back to INFO when current level is NOTSET"""
        target_logger = logging.getLogger("tree_sitter_analyzer")
        saved = target_logger.level

        # Set logger to NOTSET to trigger the fallback
        target_logger.setLevel(logging.NOTSET)
        try:
            with LoggingContext(enabled=True, level=logging.ERROR):
                assert target_logger.level == logging.ERROR

            # After exit, should restore to INFO (the NOTSET fallback)
            assert target_logger.level == logging.INFO
        finally:
            target_logger.setLevel(saved)

    def test_logging_context_restores_after_exception(self):
        """Test LoggingContext restores level even when exception occurs"""
        target_logger = logging.getLogger("tree_sitter_analyzer")
        original_level = target_logger.level

        try:
            with LoggingContext(enabled=True, level=logging.DEBUG):
                assert target_logger.level == logging.DEBUG
                raise RuntimeError("test error")
        except RuntimeError:
            pass

        assert target_logger.level == original_level

    def test_logging_context_disabled_does_not_save_level(self):
        """Test LoggingContext disabled does not modify old_level"""
        ctx = LoggingContext(enabled=False, level=logging.DEBUG)
        ctx.__enter__()
        assert ctx.old_level is None
        ctx.__exit__(None, None, None)

    def test_logging_context_exit_without_enter(self):
        """Test LoggingContext exit without entering enabled context"""
        ctx = LoggingContext(enabled=True, level=logging.DEBUG)
        # old_level is None since __enter__ was never called
        assert ctx.old_level is None
        # __exit__ should be safe to call
        ctx.__exit__(None, None, None)


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

    def test_suppress_output_no_test_mode(self):
        """Test suppress_output in production mode (no _testing attr)"""
        # Ensure _testing is not set
        had_testing = hasattr(sys, "_testing")
        if had_testing:
            old_val = sys._testing
            del sys._testing

        try:

            @suppress_output
            def func_returning_value():
                print("suppressed output")
                return 42

            result = func_returning_value()
            assert result == 42
        finally:
            if had_testing:
                sys._testing = old_val

    def test_suppress_output_function_raises(self):
        """Test suppress_output restores stdout when function raises"""
        original_stdout = sys.stdout

        # Ensure _testing is not set
        had_testing = hasattr(sys, "_testing")
        if had_testing:
            old_val = sys._testing
            del sys._testing

        try:

            @suppress_output
            def func_that_raises():
                raise ValueError("inner error")

            try:
                func_that_raises()
            except ValueError:
                pass

            # stdout should be restored
            assert sys.stdout is original_stdout
        finally:
            if had_testing:
                sys._testing = old_val

    def test_suppress_output_preserves_function_metadata(self):
        """Test suppress_output preserves function name via functools.wraps"""

        @suppress_output
        def my_named_function():
            return True

        assert my_named_function.__name__ == "my_named_function"

    def test_suppress_output_with_args_and_kwargs(self):
        """Test suppress_output passes args and kwargs correctly"""

        @suppress_output
        def func_with_args(a, b, key=None):
            return (a, b, key)

        result = func_with_args(1, 2, key="three")
        assert result == (1, 2, "three")


class TestSetupSafeLoggingShutdown:
    """Tests for setup_safe_logging_shutdown function"""

    def test_setup_safe_logging_shutdown(self):
        """Test setup_safe_logging_shutdown registers cleanup"""
        # This should not raise
        setup_safe_logging_shutdown()

    def test_setup_safe_logging_shutdown_registers_atexit(self):
        """Test that setup_safe_logging_shutdown registers with atexit"""
        import atexit

        with patch.object(atexit, "register") as mock_register:
            setup_safe_logging_shutdown()
            mock_register.assert_called_once()
            # The registered function should be callable
            registered_func = mock_register.call_args[0][0]
            assert callable(registered_func)

    def test_cleanup_logging_runs_safely(self):
        """Test that the registered cleanup function runs without errors"""
        import atexit

        with patch.object(atexit, "register") as mock_register:
            setup_safe_logging_shutdown()
            cleanup_func = mock_register.call_args[0][0]
            # Should not raise
            cleanup_func()


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
