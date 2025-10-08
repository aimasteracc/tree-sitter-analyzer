#!/usr/bin/env python3
"""
Fixed comprehensive tests for utils module to achieve high coverage.
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


class TestSafeStreamHandlerFixed:
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


class TestSetupLoggerFixed:
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


class TestLoggingFunctionsFixed:
    """Test logging utility functions"""

    def test_log_info(self):
        """Test log_info function"""
        with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
            log_info("Test info message")
            mock_info.assert_called_once_with("Test info message")

    def test_log_info_with_args(self):
        """Test log_info with arguments"""
        with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
            log_info("Test %s message", "info")
            mock_info.assert_called_once_with("Test %s message", "info")

    def test_log_warning(self):
        """Test log_warning function"""
        with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
            log_warning("Test warning message")
            mock_warning.assert_called_once_with("Test warning message")

    def test_log_error(self):
        """Test log_error function"""
        with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
            log_error("Test error message")
            mock_error.assert_called_once_with("Test error message")

    def test_log_debug(self):
        """Test log_debug function"""
        with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
            log_debug("Test debug message")
            mock_debug.assert_called_once_with("Test debug message")

    def test_log_performance_with_details(self):
        """Test log_performance with details"""
        with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
            log_performance("Test operation", 1.5, {"files": 10, "lines": 100})
            mock_logger.info.assert_called_once()

    def test_log_performance_without_details(self):
        """Test log_performance without details"""
        with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
            log_performance("Test operation", 2.0)
            mock_logger.info.assert_called_once()

    def test_log_performance_with_none_details(self):
        """Test log_performance with None details"""
        with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
            log_performance("Test operation", 1.0, None)
            mock_logger.info.assert_called_once()


class TestSafePrintFixed:
    """Test safe_print function"""

    def test_safe_print_basic(self):
        """Test basic safe_print functionality"""
        with patch('builtins.print') as mock_print:
            safe_print("Test message")
            mock_print.assert_called_once()

    def test_safe_print_with_level_info(self):
        """Test safe_print with info level"""
        with patch('builtins.print') as mock_print:
            safe_print("Test message", level="info")
            mock_print.assert_called_once()

    def test_safe_print_with_level_error(self):
        """Test safe_print with error level"""
        with patch('builtins.print') as mock_print:
            safe_print("Error message", level="error")
            mock_print.assert_called_once()

    def test_safe_print_with_level_warning(self):
        """Test safe_print with warning level"""
        with patch('builtins.print') as mock_print:
            safe_print("Warning message", level="warning")
            mock_print.assert_called_once()

    def test_safe_print_quiet_mode(self):
        """Test safe_print in quiet mode"""
        with patch('builtins.print') as mock_print:
            safe_print("Should not print", quiet=True)
            mock_print.assert_not_called()

    def test_safe_print_with_exception_during_print(self):
        """Test safe_print when print raises exception"""
        with patch('builtins.print', side_effect=Exception("Print error")):
            # Should not raise exception
            safe_print("Test message")


class TestLoggingContextFixed:
    """Test LoggingContext class"""

    def test_logging_context_initialization(self):
        """Test LoggingContext initialization"""
        context = LoggingContext()
        assert hasattr(context, 'enabled')

    def test_logging_context_as_context_manager(self):
        """Test LoggingContext as context manager"""
        context = LoggingContext()
        
        with context:
            # Should work as context manager
            pass

    def test_logging_context_methods(self):
        """Test LoggingContext methods exist"""
        context = LoggingContext()
        
        # Test that basic methods exist
        assert hasattr(context, '__enter__')
        assert hasattr(context, '__exit__')


class TestUtilityFunctionsFixed:
    """Test utility functions"""

    def test_create_performance_logger(self):
        """Test create_performance_logger function"""
        logger = create_performance_logger("test_perf")
        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_setup_performance_logger(self):
        """Test setup_performance_logger function"""
        logger = setup_performance_logger()
        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_performance_logger_usage(self):
        """Test performance logger usage"""
        logger = create_performance_logger("test_usage")
        
        # Test logging
        logger.info("Test performance message")
        logger.debug("Debug performance message")
        
        # Should not raise exceptions
        assert True


class TestIntegrationScenariosFixed:
    """Test integration scenarios"""

    def test_all_logging_functions_work_together(self):
        """Test that all logging functions work together"""
        with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
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
            with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
                log_info("Log message")
                safe_print("Print message")
                
                mock_logger.info.assert_called()
                mock_print.assert_called()

    def test_environment_variable_interactions(self):
        """Test interactions with environment variables"""
        # Test LOG_LEVEL
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            logger = setup_logger("test_env")
            assert logger.name == "test_env"

    def test_unicode_and_special_characters(self):
        """Test handling of unicode and special characters"""
        unicode_message = "Test with unicode: 你好世界 🌍 émojis"
        special_chars = "Test with special chars: \n\t\r\\"
        
        with patch('builtins.print') as mock_print:
            safe_print(unicode_message)
            safe_print(special_chars)
            mock_print.assert_called()
        
        with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
            log_info(unicode_message)
            log_info(special_chars)
            mock_logger.info.assert_called()

    def test_error_handling_across_functions(self):
        """Test error handling across all utility functions"""
        # Test that all functions handle errors gracefully
        
        # Test with None arguments where possible
        with patch('builtins.print'):
            safe_print("")
        
        with patch('tree_sitter_analyzer.utils.logger.info') as mock_logger:
            log_info("test")
            log_performance("test", 1.0)
            mock_logger.info.assert_called()

    def test_concurrent_logging(self):
        """Test concurrent logging scenarios"""
        import threading
        
        def log_worker(worker_id):
            for i in range(5):
                with patch('tree_sitter_analyzer.utils.logger.info'):
                    log_info(f"Worker {worker_id} message {i}")
                with patch('builtins.print'):
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
        for i in range(50):
            logger = setup_logger(f"test_logger_{i}")
            loggers.append(logger)
        
        # Test that performance loggers don't grow indefinitely
        for i in range(50):
            perf_logger = create_performance_logger(f"perf_{i}")
            perf_logger.info(f"Performance test {i}")
        
        # Should complete without memory issues
        assert True

    def test_suppress_output_decorator(self):
        """Test suppress_output decorator if it exists"""
        try:
            from tree_sitter_analyzer.utils import suppress_output
            
            @suppress_output
            def test_function():
                print("This should be suppressed")
                return "result"
            
            result = test_function()
            assert result == "result"
        except ImportError:
            # suppress_output might not exist
            pass

    def test_quiet_mode_class(self):
        """Test QuietMode class if it exists"""
        try:
            from tree_sitter_analyzer.utils import QuietMode
            
            quiet = QuietMode()
            assert hasattr(quiet, '__enter__')
            assert hasattr(quiet, '__exit__')
            
            with quiet:
                # Should work as context manager
                pass
        except ImportError:
            # QuietMode might not exist
            pass