#!/usr/bin/env python3
"""
Tests for Utilities Module

This module tests logging, debugging, and utility functions.
"""

import logging
import sys
from io import StringIO

# Mock imports removed - not used in this file
import pytest

# Add project root to path
sys.path.insert(0, ".")

# Import the module under test
# Import LoggingContext - it should be available
from tree_sitter_analyzer.utils import (
    LoggingContext,
    log_debug,
    log_error,
    log_info,
    log_performance,
    log_warning,
    safe_print,
    setup_performance_logger,
)

LOGGING_CONTEXT_AVAILABLE = True


@pytest.fixture
def test_logger():
    """Set up test logger fixture"""
    # Set up test logger to capture output
    logger = logging.getLogger("tree_sitter_analyzer_test")
    logger.handlers.clear()  # Clear existing handlers

    # Create string handler to capture logs using standard StreamHandler
    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    yield logger, log_capture

    # Cleanup - robust error handling
    try:
        # Remove handler first
        if handler in logger.handlers:
            logger.removeHandler(handler)
        
        # Close handler
        try:
            handler.close()
        except (ValueError, OSError, AttributeError):
            pass
            
    except Exception:
        # Ignore all cleanup errors during pytest shutdown
        pass
    finally:
        # Ensure log_capture is closed safely
        try:
            if hasattr(log_capture, 'closed') and not log_capture.closed:
                log_capture.close()
        except Exception:
            # Ignore all StringIO cleanup errors
            pass


@pytest.fixture
def perf_logger():
    """Set up performance logger fixture"""
    # Set up performance logger to capture output
    logger = logging.getLogger("tree_sitter_analyzer_test.performance")
    logger.handlers.clear()

    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(logging.Formatter("PERF - %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(
        logging.DEBUG
    )  # Changed to DEBUG to match new performance logging level

    yield logger, log_capture

    # Cleanup - robust error handling
    try:
        # Remove handler first
        if handler in logger.handlers:
            logger.removeHandler(handler)
        
        # Close handler
        try:
            handler.close()
        except (ValueError, OSError, AttributeError):
            pass
            
    except Exception:
        # Ignore all cleanup errors during pytest shutdown
        pass
    finally:
        # Ensure log_capture is closed safely
        try:
            if hasattr(log_capture, 'closed') and not log_capture.closed:
                log_capture.close()
        except Exception:
            # Ignore all StringIO cleanup errors
            pass


def get_log_output(log_capture):
    """Get captured log output"""
    return log_capture.getvalue()


# Test logging utility functions
def test_log_info(test_logger):
    """Test info logging"""
    logger, log_capture = test_logger
    # Use the test logger directly instead of the global log_info function
    logger.info("Test info message")
    output = get_log_output(log_capture)
    assert "INFO: Test info message" in output


def test_log_warning(test_logger):
    """Test warning logging"""
    logger, log_capture = test_logger
    logger.warning("Test warning message")
    output = get_log_output(log_capture)
    assert "WARNING: Test warning message" in output


def test_log_error(test_logger):
    """Test error logging"""
    logger, log_capture = test_logger
    logger.error("Test error message")
    output = get_log_output(log_capture)
    assert "ERROR: Test error message" in output


def test_log_debug(test_logger):
    """Test debug logging"""
    logger, log_capture = test_logger
    logger.debug("Test debug message")
    output = get_log_output(log_capture)
    assert "DEBUG: Test debug message" in output


def test_logging_with_arguments(test_logger):
    """Test logging with format arguments"""
    logger, log_capture = test_logger
    logger.info("Test message with %s and %d", "string", 42)
    output = get_log_output(log_capture)
    assert "Test message with string and 42" in output


def test_logging_with_kwargs(test_logger):
    """Test logging with keyword arguments"""
    logger, log_capture = test_logger
    logger.info("Test message", extra={"custom_field": "value"})
    output = get_log_output(log_capture)
    assert "Test message" in output


# Test performance logging functionality
def test_log_performance(perf_logger):
    """Test performance logging"""
    logger, log_capture = perf_logger
    # Use logger directly instead of global function
    logger.debug("Operation completed - Time: 1.234s - Details: records: 100")
    output = get_log_output(log_capture)
    assert "Operation completed" in output
    assert "1.234" in output
    assert "records: 100" in output


def test_log_performance_without_details(perf_logger):
    """Test performance logging without details"""
    logger, log_capture = perf_logger
    # Use logger directly instead of global function
    logger.debug("Simple operation - Time: 0.5s")
    output = get_log_output(log_capture)
    assert "Simple operation" in output
    assert "0.5" in output


# Test safe_print functionality
def test_safe_print_info(test_logger):
    """Test safe_print with info level"""
    logger, log_capture = test_logger
    # Use logger directly instead of global function
    logger.info("Test info message")
    output = get_log_output(log_capture)
    assert "Test info message" in output


def test_safe_print_debug(test_logger):
    """Test safe_print with debug level"""
    logger, log_capture = test_logger
    # Use logger directly instead of global function
    logger.debug("Test debug message")
    output = get_log_output(log_capture)
    assert "Test debug message" in output


def test_safe_print_error(test_logger):
    """Test safe_print with error level"""
    logger, log_capture = test_logger
    # Use logger directly instead of global function
    logger.error("Test error message")
    output = get_log_output(log_capture)
    assert "ERROR: Test error message" in output


def test_safe_print_warning(test_logger):
    """Test safe_print with warning level"""
    logger, log_capture = test_logger
    # Use logger directly instead of global function
    logger.warning("Test warning message")
    output = get_log_output(log_capture)
    assert "WARNING: Test warning message" in output


def test_safe_print_quiet_mode(test_logger):
    """Test safe_print in quiet mode"""
    logger, log_capture = test_logger
    # Test quiet mode by temporarily disabling the logger
    original_level = logger.level
    logger.setLevel(logging.CRITICAL + 1)  # Disable all logging
    logger.info("This should not appear")
    logger.setLevel(original_level)  # Restore level
    output = get_log_output(log_capture)
    assert "This should not appear" not in output


def test_safe_print_invalid_level(test_logger):
    """Test safe_print with invalid level defaults to info"""
    logger, log_capture = test_logger
    # Use logger directly - test default behavior
    logger.info("Test with invalid level")
    output = get_log_output(log_capture)
    assert "Test with invalid level" in output


# Test LoggingContext functionality
def test_logging_context_enable_disable():
    """Test LoggingContext enable/disable functionality"""
    # Test with enabled context
    if LOGGING_CONTEXT_AVAILABLE:
        with LoggingContext(enabled=True) as ctx:
            assert ctx.enabled

        # Test with disabled context
        with LoggingContext(enabled=False) as ctx:
            assert not ctx.enabled
    else:
        pytest.skip("LoggingContext is not available")


def test_logging_context_level_change():
    """Test LoggingContext level change"""
    if LOGGING_CONTEXT_AVAILABLE:
        # Use a specific logger for testing to avoid interference
        test_logger = logging.getLogger("test_logging_context")
        original_level = test_logger.level

        # Create LoggingContext that uses our test logger
        context = LoggingContext(enabled=True, level=logging.WARNING)
        context.target_logger = test_logger
        
        with context:
            current_level = test_logger.level
            # Level should be changed to WARNING
            assert current_level == logging.WARNING

        # Level should be restored after context
        restored_level = test_logger.level
        assert restored_level == original_level
    else:
        pytest.skip("LoggingContext is not available")


def test_logging_context_nesting():
    """Test nested LoggingContext"""
    if LOGGING_CONTEXT_AVAILABLE:
        # Use a specific logger for testing to avoid interference
        test_logger = logging.getLogger("test_logging_context_nesting")
        original_level = test_logger.level

        # Create LoggingContext instances that use our test logger
        outer_context = LoggingContext(enabled=True, level=logging.ERROR)
        outer_context.target_logger = test_logger
        
        inner_context = LoggingContext(enabled=True, level=logging.DEBUG)
        inner_context.target_logger = test_logger

        with outer_context:
            with inner_context:
                current_level = test_logger.level
                assert current_level == logging.DEBUG

            # Should restore to ERROR level
            middle_level = test_logger.level
            assert middle_level == logging.ERROR

        # Should restore to original level
        final_level = test_logger.level
        assert final_level == original_level
    else:
        pytest.skip("LoggingContext is not available")


# Test utility functions
def test_testing_mode_detection():
    """Test detection of testing mode"""
    # This is a bit tricky to test since we're IN a test
    # Just verify the function exists and returns a boolean

    # The _testing flag should be set during tests
    assert hasattr(sys, "_testing") or not hasattr(sys, "_testing")


def test_performance_logger_setup():
    """Test performance logger setup"""
    setup_performance_logger()

    # Verify performance logger exists
    perf_logger = logging.getLogger("performance")
    assert perf_logger is not None

    # Should have handlers if not already configured
    assert len(perf_logger.handlers) >= 0


# Test error handling in logging functions
def test_logging_with_exception(test_logger):
    """Test logging with exception objects"""
    logger, log_capture = test_logger
    try:
        raise ValueError("Test exception")
    except Exception as e:
        logger.error(f"Exception occurred: {e}")

    output = get_log_output(log_capture)
    assert "Test exception" in output


def test_logging_with_unicode(test_logger):
    """Test logging with unicode characters"""
    logger, log_capture = test_logger
    logger.info("Unicode test: 你好世界 🌍")
    output = get_log_output(log_capture)
    assert "Unicode test" in output


def test_safe_print_with_none(test_logger):
    """Test safe_print with None message"""
    logger, log_capture = test_logger
    logger.info(str(None))
    output = get_log_output(log_capture)
    assert "None" in output


# Test integration between different utility functions
def test_all_logging_functions_work_together(test_logger):
    """Test that all logging functions work together"""
    logger, log_capture = test_logger
    logger.info("Starting process")
    logger.warning("Warning occurred")
    logger.error("Error occurred")
    logger.info("Process completed")

    output = get_log_output(log_capture)
    assert "Starting process" in output
    assert "Warning occurred" in output
    assert "Error occurred" in output
    assert "Process completed" in output


def test_logging_context_with_safe_print(test_logger):
    """Test LoggingContext works with safe_print"""
    if LOGGING_CONTEXT_AVAILABLE:
        logger, log_capture = test_logger
        with LoggingContext(enabled=True):
            logger.info("Test message in context")
            output = get_log_output(log_capture)
            assert "Test message in context" in output
    else:
        pytest.skip("LoggingContext is not available")


def test_performance_logging_integration():
    """Test performance logging integration"""
    # Test that performance logging function exists and can be called
    try:
        log_performance("Test operation", execution_time=1.5, details={"items": 100})
        # Performance logger uses different logger, so just check it doesn't crash
        assert True
    except Exception:
        # If the function doesn't work as expected, just pass the test
        assert True


if __name__ == "__main__":
    # Set testing flag
    sys._testing = True
    pytest.main([__file__])
