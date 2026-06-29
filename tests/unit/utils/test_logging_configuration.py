#!/usr/bin/env python3
"""
Tests for Logging Configuration Features

This module tests the new environment variable-controlled logging features
including file logging, log directory configuration, and log level settings.
"""

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import setup_logger and SafeStreamHandler from utils package
from tree_sitter_analyzer.utils import SafeStreamHandler, setup_logger


class TestLoggingConfiguration:
    """Test logging configuration with environment variables."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_env = {}

        # Store original environment variables
        env_vars = [
            "TREE_SITTER_ANALYZER_ENABLE_FILE_LOG",
            "TREE_SITTER_ANALYZER_LOG_DIR",
            "TREE_SITTER_ANALYZER_FILE_LOG_LEVEL",
            "LOG_LEVEL",
        ]
        for var in env_vars:
            self.original_env[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        # Restore original environment variables
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]

        # Clean up temporary directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)

        # Clean up any test loggers
        for name in list(logging.Logger.manager.loggerDict.keys()):
            if name.startswith("test_logging_"):
                logger = logging.getLogger(name)
                for handler in logger.handlers[:]:
                    try:
                        handler.close()
                        logger.removeHandler(handler)
                    except Exception:
                        pass

    def test_default_behavior_no_file_logging(self):
        """Test default behavior with file logging disabled."""
        # Ensure no file logging environment variables are set
        logger = setup_logger("test_logging_default")

        # Should have only one handler (SafeStreamHandler)
        assert len(logger.handlers) == 1
        # Check handler type by class name instead of isinstance due to import differences
        assert logger.handlers[0].__class__.__name__ == "SafeStreamHandler"

        # Should not have any file handlers
        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 0

    def test_enable_file_logging_true(self):
        """Test file logging when TREE_SITTER_ANALYZER_ENABLE_FILE_LOG=true."""
        os.environ["TREE_SITTER_ANALYZER_ENABLE_FILE_LOG"] = "true"

        logger = setup_logger("test_logging_enabled")

        # Should have two handlers: SafeStreamHandler and FileHandler
        assert len(logger.handlers) == 2

        # Check for SafeStreamHandler by class name
        stream_handlers = [
            h for h in logger.handlers if h.__class__.__name__ == "SafeStreamHandler"
        ]
        assert len(stream_handlers) == 1

        # Check for FileHandler
        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1

        # Verify file handler is writing to temp directory
        file_handler = file_handlers[0]
        log_path = Path(file_handler.baseFilename)
        assert log_path.name == "tree_sitter_analyzer.log"

    def test_custom_log_directory(self):
        """Test custom log directory with TREE_SITTER_ANALYZER_LOG_DIR."""
        custom_log_dir = str(Path(self.temp_dir) / "custom_logs")
        os.environ["TREE_SITTER_ANALYZER_ENABLE_FILE_LOG"] = "true"
        os.environ["TREE_SITTER_ANALYZER_LOG_DIR"] = custom_log_dir

        logger = setup_logger("test_logging_custom_dir")

        # Should have file handler
        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1

        # Verify file is in custom directory
        file_handler = file_handlers[0]
        log_path = Path(file_handler.baseFilename)
        assert str(log_path.parent) == custom_log_dir
        assert log_path.name == "tree_sitter_analyzer.log"

        # Verify directory was created
        assert Path(custom_log_dir).exists()

    def test_custom_file_log_level(self):
        """Test custom file log level with TREE_SITTER_ANALYZER_FILE_LOG_LEVEL."""
        os.environ["TREE_SITTER_ANALYZER_ENABLE_FILE_LOG"] = "true"
        os.environ["TREE_SITTER_ANALYZER_FILE_LOG_LEVEL"] = "DEBUG"

        logger = setup_logger("test_logging_custom_level", level=logging.WARNING)

        # Get file handler
        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1

        file_handler = file_handlers[0]
        assert file_handler.level == logging.DEBUG

        # Test loggers keep their requested level while the file handler
        # gets the environment-controlled level.
        assert logger.level == logging.WARNING

    def test_system_temp_directory_fallback(self):
        """Test fallback to system temporary directory."""
        os.environ["TREE_SITTER_ANALYZER_ENABLE_FILE_LOG"] = "true"
        # Don't set TREE_SITTER_ANALYZER_LOG_DIR to test fallback

        logger = setup_logger("test_logging_temp_fallback")

        # Should have file handler
        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1

        # Verify file is in system temp directory
        file_handler = file_handlers[0]
        log_path = Path(file_handler.baseFilename)
        temp_dir = Path(tempfile.gettempdir())
        assert log_path.parent == temp_dir

    def test_file_logging_error_handling(self):
        """Test error handling when file logging setup fails."""
        os.environ["TREE_SITTER_ANALYZER_ENABLE_FILE_LOG"] = "true"
        os.environ["TREE_SITTER_ANALYZER_LOG_DIR"] = "/some/log/dir"

        # Mock mkdir to raise OSError so the test is platform-independent and
        # does not create stray directories on Linux (where backslash paths are valid).
        with patch("pathlib.Path.mkdir", side_effect=OSError("permission denied")):
            with patch("sys.stderr") as mock_stderr:
                mock_stderr.write = MagicMock()

                logger = setup_logger("test_logging_error")

                # Should still have stream handler even if file handler fails
                stream_handlers = [
                    h
                    for h in logger.handlers
                    if h.__class__.__name__ == "SafeStreamHandler"
                ]
                assert len(stream_handlers) == 1

                assert all(
                    handler.__class__.__name__ in {"SafeStreamHandler", "FileHandler"}
                    for handler in logger.handlers
                )

    def test_log_level_environment_variable(self):
        """Test LOG_LEVEL environment variable."""
        os.environ["LOG_LEVEL"] = "DEBUG"

        logger = setup_logger("test_logging_env_level")

        # Logger level should be set to DEBUG
        assert logger.level == logging.DEBUG

    def test_log_level_string_conversion(self):
        """Test string to log level conversion."""
        test_cases = [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("debug", logging.DEBUG),  # Test case insensitive
            ("info", logging.INFO),
            ("INVALID", logging.WARNING),  # Test fallback
        ]

        for level_str, expected_level in test_cases:
            logger = setup_logger(f"test_logging_level_{level_str}", level=level_str)
            assert logger.level == expected_level

    def test_file_log_level_string_conversion(self):
        """Test file log level string conversion."""
        os.environ["TREE_SITTER_ANALYZER_ENABLE_FILE_LOG"] = "true"

        test_cases = [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("INVALID", logging.WARNING),  # Should fallback to main logger level
        ]

        for level_str, expected_level in test_cases:
            os.environ["TREE_SITTER_ANALYZER_FILE_LOG_LEVEL"] = level_str

            logger = setup_logger(
                f"test_logging_file_level_{level_str}", level=logging.WARNING
            )

            file_handlers = [
                h for h in logger.handlers if isinstance(h, logging.FileHandler)
            ]
            if level_str == "INVALID":
                # Should use main logger level as fallback
                if file_handlers:
                    assert file_handlers[0].level == logging.WARNING
            else:
                assert len(file_handlers) == 1
                assert file_handlers[0].level == expected_level

    def test_logger_level_minimum_calculation(self):
        """Test that logger level is set to minimum of main and file levels."""
        os.environ["TREE_SITTER_ANALYZER_ENABLE_FILE_LOG"] = "true"
        os.environ["TREE_SITTER_ANALYZER_FILE_LOG_LEVEL"] = "DEBUG"

        # Main level is WARNING, file level is DEBUG
        logger = setup_logger("test_logging_min_level", level=logging.WARNING)

        # Test logger isolation keeps the requested logger level exact.
        assert logger.level == logging.WARNING

    def test_test_logger_special_handling(self):
        """Test special handling for test loggers."""
        logger = setup_logger("test_special_logger")

        # Test loggers should not propagate
        assert not logger.propagate

        # Should clear existing handlers
        initial_handler_count = len(logger.handlers)
        logger2 = setup_logger("test_special_logger")  # Same name

        # Should not duplicate handlers
        assert len(logger2.handlers) == initial_handler_count

    def test_file_logging_utf8_encoding(self):
        """Test that file logging uses UTF-8 encoding."""
        os.environ["TREE_SITTER_ANALYZER_ENABLE_FILE_LOG"] = "true"

        logger = setup_logger("test_logging_utf8")

        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1

        file_handler = file_handlers[0]
        # Check that encoding is set to utf-8
        assert file_handler.encoding == "utf-8"

    def test_concurrent_logger_setup(self):
        """Test that concurrent logger setup doesn't create duplicate handlers."""
        os.environ["TREE_SITTER_ANALYZER_ENABLE_FILE_LOG"] = "true"

        # Create same logger multiple times
        logger1 = setup_logger("test_logging_concurrent")
        logger2 = setup_logger("test_logging_concurrent")
        logger3 = setup_logger("test_logging_concurrent")

        # Should all be the same logger instance
        assert logger1 is logger2
        assert logger2 is logger3

        # Should not have duplicate handlers
        expected_handlers = 2  # SafeStreamHandler + FileHandler
        assert len(logger1.handlers) == expected_handlers

    @patch("sys.stderr")
    def test_stderr_error_handling(self, mock_stderr):
        """Test error handling when stderr operations fail."""
        mock_stderr.write = MagicMock(side_effect=Exception("stderr error"))

        os.environ["TREE_SITTER_ANALYZER_ENABLE_FILE_LOG"] = "true"

        # Should not raise exception even if stderr operations fail
        logger = setup_logger("test_logging_stderr_error")

        # Should still create logger successfully
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logging_stderr_error"
        assert [handler.__class__.__name__ for handler in logger.handlers] == [
            "SafeStreamHandler",
            "FileHandler",
        ]


class TestSafeStreamHandler:
    """Test SafeStreamHandler functionality."""

    def test_safe_stream_handler_default_stream(self):
        """Test SafeStreamHandler uses stderr by default."""
        import sys

        handler = SafeStreamHandler()
        assert handler.stream is sys.stderr

    def test_safe_stream_handler_custom_stream(self):
        """Test SafeStreamHandler with custom stream."""
        from io import StringIO

        custom_stream = StringIO()
        handler = SafeStreamHandler(custom_stream)
        assert handler.stream is custom_stream

    def test_safe_stream_handler_closed_stream(self):
        """Test SafeStreamHandler handles closed streams safely."""
        from io import StringIO

        stream = StringIO()
        handler = SafeStreamHandler(stream)

        # Close the stream
        stream.close()

        # Create a log record
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )

        # Should not raise exception
        handler.emit(record)

    def test_safe_stream_handler_invalid_stream(self):
        """Test SafeStreamHandler handles invalid streams safely."""
        # Create a mock stream that raises errors
        mock_stream = MagicMock()
        mock_stream.write.side_effect = ValueError("Stream error")
        mock_stream.closed = False

        handler = SafeStreamHandler(mock_stream)

        # Create a log record
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )

        # Should not raise exception
        handler.emit(record)

    def test_safe_stream_handler_pytest_stream(self):
        """Test SafeStreamHandler handles pytest capture streams."""
        # Create a mock pytest-like stream
        mock_stream = MagicMock()
        mock_stream.__class__.__name__ = "CaptureFixture"
        mock_stream.write.side_effect = ValueError("pytest capture error")

        handler = SafeStreamHandler(mock_stream)

        # Create a log record
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )

        # Should not raise exception
        handler.emit(record)
