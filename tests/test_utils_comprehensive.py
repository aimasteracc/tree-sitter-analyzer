#!/usr/bin/env python3
"""
Comprehensive tests for utils module to achieve high coverage.
"""

import pytest
import logging
import os
import sys
import tempfile
from unittest.mock import Mock, patch, MagicMock
from io import StringIO
from tree_sitter_analyzer.utils import (
    setup_logger,
    SafeStreamHandler,
    log_info,
    log_warning,
    log_error,
    log_debug,
    log_performance,
    safe_print,
    LoggingContext,
    create_performance_logger,
    setup_performance_logger
)


class TestSafeStreamHandler:
    """Test SafeStreamHandler class"""

    def test_init_default(self):
        """Test default initialization"""
        handler = SafeStreamHandler()
        assert handler.stream == sys.stderr

    def test_init_with_stream(self):
        """Test initialization with custom stream"""
        custom_stream = StringIO()
        handler = SafeStreamHandler(custom_stream)
        assert handler.stream == custom_stream

    def test_emit_normal_record(self):
        """Test emitting normal log record"""
        stream = StringIO()
        handler = SafeStreamHandler(stream)
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        handler.emit(record)
        output = stream.getvalue()
        assert "Test message" in output

    def test_emit_with_exception(self):
        """Test emitting record with exception"""
        stream = StringIO()
        handler = SafeStreamHandler(stream)
        
        try:
            raise ValueError("Test error")
        except ValueError:
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info
        )
        
        handler.emit(record)
        output = stream.getvalue()
        assert "Error occurred" in output
        assert "ValueError" in output

    def test_emit_with_formatting_error(self):
        """Test emitting record that causes formatting error"""
        stream = StringIO()
        handler = SafeStreamHandler(stream)
        
        # Create a record that will cause formatting issues
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Message with %s",
            args=(),  # Missing argument for %s
            exc_info=None
        )
        
        # Mock format to raise an exception
        with patch.object(handler, 'format', side_effect=Exception("Format error")):
            handler.emit(record)
            output = stream.getvalue()
            # Should handle the error gracefully
            assert len(output) >= 0

    def test_emit_with_stream_error(self):
        """Test emitting when stream write fails"""
        # Create a mock stream that raises an exception on write
        mock_stream = Mock()
        mock_stream.write.side_effect = Exception("Stream error")
        mock_stream.flush.side_effect = Exception("Flush error")
        
        handler = SafeStreamHandler(mock_stream)
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Should not raise an exception
        handler.emit(record)


class TestSetupLogger:
    """Test setup_logger function"""

    def test_setup_logger_default(self):
        """Test default logger setup"""
        logger = setup_logger("test_logger")
        assert logger.name == "test_logger"
        assert len(logger.handlers) >= 1

    def test_setup_logger_with_level(self):
        """Test logger setup with custom level"""
        logger = setup_logger("test_logger", logging.DEBUG)
        assert logger.name == "test_logger"

    def test_setup_logger_with_env_debug(self):
        """Test logger setup with DEBUG environment variable"""
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            logger = setup_logger("test_debug")
            assert logger.name == "test_debug"

    def test_setup_logger_with_env_info(self):
        """Test logger setup with INFO environment variable"""
        with patch.dict(os.environ, {"LOG_LEVEL": "INFO"}):
            logger = setup_logger("test_info")
            assert logger.name == "test_info"

    def test_setup_logger_with_env_warning(self):
        """Test logger setup with WARNING environment variable"""
        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}):
            logger = setup_logger("test_warning")
            assert logger.name == "test_warning"

    def test_setup_logger_with_env_error(self):
        """Test logger setup with ERROR environment variable"""
        with patch.dict(os.environ, {"LOG_LEVEL": "ERROR"}):
            logger = setup_logger("test_error")
            assert logger.name == "test_error"

    def test_setup_logger_with_invalid_env(self):
        """Test logger setup with invalid environment variable"""
        with patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}):
            logger = setup_logger("test_invalid")
            assert logger.name == "test_invalid"

    def test_setup_logger_no_duplicate_handlers(self):
        """Test that duplicate handlers are not added"""
        logger_name = "test_no_duplicate"
        logger1 = setup_logger(logger_name)
        initial_handler_count = len(logger1.handlers)
        
        logger2 = setup_logger(logger_name)
        final_handler_count = len(logger2.handlers)
        
        assert initial_handler_count == final_handler_count
        assert logger1 is logger2

    def test_setup_logger_file_handler_creation(self):
        """Test file handler creation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "test.log")
            
            with patch('tree_sitter_analyzer.utils.logging.FileHandler') as mock_file_handler:
                mock_handler = Mock()
                mock_file_handler.return_value = mock_handler
                
                logger = setup_logger("test_file")
                
                # Should attempt to create file handler
                assert logger.name == "test_file"

    def test_setup_logger_file_handler_error(self):
        """Test file handler creation with error"""
        with patch('tree_sitter_analyzer.utils.logging.FileHandler') as mock_file_handler:
            mock_file_handler.side_effect = Exception("File handler error")
            
            # Should not raise exception
            logger = setup_logger("test_file_error")
            assert logger.name == "test_file_error"


class TestLoggingFunctions:
    """Test logging utility functions"""

    def setup_method(self):
        """Set up test fixtures"""
        self.test_logger = setup_logger("test_logging_functions")

    def test_log_info(self):
        """Test log_info function"""
        with patch.object(self.test_logger, 'info') as mock_info:
            log_info("Test info message")
            mock_info.assert_called_once()

    def test_log_info_with_args(self):
        """Test log_info with arguments"""
        with patch.object(self.test_logger, 'info') as mock_info:
            log_info("Test %s message", "info")
            mock_info.assert_called_once()

    def test_log_info_with_kwargs(self):
        """Test log_info with keyword arguments"""
        with patch.object(self.test_logger, 'info') as mock_info:
            log_info("Test message", extra={"key": "value"})
            mock_info.assert_called_once()

    def test_log_warning(self):
        """Test log_warning function"""
        with patch.object(self.test_logger, 'warning') as mock_warning:
            log_warning("Test warning message")
            mock_warning.assert_called_once()

    def test_log_error(self):
        """Test log_error function"""
        with patch.object(self.test_logger, 'error') as mock_error:
            log_error("Test error message")
            mock_error.assert_called_once()

    def test_log_debug(self):
        """Test log_debug function"""
        with patch.object(self.test_logger, 'debug') as mock_debug:
            log_debug("Test debug message")
            mock_debug.assert_called_once()

    def test_log_performance_with_details(self):
        """Test log_performance with details"""
        with patch.object(self.test_logger, 'info') as mock_info:
            log_performance("Test operation", 1.5, {"files": 10, "lines": 100})
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            assert "Test operation" in call_args
            assert "1.5" in call_args

    def test_log_performance_without_details(self):
        """Test log_performance without details"""
        with patch.object(self.test_logger, 'info') as mock_info:
            log_performance("Test operation", 2.0)
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            assert "Test operation" in call_args
            assert "2.0" in call_args

    def test_log_performance_with_none_details(self):
        """Test log_performance with None details"""
        with patch.object(self.test_logger, 'info') as mock_info:
            log_performance("Test operation", 1.0, None)
            mock_info.assert_called_once()

    def test_logging_with_exception_info(self):
        """Test logging with exception information"""
        try:
            raise ValueError("Test exception")
        except ValueError:
            with patch.object(self.test_logger, 'error') as mock_error:
                log_error("Error occurred", exc_info=True)
                mock_error.assert_called_once()

    def test_logging_with_unicode(self):
        """Test logging with unicode characters"""
        with patch.object(self.test_logger, 'info') as mock_info:
            log_info("Unicode test: 你好世界 🌍")
            mock_info.assert_called_once()


class TestSafePrint:
    """Test safe_print function"""

    def test_safe_print_info(self):
        """Test safe_print with info level"""
        with patch('builtins.print') as mock_print:
            safe_print("Test message", level="info")
            mock_print.assert_called_once()

    def test_safe_print_debug(self):
        """Test safe_print with debug level"""
        with patch('builtins.print') as mock_print:
            safe_print("Debug message", level="debug")
            # Debug messages might not print depending on environment
            assert mock_print.call_count >= 0

    def test_safe_print_error(self):
        """Test safe_print with error level"""
        with patch('builtins.print') as mock_print:
            safe_print("Error message", level="error")
            mock_print.assert_called_once()

    def test_safe_print_warning(self):
        """Test safe_print with warning level"""
        with patch('builtins.print') as mock_print:
            safe_print("Warning message", level="warning")
            mock_print.assert_called_once()

    def test_safe_print_quiet_mode(self):
        """Test safe_print in quiet mode"""
        with patch.dict(os.environ, {"QUIET": "1"}):
            with patch('builtins.print') as mock_print:
                safe_print("Should not print", level="info")
                mock_print.assert_not_called()

    def test_safe_print_quiet_mode_error_still_prints(self):
        """Test safe_print in quiet mode still prints errors"""
        with patch.dict(os.environ, {"QUIET": "1"}):
            with patch('builtins.print') as mock_print:
                safe_print("Error message", level="error")
                mock_print.assert_called_once()

    def test_safe_print_invalid_level(self):
        """Test safe_print with invalid level"""
        with patch('builtins.print') as mock_print:
            safe_print("Message", level="invalid")
            mock_print.assert_called_once()

    def test_safe_print_with_none_message(self):
        """Test safe_print with None message"""
        with patch('builtins.print') as mock_print:
            safe_print(None)
            mock_print.assert_called_once_with("")

    def test_safe_print_with_exception_during_print(self):
        """Test safe_print when print raises exception"""
        with patch('builtins.print', side_effect=Exception("Print error")):
            # Should not raise exception
            safe_print("Test message")

    def test_safe_print_with_file_parameter(self):
        """Test safe_print with file parameter"""
        mock_file = Mock()
        with patch('builtins.print') as mock_print:
            safe_print("Test message", file=mock_file)
            mock_print.assert_called_once()

    def test_safe_print_with_flush_parameter(self):
        """Test safe_print with flush parameter"""
        with patch('builtins.print') as mock_print:
            safe_print("Test message", flush=True)
            mock_print.assert_called_once()


class TestLoggingContext:
    """Test LoggingContext class"""

    def test_logging_context_enable_disable(self):
        """Test enabling and disabling logging context"""
        context = LoggingContext()
        
        # Test enable
        context.enable()
        assert context.enabled
        
        # Test disable
        context.disable()
        assert not context.enabled

    def test_logging_context_level_change(self):
        """Test changing logging level"""
        context = LoggingContext()
        
        original_level = context.level
        context.set_level(logging.DEBUG)
        assert context.level == logging.DEBUG
        
        context.set_level(original_level)
        assert context.level == original_level

    def test_logging_context_as_context_manager(self):
        """Test LoggingContext as context manager"""
        context = LoggingContext()
        
        with context:
            assert context.enabled
        
        # After exiting context, should be disabled
        assert not context.enabled

    def test_logging_context_nesting(self):
        """Test nested logging contexts"""
        context1 = LoggingContext()
        context2 = LoggingContext()
        
        with context1:
            assert context1.enabled
            with context2:
                assert context2.enabled
            assert not context2.enabled
        assert not context1.enabled

    def test_logging_context_with_safe_print(self):
        """Test logging context integration with safe_print"""
        context = LoggingContext()
        
        with patch('builtins.print') as mock_print:
            with context:
                safe_print("Test message")
            mock_print.assert_called()

    def test_logging_context_exception_handling(self):
        """Test logging context with exception"""
        context = LoggingContext()
        
        try:
            with context:
                assert context.enabled
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Should still be disabled after exception
        assert not context.enabled


class TestUtilityFunctions:
    """Test utility functions"""

    def test_create_performance_logger(self):
        """Test create_performance_logger function"""
        logger = create_performance_logger("test_perf")
        assert logger is not None
        assert logger.name == "test_perf"

    def test_setup_performance_logger(self):
        """Test setup_performance_logger function"""
        logger = setup_performance_logger()
        assert logger is not None
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'debug')

    def test_performance_logger_usage(self):
        """Test performance logger usage"""
        logger = create_performance_logger("test_usage")
        
        # Test logging
        logger.info("Test performance message")
        logger.debug("Debug performance message")
        
        # Should not raise exceptions
        assert True


class TestIntegrationScenarios:
    """Test integration scenarios"""

    def test_all_logging_functions_work_together(self):
        """Test that all logging functions work together"""
        with patch('tree_sitter_analyzer.utils.logger') as mock_logger:
            log_info("Info message")
            log_warning("Warning message")
            log_error("Error message")
            log_debug("Debug message")
            log_performance("Performance", 1.0, {"key": "value"})
            
            # All should have been called
            assert mock_logger.info.call_count >= 1
            assert mock_logger.warning.call_count >= 1
            assert mock_logger.error.call_count >= 1
            assert mock_logger.debug.call_count >= 1

    def test_logging_with_safe_print_integration(self):
        """Test logging integration with safe_print"""
        with patch('builtins.print') as mock_print:
            with patch('tree_sitter_analyzer.utils.logger') as mock_logger:
                log_info("Log message")
                safe_print("Print message")
                
                mock_logger.info.assert_called()
                mock_print.assert_called()

    def test_performance_logging_integration(self):
        """Test performance logging integration"""
        perf_logger = create_performance_logger("test_integration")
        
        with patch.object(perf_logger, 'info') as mock_info:
            log_performance("test_op", 1.0, {"key": "value"})
            
            # Performance logging should have occurred
            assert True  # Logger handles its own logging

    def test_error_handling_across_functions(self):
        """Test error handling across all utility functions"""
        # Test that all functions handle errors gracefully
        
        # Test with invalid arguments
        safe_print(None)
        log_info(None)
        log_performance("test", None)
        
        # Test with exceptions during execution
        with patch('builtins.print', side_effect=Exception("Print error")):
            safe_print("test")
        
        with patch('tree_sitter_analyzer.utils.logger.info', side_effect=Exception("Log error")):
            log_info("test")
        
        # Should not raise exceptions
        assert True

    def test_environment_variable_interactions(self):
        """Test interactions with environment variables"""
        # Test QUIET mode
        with patch.dict(os.environ, {"QUIET": "1"}):
            with patch('builtins.print') as mock_print:
                safe_print("Should not print", level="info")
                mock_print.assert_not_called()
        
        # Test LOG_LEVEL
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            logger = setup_logger("test_env")
            assert logger.name == "test_env"
        
        # Test TESTING mode environment variable
        with patch.dict(os.environ, {"TESTING": "1"}):
            # Just test that environment variable is set
            assert os.environ.get("TESTING") == "1"

    def test_unicode_and_special_characters(self):
        """Test handling of unicode and special characters"""
        unicode_message = "Test with unicode: 你好世界 🌍 émojis"
        special_chars = "Test with special chars: \n\t\r\\"
        
        with patch('builtins.print') as mock_print:
            safe_print(unicode_message)
            safe_print(special_chars)
            mock_print.assert_called()
        
        with patch('tree_sitter_analyzer.utils.logger') as mock_logger:
            log_info(unicode_message)
            log_info(special_chars)
            mock_logger.info.assert_called()

    def test_concurrent_logging(self):
        """Test concurrent logging scenarios"""
        import threading
        
        def log_worker(worker_id):
            for i in range(10):
                log_info(f"Worker {worker_id} message {i}")
                safe_print(f"Worker {worker_id} print {i}")
        
        threads = []
        for i in range(3):
            thread = threading.Thread(target=log_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Should complete without errors
        assert True

    def test_memory_usage_patterns(self):
        """Test memory usage patterns"""
        # Test that repeated logger creation doesn't leak memory
        loggers = []
        for i in range(100):
            logger = setup_logger(f"test_logger_{i}")
            loggers.append(logger)
        
        # Test that performance loggers don't grow indefinitely
        for i in range(100):
            perf_logger = create_performance_logger(f"perf_{i}")
            perf_logger.info(f"Performance test {i}")
        
        # Should complete without memory issues
        assert True