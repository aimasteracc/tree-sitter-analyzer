#!/usr/bin/env python3
"""
Unit tests for error_handler module

Tests error classification, handling, recovery mechanisms,
and error statistics for MCP server.
"""

import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.utils.error_handler import (
    AnalysisError,
    ErrorCategory,
    ErrorHandler,
    ErrorSeverity,
    FileAccessError,
    MCPError,
    ParsingError,
    ResourceError,
    ValidationError,
    get_error_handler,
    handle_mcp_errors,
)


class TestErrorSeverity:
    """Test ErrorSeverity enum"""

    def test_severity_values(self):
        """Test all severity levels are defined"""
        assert ErrorSeverity.LOW.value == "low"
        assert ErrorSeverity.MEDIUM.value == "medium"
        assert ErrorSeverity.HIGH.value == "high"
        assert ErrorSeverity.CRITICAL.value == "critical"

    def test_severity_comparison(self):
        """Test severity can be compared"""
        assert ErrorSeverity.LOW != ErrorSeverity.HIGH
        assert ErrorSeverity.MEDIUM == ErrorSeverity.MEDIUM


class TestErrorCategory:
    """Test ErrorCategory enum"""

    def test_category_values(self):
        """Test all categories are defined"""
        assert ErrorCategory.FILE_ACCESS.value == "file_access"
        assert ErrorCategory.PARSING.value == "parsing"
        assert ErrorCategory.ANALYSIS.value == "analysis"
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.VALIDATION.value == "validation"
        assert ErrorCategory.RESOURCE.value == "resource"
        assert ErrorCategory.CONFIGURATION.value == "configuration"
        assert ErrorCategory.UNKNOWN.value == "unknown"


class TestMCPError:
    """Test MCPError base class"""

    def test_basic_initialization(self):
        """Test basic error initialization"""
        error = MCPError("Test error message")
        assert error.message == "Test error message"
        assert error.category == ErrorCategory.UNKNOWN
        assert error.severity == ErrorSeverity.MEDIUM
        assert error.recoverable is True
        assert error.details == {}
        assert isinstance(error.timestamp, datetime)

    def test_initialization_with_all_parameters(self):
        """Test initialization with all parameters"""
        details = {"key": "value"}
        error = MCPError(
            message="Test error",
            category=ErrorCategory.PARSING,
            severity=ErrorSeverity.HIGH,
            details=details,
            recoverable=False,
        )
        assert error.message == "Test error"
        assert error.category == ErrorCategory.PARSING
        assert error.severity == ErrorSeverity.HIGH
        assert error.details == details
        assert error.recoverable is False

    def test_to_dict(self):
        """Test error conversion to dictionary"""
        error = MCPError(
            message="Test error",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            details={"field": "test"},
            recoverable=True,
        )
        error_dict = error.to_dict()
        assert error_dict["error_type"] == "MCPError"
        assert error_dict["message"] == "Test error"
        assert error_dict["category"] == "validation"
        assert error_dict["severity"] == "low"
        assert error_dict["details"] == {"field": "test"}
        assert error_dict["recoverable"] is True
        assert "timestamp" in error_dict


class TestFileAccessError:
    """Test FileAccessError subclass"""

    def test_file_access_error_initialization(self):
        """Test file access error initialization"""
        error = FileAccessError("File not found", "/path/to/file.txt")
        assert error.message == "File not found"
        assert error.category == ErrorCategory.FILE_ACCESS
        assert error.details == {"file_path": "/path/to/file.txt"}

    def test_file_access_error_with_custom_severity(self):
        """Test file access error with custom severity"""
        error = FileAccessError(
            "Permission denied",
            "/path/to/file.txt",
            severity=ErrorSeverity.CRITICAL,
            recoverable=False,
        )
        assert error.severity == ErrorSeverity.CRITICAL
        assert error.recoverable is False


class TestParsingError:
    """Test ParsingError subclass"""

    def test_parsing_error_initialization(self):
        """Test parsing error initialization"""
        error = ParsingError("Invalid syntax", "/path/to/file.py", language="python")
        assert error.message == "Invalid syntax"
        assert error.category == ErrorCategory.PARSING
        assert error.details == {
            "file_path": "/path/to/file.py",
            "language": "python",
        }

    def test_parsing_error_without_language(self):
        """Test parsing error without language specified"""
        error = ParsingError("Parse error", "/path/to/file.js")
        assert error.details["language"] is None


class TestAnalysisError:
    """Test AnalysisError subclass"""

    def test_analysis_error_initialization(self):
        """Test analysis error initialization"""
        error = AnalysisError("Analysis failed", "code_structure")
        assert error.message == "Analysis failed"
        assert error.category == ErrorCategory.ANALYSIS
        assert error.details == {"operation": "code_structure"}

    def test_analysis_error_with_custom_severity(self):
        """Test analysis error with custom severity"""
        error = AnalysisError(
            "Critical analysis error",
            "complex_analysis",
            severity=ErrorSeverity.CRITICAL,
        )
        assert error.severity == ErrorSeverity.CRITICAL


class TestValidationError:
    """Test ValidationError subclass"""

    def test_validation_error_initialization(self):
        """Test validation error initialization"""
        error = ValidationError("Invalid input", "file_path", "/invalid/path")
        assert error.message == "Invalid input"
        assert error.category == ErrorCategory.VALIDATION
        assert error.details == {"field": "file_path", "value": "/invalid/path"}

    def test_validation_error_without_value(self):
        """Test validation error without value"""
        error = ValidationError("Missing field", "required_field")
        assert error.details["value"] is None


class TestResourceError:
    """Test ResourceError subclass"""

    def test_resource_error_initialization(self):
        """Test resource error initialization"""
        error = ResourceError("Resource not found", "code://file/test.py")
        assert error.message == "Resource not found"
        assert error.category == ErrorCategory.RESOURCE
        assert error.details == {"resource_uri": "code://file/test.py"}


class TestErrorHandler:
    """Test ErrorHandler class"""

    def test_handler_initialization(self):
        """Test handler initialization"""
        handler = ErrorHandler()
        assert handler.error_counts == {}
        assert handler.error_history == []
        assert handler.max_history_size == 1000
        assert len(handler.recovery_strategies) > 0  # Default strategies registered

    def test_register_recovery_strategy(self):
        """Test registering custom recovery strategy"""
        handler = ErrorHandler()

        def custom_strategy(error, context):
            return {"custom": True}

        handler.register_recovery_strategy(RuntimeError, custom_strategy)
        assert RuntimeError in handler.recovery_strategies
        assert handler.recovery_strategies[RuntimeError] == custom_strategy

    def test_handle_mcp_error(self):
        """Test handling MCP error"""
        handler = ErrorHandler()
        error = MCPError("Test error", category=ErrorCategory.VALIDATION)
        context = {"operation": "test"}

        result = handler.handle_error(error, context, "test_operation")
        assert result["message"] == "Test error"
        assert result["category"] == "validation"
        # Note: MCPError.to_dict() doesn't include operation,
        # operation is only added in _classify_error for generic exceptions
        # Check history entry instead
        assert len(handler.error_history) == 1
        assert handler.error_history[0]["operation"] == "test_operation"

    def test_handle_generic_file_not_found_error(self):
        """Test handling generic FileNotFoundError"""
        handler = ErrorHandler()
        error = FileNotFoundError("File not found")
        context = {"file_path": "/test.txt"}

        result = handler.handle_error(error, context, "read_file")
        assert result["error_type"] == "FileNotFoundError"
        assert result["category"] == "file_access"
        assert "error" in result or "suggestion" in result

    def test_handle_permission_error(self):
        """Test handling PermissionError"""
        handler = ErrorHandler()
        error = PermissionError("Permission denied")
        context = {"file_path": "/protected.txt"}

        result = handler.handle_error(error, context, "write_file")
        assert result["error_type"] == "PermissionError"
        assert result["category"] == "file_access"
        assert result["severity"] == "high"
        assert result["recoverable"] is False

    def test_handle_value_error(self):
        """Test handling ValueError"""
        handler = ErrorHandler()
        error = ValueError("Invalid value")
        context = {"field": "age"}

        result = handler.handle_error(error, context, "validate_input")
        assert result["error_type"] == "ValueError"
        assert result["category"] == "validation"
        assert result["severity"] == "low"

    def test_handle_os_error(self):
        """Test handling OSError"""
        handler = ErrorHandler()
        error = OSError("OS error")
        context = {}

        result = handler.handle_error(error, context, "file_operation")
        assert result["error_type"] == "OSError"
        assert result["category"] == "file_access"
        assert result["severity"] == "high"

    def test_handle_runtime_error(self):
        """Test handling RuntimeError"""
        handler = ErrorHandler()
        error = RuntimeError("Runtime error")
        context = {}

        result = handler.handle_error(error, context, "analysis")
        assert result["error_type"] == "RuntimeError"
        assert result["category"] == "analysis"
        assert result["severity"] == "medium"

    def test_handle_memory_error(self):
        """Test handling MemoryError"""
        handler = ErrorHandler()
        error = MemoryError("Out of memory")
        context = {}

        result = handler.handle_error(error, context, "large_operation")
        assert result["error_type"] == "MemoryError"
        assert result["category"] == "resource"
        assert result["severity"] == "critical"
        assert result["recoverable"] is False

    def test_handle_timeout_error(self):
        """Test handling asyncio.TimeoutError"""
        handler = ErrorHandler()
        error = asyncio.TimeoutError("Timeout")
        context = {}

        result = handler.handle_error(error, context, "network_request")
        assert result["error_type"] == "TimeoutError"
        # Note: In Python 3.11+, asyncio.TimeoutError is an alias for TimeoutError
        # which inherits from OSError, so it's classified as file_access with high severity
        # rather than network with medium severity
        assert result["category"] == "file_access"
        assert result["severity"] == "high"

    def test_error_statistics_update(self):
        """Test error statistics are updated"""
        handler = ErrorHandler()
        error = FileNotFoundError("Test error")

        handler.handle_error(error, {}, "test")
        handler.handle_error(error, {}, "test")

        assert "type:FileNotFoundError" in handler.error_counts
        assert handler.error_counts["type:FileNotFoundError"] == 2
        assert "category:file_access" in handler.error_counts
        assert "severity:medium" in handler.error_counts

    def test_error_history_tracking(self):
        """Test error history is tracked"""
        handler = ErrorHandler()
        error = ValueError("Test error")

        handler.handle_error(error, {"key": "value"}, "test_operation")

        assert len(handler.error_history) == 1
        assert handler.error_history[0]["error_type"] == "ValueError"
        assert handler.error_history[0]["context"] == {"key": "value"}
        assert handler.error_history[0]["operation"] == "test_operation"

    def test_history_size_limit(self):
        """Test history size limit is enforced"""
        handler = ErrorHandler()
        handler.max_history_size = 5

        for i in range(10):
            handler.handle_error(ValueError(f"Error {i}"), {}, "test")

        assert len(handler.error_history) == 5
        assert handler.error_history[0]["message"] == "Error 5"

    def test_get_error_stats(self):
        """Test getting error statistics"""
        handler = ErrorHandler()
        handler.handle_error(FileNotFoundError("Test"), {}, "test1")
        handler.handle_error(ValueError("Test"), {}, "test2")

        stats = handler.get_error_stats()
        assert stats["total_errors"] == 2
        assert "error_counts" in stats
        assert "history_size" in stats
        assert stats["history_size"] == 2

    def test_get_recent_errors(self):
        """Test getting recent errors"""
        handler = ErrorHandler()

        for i in range(5):
            handler.handle_error(ValueError(f"Error {i}"), {}, "test")

        recent = handler.get_recent_errors(limit=3)
        assert len(recent) == 3
        assert recent[0]["message"] == "Error 2"
        assert recent[-1]["message"] == "Error 4"

    def test_get_recent_errors_empty_history(self):
        """Test getting recent errors when history is empty"""
        handler = ErrorHandler()
        recent = handler.get_recent_errors()
        assert recent == []

    def test_clear_history(self):
        """Test clearing error history"""
        handler = ErrorHandler()
        handler.handle_error(ValueError("Test"), {}, "test")

        assert len(handler.error_history) > 0
        assert len(handler.error_counts) > 0

        handler.clear_history()

        assert len(handler.error_history) == 0
        assert len(handler.error_counts) == 0

    def test_custom_recovery_strategy_called(self):
        """Test custom recovery strategy is called"""
        handler = ErrorHandler()

        def custom_recovery(error, context):
            return {"custom_recovery": True, "message": "Custom message"}

        handler.register_recovery_strategy(RuntimeError, custom_recovery)

        result = handler.handle_error(RuntimeError("Test"), {}, "test")
        assert "custom_recovery" in result
        assert result["custom_recovery"] is True

    def test_recovery_strategy_failure_handling(self):
        """Test recovery strategy failure is handled gracefully"""
        handler = ErrorHandler()

        def failing_recovery(error, context):
            raise Exception("Recovery failed")

        handler.register_recovery_strategy(RuntimeError, failing_recovery)

        # Should not raise, just log warning
        result = handler.handle_error(RuntimeError("Test"), {}, "test")
        assert result is not None

    def test_parent_class_recovery_strategy(self):
        """Test parent class recovery strategy is used"""
        handler = ErrorHandler()

        # Register strategy for Exception (parent of all exceptions)
        def parent_recovery(error, context):
            return {"parent_recovery": True}

        handler.register_recovery_strategy(Exception, parent_recovery)

        # RuntimeError inherits from Exception
        result = handler.handle_error(RuntimeError("Test"), {}, "test")
        assert "parent_recovery" in result

    def test_exact_type_match_takes_precedence(self):
        """Test exact type match takes precedence over parent class"""
        handler = ErrorHandler()

        def parent_recovery(error, context):
            return {"source": "parent"}

        def exact_recovery(error, context):
            return {"source": "exact"}

        handler.register_recovery_strategy(Exception, parent_recovery)
        handler.register_recovery_strategy(RuntimeError, exact_recovery)

        result = handler.handle_error(RuntimeError("Test"), {}, "test")
        assert result["source"] == "exact"


class TestHandleMCPErrorsDecorator:
    """Test handle_mcp_errors decorator"""

    def test_decorator_with_sync_function_success(self):
        """Test decorator with successful sync function"""

        @handle_mcp_errors(operation="test_operation")
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    def test_decorator_with_sync_function_exception(self):
        """Test decorator with exception in sync function"""

        @handle_mcp_errors(operation="test_operation")
        def test_func():
            raise ValueError("Test error")

        with pytest.raises(AnalysisError):
            test_func()

    def test_decorator_with_async_function_success(self):
        """Test decorator with successful async function"""

        @handle_mcp_errors(operation="test_operation")
        async def test_func():
            return "success"

        result = asyncio.run(test_func())
        assert result == "success"

    def test_decorator_with_async_function_exception(self):
        """Test decorator with exception in async function"""

        @handle_mcp_errors(operation="test_operation")
        async def test_func():
            raise ValueError("Test error")

        with pytest.raises(AnalysisError):
            asyncio.run(test_func())

    def test_decorator_preserves_function_name(self):
        """Test decorator preserves function name"""

        @handle_mcp_errors(operation="test")
        def my_function():
            pass

        assert my_function.__name__ == "my_function"

    def test_decorator_with_mcp_error(self):
        """Test decorator with MCPError (should re-raise as-is)"""

        @handle_mcp_errors(operation="test_operation")
        def test_func():
            raise MCPError("MCP error", category=ErrorCategory.VALIDATION)

        with pytest.raises(MCPError) as exc_info:
            test_func()

        assert exc_info.value.message == "MCP error"

    def test_decorator_with_runtime_error_not_initialized(self):
        """Test decorator handles 'not fully initialized' runtime error"""

        @handle_mcp_errors(operation="test_operation")
        async def test_func():
            raise RuntimeError("Server is not fully initialized")

        with pytest.raises(MCPError) as exc_info:
            asyncio.run(test_func())

        assert "still initializing" in exc_info.value.message.lower()
        assert exc_info.value.category == ErrorCategory.CONFIGURATION

    def test_decorator_updates_error_stats(self):
        """Test decorator updates error statistics"""
        handler = get_error_handler()
        initial_count = sum(handler.error_counts.values())

        @handle_mcp_errors(operation="test")
        def test_func():
            raise ValueError("Test error")

        try:
            test_func()
        except AnalysisError:
            pass

        final_count = sum(handler.error_counts.values())
        assert final_count > initial_count


class TestGetErrorHandler:
    """Test get_error_handler function"""

    def test_get_error_handler_returns_singleton(self):
        """Test get_error_handler returns singleton instance"""
        handler1 = get_error_handler()
        handler2 = get_error_handler()
        assert handler1 is handler2

    def test_get_error_handler_is_error_handler_instance(self):
        """Test get_error_handler returns ErrorHandler instance"""
        handler = get_error_handler()
        assert isinstance(handler, ErrorHandler)


class TestErrorHandlerLogging:
    """Test error handler logging behavior"""

    @patch("tree_sitter_analyzer.mcp.utils.error_handler.logger")
    def test_critical_error_logging(self, mock_logger):
        """Test critical errors are logged at critical level"""
        handler = ErrorHandler()
        error = MemoryError("Out of memory")

        handler.handle_error(error, {}, "test")

        mock_logger.critical.assert_called_once()

    @patch("tree_sitter_analyzer.mcp.utils.error_handler.logger")
    def test_high_severity_error_logging(self, mock_logger):
        """Test high severity errors are logged at error level"""
        handler = ErrorHandler()
        error = PermissionError("Permission denied")

        handler.handle_error(error, {}, "test")

        mock_logger.error.assert_called_once()

    @patch("tree_sitter_analyzer.mcp.utils.error_handler.logger")
    def test_medium_severity_error_logging(self, mock_logger):
        """Test medium severity errors are logged at warning level"""
        handler = ErrorHandler()
        error = FileNotFoundError("File not found")

        handler.handle_error(error, {}, "test")

        mock_logger.warning.assert_called_once()

    @patch("tree_sitter_analyzer.mcp.utils.error_handler.logger")
    def test_low_severity_error_logging(self, mock_logger):
        """Test low severity errors are logged at info level"""
        handler = ErrorHandler()
        error = ValueError("Invalid value")

        # Reset mock to clear initialization log
        mock_logger.reset_mock()

        handler.handle_error(error, {}, "test")

        mock_logger.info.assert_called_once()


class TestErrorHandlerRecovery:
    """Test error handler recovery mechanisms"""

    def test_recovery_strategy_returns_none(self):
        """Test recovery strategy returning None is handled"""
        handler = ErrorHandler()

        def none_recovery(error, context):
            return None

        handler.register_recovery_strategy(RuntimeError, none_recovery)

        result = handler.handle_error(RuntimeError("Test"), {}, "test")
        assert result is not None  # Should still return error info

    def test_recovery_strategy_returns_empty_dict(self):
        """Test recovery strategy returning empty dict is handled"""
        handler = ErrorHandler()

        def empty_recovery(error, context):
            return {}

        handler.register_recovery_strategy(RuntimeError, empty_recovery)

        result = handler.handle_error(RuntimeError("Test"), {}, "test")
        assert result is not None

    def test_multiple_recovery_strategies(self):
        """Test multiple recovery strategies can be registered"""
        handler = ErrorHandler()

        handler.register_recovery_strategy(ValueError, lambda e, c: {"value": True})
        handler.register_recovery_strategy(TypeError, lambda e, c: {"type": True})

        result1 = handler.handle_error(ValueError("Test"), {}, "test")
        result2 = handler.handle_error(TypeError("Test"), {}, "test")

        assert "value" in result1
        assert "type" in result2


class TestErrorHandlerEdgeCases:
    """Test error handler edge cases"""

    def test_handle_error_with_none_context(self):
        """Test handling error with None context"""
        handler = ErrorHandler()
        error = ValueError("Test")

        result = handler.handle_error(error, None, "test")
        assert result is not None
        assert result["details"] == {}

    def test_handle_error_with_empty_operation(self):
        """Test handling error with empty operation name"""
        handler = ErrorHandler()
        error = ValueError("Test")

        result = handler.handle_error(error, {}, "")
        assert result is not None
        assert result["operation"] == ""

    def test_get_error_stats_with_no_errors(self):
        """Test getting stats when no errors occurred"""
        handler = ErrorHandler()
        stats = handler.get_error_stats()
        assert stats["total_errors"] == 0
        assert stats["history_size"] == 0

    def test_clear_history_with_no_history(self):
        """Test clearing history when already empty"""
        handler = ErrorHandler()
        handler.clear_history()
        assert len(handler.error_history) == 0
        assert len(handler.error_counts) == 0

    def test_error_with_complex_details(self):
        """Test error with complex details dictionary"""
        handler = ErrorHandler()
        error = MCPError(
            "Complex error",
            details={
                "nested": {"key": "value"},
                "list": [1, 2, 3],
                "number": 42,
            },
        )

        result = handler.handle_error(error, {}, "test")
        assert result["details"]["nested"]["key"] == "value"
        assert result["details"]["list"] == [1, 2, 3]
        assert result["details"]["number"] == 42
