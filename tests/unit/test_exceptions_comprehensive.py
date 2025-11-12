"""
Comprehensive tests for exceptions.py

Tests for all custom exception types and exception handling utilities.
"""

from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.exceptions import (
    AnalysisError,
    ConfigurationError,
    FileHandlingError,
    FileRestrictionError,
    LanguageNotSupportedError,
    MCPError,
    MCPResourceError,
    MCPTimeoutError,
    MCPToolError,
    MCPValidationError,
    ParseError,
    PathTraversalError,
    PluginError,
    QueryError,
    RegexSecurityError,
    SecurityError,
    TreeSitterAnalyzerError,
    ValidationError,
    create_error_response,
    create_mcp_error_response,
    handle_exception,
    handle_exceptions,
    mcp_exception_handler,
    safe_execute,
    safe_execute_async,
)


class TestBaseException:
    """Test TreeSitterAnalyzerError base exception."""

    def test_base_exception_initialization(self) -> None:
        """Test base exception can be initialized with message only."""
        exc = TreeSitterAnalyzerError("Test error")
        assert exc.message == "Test error"
        assert exc.error_code == "TreeSitterAnalyzerError"
        assert exc.context == {}

    def test_base_exception_with_error_code(self) -> None:
        """Test base exception with custom error code."""
        exc = TreeSitterAnalyzerError("Test error", error_code="CUSTOM_001")
        assert exc.error_code == "CUSTOM_001"

    def test_base_exception_with_context(self) -> None:
        """Test base exception with context dictionary."""
        context = {"file": "test.py", "line": 42}
        exc = TreeSitterAnalyzerError("Test error", context=context)
        assert exc.context == context

    def test_base_exception_to_dict(self) -> None:
        """Test exception conversion to dictionary."""
        exc = TreeSitterAnalyzerError(
            "Test error", error_code="TEST_001", context={"key": "value"}
        )
        result = exc.to_dict()

        assert result["error_type"] == "TreeSitterAnalyzerError"
        assert result["error_code"] == "TEST_001"
        assert result["message"] == "Test error"
        assert result["context"] == {"key": "value"}

    def test_base_exception_str_representation(self) -> None:
        """Test exception string representation."""
        exc = TreeSitterAnalyzerError("Test error")
        assert str(exc) == "Test error"


class TestAnalysisError:
    """Test AnalysisError exception."""

    def test_analysis_error_basic(self) -> None:
        """Test AnalysisError with basic message."""
        exc = AnalysisError("Analysis failed")
        assert exc.message == "Analysis failed"
        assert exc.context == {}

    def test_analysis_error_with_file_path(self) -> None:
        """Test AnalysisError with file path."""
        exc = AnalysisError("Analysis failed", file_path="/path/to/file.py")
        assert exc.context["file_path"] == "/path/to/file.py"

    def test_analysis_error_with_path_object(self) -> None:
        """Test AnalysisError with Path object."""
        path = Path("/path/to/file.py")
        exc = AnalysisError("Analysis failed", file_path=path)
        assert exc.context["file_path"] == str(path)

    def test_analysis_error_with_language(self) -> None:
        """Test AnalysisError with language parameter."""
        exc = AnalysisError("Analysis failed", language="python")
        assert exc.context["language"] == "python"

    def test_analysis_error_with_all_params(self) -> None:
        """Test AnalysisError with all parameters."""
        exc = AnalysisError(
            "Analysis failed", file_path="/test.py", language="python"
        )
        assert exc.context["file_path"] == "/test.py"
        assert exc.context["language"] == "python"


class TestParseError:
    """Test ParseError exception."""

    def test_parse_error_basic(self) -> None:
        """Test ParseError with basic message."""
        exc = ParseError("Parse failed")
        assert exc.message == "Parse failed"

    def test_parse_error_with_language(self) -> None:
        """Test ParseError with language."""
        exc = ParseError("Parse failed", language="javascript")
        assert exc.context["language"] == "javascript"

    def test_parse_error_with_source_info(self) -> None:
        """Test ParseError with source information."""
        source_info = {"line": 10, "column": 5, "offset": 150}
        exc = ParseError("Parse failed", source_info=source_info)
        assert exc.context["line"] == 10
        assert exc.context["column"] == 5
        assert exc.context["offset"] == 150


class TestLanguageNotSupportedError:
    """Test LanguageNotSupportedError exception."""

    def test_language_not_supported_basic(self) -> None:
        """Test LanguageNotSupportedError with language name."""
        exc = LanguageNotSupportedError("rust")
        assert "rust" in exc.message
        assert exc.context["language"] == "rust"

    def test_language_not_supported_with_list(self) -> None:
        """Test LanguageNotSupportedError with supported languages list."""
        supported = ["python", "java", "javascript"]
        exc = LanguageNotSupportedError("rust", supported_languages=supported)
        assert "rust" in exc.message
        assert "python" in exc.message
        assert exc.context["supported_languages"] == supported


class TestPluginError:
    """Test PluginError exception."""

    def test_plugin_error_basic(self) -> None:
        """Test PluginError with basic message."""
        exc = PluginError("Plugin failed")
        assert exc.message == "Plugin failed"

    def test_plugin_error_with_plugin_name(self) -> None:
        """Test PluginError with plugin name."""
        exc = PluginError("Plugin failed", plugin_name="JavaPlugin")
        assert exc.context["plugin_name"] == "JavaPlugin"

    def test_plugin_error_with_operation(self) -> None:
        """Test PluginError with operation."""
        exc = PluginError("Plugin failed", operation="initialize")
        assert exc.context["operation"] == "initialize"


class TestQueryError:
    """Test QueryError exception."""

    def test_query_error_basic(self) -> None:
        """Test QueryError with basic message."""
        exc = QueryError("Query failed")
        assert exc.message == "Query failed"

    def test_query_error_with_all_params(self) -> None:
        """Test QueryError with all parameters."""
        exc = QueryError(
            "Query failed",
            query_name="methods",
            query_string="(method_declaration) @method",
            language="java",
        )
        assert exc.context["query_name"] == "methods"
        assert exc.context["query_string"] == "(method_declaration) @method"
        assert exc.context["language"] == "java"


class TestFileHandlingError:
    """Test FileHandlingError exception."""

    def test_file_handling_error_basic(self) -> None:
        """Test FileHandlingError with basic message."""
        exc = FileHandlingError("File operation failed")
        assert exc.message == "File operation failed"

    def test_file_handling_error_with_path(self) -> None:
        """Test FileHandlingError with file path."""
        exc = FileHandlingError("File operation failed", file_path="/test.txt")
        assert exc.context["file_path"] == "/test.txt"

    def test_file_handling_error_with_operation(self) -> None:
        """Test FileHandlingError with operation type."""
        exc = FileHandlingError("File operation failed", operation="read")
        assert exc.context["operation"] == "read"


class TestConfigurationError:
    """Test ConfigurationError exception."""

    def test_configuration_error_basic(self) -> None:
        """Test ConfigurationError with basic message."""
        exc = ConfigurationError("Invalid configuration")
        assert exc.message == "Invalid configuration"

    def test_configuration_error_with_key_value(self) -> None:
        """Test ConfigurationError with config key and value."""
        exc = ConfigurationError(
            "Invalid configuration", config_key="timeout", config_value=9999
        )
        assert exc.context["config_key"] == "timeout"
        assert exc.context["config_value"] == 9999


class TestValidationError:
    """Test ValidationError exception."""

    def test_validation_error_basic(self) -> None:
        """Test ValidationError with basic message."""
        exc = ValidationError("Validation failed")
        assert exc.message == "Validation failed"

    def test_validation_error_with_type_and_value(self) -> None:
        """Test ValidationError with validation type and invalid value."""
        exc = ValidationError(
            "Validation failed", validation_type="range", invalid_value=-1
        )
        assert exc.context["validation_type"] == "range"
        assert exc.context["invalid_value"] == -1


class TestSecurityExceptions:
    """Test security-related exceptions."""

    def test_security_error_basic(self) -> None:
        """Test SecurityError with basic message."""
        exc = SecurityError("Security violation")
        assert exc.message == "Security violation"

    def test_security_error_with_type(self) -> None:
        """Test SecurityError with security type."""
        exc = SecurityError("Security violation", security_type="path_traversal")
        assert exc.context["security_type"] == "path_traversal"
        assert exc.security_type == "path_traversal"

    def test_path_traversal_error(self) -> None:
        """Test PathTraversalError exception."""
        exc = PathTraversalError("Path traversal detected", attempted_path="../etc/passwd")
        assert exc.security_type == "path_traversal"
        assert exc.attempted_path == "../etc/passwd"
        assert exc.context["attempted_path"] == "../etc/passwd"

    def test_regex_security_error(self) -> None:
        """Test RegexSecurityError exception."""
        exc = RegexSecurityError(
            "Unsafe regex",
            pattern="(a+)+",
            dangerous_construct="nested quantifiers",
        )
        assert exc.security_type == "regex_security"
        assert exc.pattern == "(a+)+"
        assert exc.dangerous_construct == "nested quantifiers"

    def test_file_restriction_error(self) -> None:
        """Test FileRestrictionError exception."""
        exc = FileRestrictionError(
            "File access restricted",
            file_path="/restricted/file.txt",
            current_mode="read-only",
            allowed_patterns=["*.py", "*.txt"],
        )
        assert exc.security_type == "file_restriction"
        assert exc.current_mode == "read-only"
        assert exc.allowed_patterns == ["*.py", "*.txt"]


class TestMCPExceptions:
    """Test MCP-related exceptions."""

    def test_mcp_error_basic(self) -> None:
        """Test MCPError with basic message."""
        exc = MCPError("MCP operation failed")
        assert exc.message == "MCP operation failed"

    def test_mcp_error_with_tool_name(self) -> None:
        """Test MCPError with tool name."""
        exc = MCPError("MCP operation failed", tool_name="analyze_code")
        assert exc.context["tool_name"] == "analyze_code"

    def test_mcp_tool_error(self) -> None:
        """Test MCPToolError exception."""
        exc = MCPToolError(
            "Tool execution failed",
            tool_name="query_code",
            input_params={"file": "test.py", "query": "functions"},
            execution_stage="parsing",
        )
        assert exc.tool_name == "query_code"
        assert exc.execution_stage == "parsing"
        assert "input_params" in exc.context

    def test_mcp_tool_error_sanitizes_sensitive_params(self) -> None:
        """Test MCPToolError sanitizes sensitive parameters."""
        exc = MCPToolError(
            "Tool failed",
            input_params={"password": "secret123", "file": "test.py"},
        )
        assert exc.context["input_params"]["password"] == "***REDACTED***"
        assert exc.context["input_params"]["file"] == "test.py"

    def test_mcp_tool_error_truncates_long_values(self) -> None:
        """Test MCPToolError truncates long parameter values."""
        long_value = "x" * 200
        exc = MCPToolError(
            "Tool failed",
            input_params={"data": long_value},
        )
        assert "[TRUNCATED]" in exc.context["input_params"]["data"]

    def test_mcp_resource_error(self) -> None:
        """Test MCPResourceError exception."""
        exc = MCPResourceError(
            "Resource not found",
            resource_uri="file:///test.py",
            resource_type="file",
            access_mode="read",
        )
        assert exc.resource_uri == "file:///test.py"
        assert exc.resource_type == "file"
        assert exc.access_mode == "read"

    def test_mcp_timeout_error(self) -> None:
        """Test MCPTimeoutError exception."""
        exc = MCPTimeoutError(
            "Operation timed out",
            timeout_seconds=30.0,
            operation_type="file_analysis",
        )
        assert exc.timeout_seconds == 30.0
        assert exc.operation_type == "file_analysis"

    def test_mcp_validation_error(self) -> None:
        """Test MCPValidationError exception."""
        exc = MCPValidationError(
            "Invalid parameter",
            tool_name="analyze",
            parameter_name="max_depth",
            parameter_value=-1,
            validation_rule="must be positive",
        )
        assert exc.tool_name == "analyze"
        assert exc.parameter_name == "max_depth"
        assert exc.validation_rule == "must be positive"

    def test_mcp_validation_error_truncates_long_values(self) -> None:
        """Test MCPValidationError truncates long parameter values."""
        long_value = "x" * 300
        exc = MCPValidationError(
            "Invalid parameter",
            parameter_name="content",
            parameter_value=long_value,
        )
        assert "[TRUNCATED]" in exc.context["parameter_value"]


class TestExceptionHandlingUtilities:
    """Test exception handling utility functions."""

    def test_create_error_response_basic(self) -> None:
        """Test create_error_response with basic exception."""
        exc = TreeSitterAnalyzerError("Test error")
        response = create_error_response(exc)

        assert response["success"] is False
        assert response["error"]["type"] == "TreeSitterAnalyzerError"
        assert response["error"]["message"] == "Test error"

    def test_create_error_response_with_context(self) -> None:
        """Test create_error_response includes context."""
        exc = TreeSitterAnalyzerError("Test error", context={"key": "value"})
        response = create_error_response(exc)

        assert response["error"]["context"] == {"key": "value"}

    def test_create_error_response_with_traceback(self) -> None:
        """Test create_error_response with traceback."""
        exc = TreeSitterAnalyzerError("Test error")
        response = create_error_response(exc, include_traceback=True)

        assert "traceback" in response["error"]

    def test_safe_execute_success(self) -> None:
        """Test safe_execute with successful execution."""

        def success_func() -> str:
            return "success"

        result = safe_execute(success_func, default_return="failed")
        assert result == "success"

    def test_safe_execute_with_exception(self) -> None:
        """Test safe_execute returns default on exception."""

        def failing_func() -> None:
            raise ValueError("Test error")

        result = safe_execute(failing_func, default_return="default")
        assert result == "default"

    def test_safe_execute_with_specific_exception_types(self) -> None:
        """Test safe_execute catches specific exception types."""

        def failing_func() -> None:
            raise ValueError("Test error")

        # Should catch ValueError
        result = safe_execute(
            failing_func, default_return="caught", exception_types=(ValueError,)
        )
        assert result == "caught"

        # Should not catch KeyError
        with pytest.raises(ValueError):
            safe_execute(
                failing_func, default_return="caught", exception_types=(KeyError,)
            )

    def test_handle_exceptions_decorator(self) -> None:
        """Test handle_exceptions decorator."""

        @handle_exceptions(default_return="error", log_errors=False)
        def failing_function() -> None:
            raise ValueError("Test error")

        result = failing_function()
        assert result == "error"

    def test_handle_exceptions_decorator_reraise(self) -> None:
        """Test handle_exceptions decorator with reraise_as."""

        @handle_exceptions(reraise_as=AnalysisError, log_errors=False)
        def failing_function() -> None:
            raise ValueError("Test error")

        with pytest.raises(AnalysisError):
            failing_function()


class TestMCPErrorResponse:
    """Test MCP-specific error response utilities."""

    def test_create_mcp_error_response_basic(self) -> None:
        """Test create_mcp_error_response with basic exception."""
        exc = MCPError("MCP failed")
        response = create_mcp_error_response(exc)

        assert response["success"] is False
        assert response["error"]["type"] == "MCPError"
        assert response["error"]["message"] == "MCP failed"
        assert "timestamp" in response["error"]

    def test_create_mcp_error_response_with_tool_name(self) -> None:
        """Test create_mcp_error_response includes tool name."""
        exc = MCPError("Tool failed")
        response = create_mcp_error_response(exc, tool_name="analyze_code")

        assert response["error"]["tool"] == "analyze_code"

    def test_create_mcp_error_response_sanitizes_sensitive_data(self) -> None:
        """Test create_mcp_error_response sanitizes sensitive information."""
        exc = MCPError(
            "Failed",
            context={"password": "secret", "token": "abc123", "file": "test.py"},
        )
        response = create_mcp_error_response(exc, sanitize_sensitive=True)

        assert response["error"]["context"]["password"] == "***REDACTED***"
        assert response["error"]["context"]["token"] == "***REDACTED***"
        assert response["error"]["context"]["file"] == "test.py"

    def test_create_mcp_error_response_with_debug_info(self) -> None:
        """Test create_mcp_error_response includes debug information."""
        exc = MCPError("Failed")
        response = create_mcp_error_response(exc, include_debug_info=True)

        assert "debug" in response["error"]
        assert "traceback" in response["error"]["debug"]

    def test_create_mcp_error_response_specific_types(self) -> None:
        """Test create_mcp_error_response with specific exception types."""
        # MCPToolError
        exc1 = MCPToolError("Failed", execution_stage="validation")
        response1 = create_mcp_error_response(exc1)
        assert response1["error"]["execution_stage"] == "validation"

        # MCPTimeoutError
        exc2 = MCPTimeoutError("Timed out", timeout_seconds=60.0)
        response2 = create_mcp_error_response(exc2)
        assert response2["error"]["timeout_seconds"] == 60.0

        # FileRestrictionError
        exc3 = FileRestrictionError("Restricted", current_mode="read-only")
        response3 = create_mcp_error_response(exc3)
        assert response3["error"]["current_mode"] == "read-only"


class TestAsyncExceptionHandling:
    """Test async exception handling utilities."""

    @pytest.mark.asyncio
    async def test_safe_execute_async_success(self) -> None:
        """Test safe_execute_async with successful execution."""

        async def success_coro() -> str:
            return "success"

        result = await safe_execute_async(success_coro(), default_return="failed")
        assert result == "success"

    @pytest.mark.asyncio
    async def test_safe_execute_async_with_exception(self) -> None:
        """Test safe_execute_async returns default on exception."""

        async def failing_coro() -> None:
            raise ValueError("Test error")

        result = await safe_execute_async(
            failing_coro(), default_return="default", log_errors=False
        )
        assert result == "default"

    @pytest.mark.asyncio
    async def test_mcp_exception_handler_decorator_async(self) -> None:
        """Test mcp_exception_handler decorator with async function."""

        @mcp_exception_handler(tool_name="test_tool", include_debug=False)
        async def failing_async_tool() -> None:
            raise ValueError("Async tool failed")

        response = await failing_async_tool()

        assert response["success"] is False
        assert response["error"]["tool"] == "test_tool"
        assert "ValueError" in response["error"]["type"]

    def test_mcp_exception_handler_decorator_sync(self) -> None:
        """Test mcp_exception_handler decorator with sync function."""

        @mcp_exception_handler(tool_name="test_tool", include_debug=False)
        def failing_sync_tool() -> None:
            raise ValueError("Sync tool failed")

        response = failing_sync_tool()

        assert response["success"] is False
        assert response["error"]["tool"] == "test_tool"
        assert "ValueError" in response["error"]["type"]


class TestExceptionInheritance:
    """Test exception inheritance chain."""

    def test_all_exceptions_inherit_from_base(self) -> None:
        """Test that all custom exceptions inherit from TreeSitterAnalyzerError."""
        exception_classes = [
            AnalysisError,
            ParseError,
            LanguageNotSupportedError,
            PluginError,
            QueryError,
            FileHandlingError,
            ConfigurationError,
            ValidationError,
            MCPError,
            SecurityError,
            PathTraversalError,
            RegexSecurityError,
            MCPToolError,
            MCPResourceError,
            MCPTimeoutError,
            MCPValidationError,
            FileRestrictionError,
        ]

        for exc_class in exception_classes:
            assert issubclass(exc_class, TreeSitterAnalyzerError)

    def test_security_exceptions_inheritance(self) -> None:
        """Test security exception inheritance chain."""
        assert issubclass(PathTraversalError, SecurityError)
        assert issubclass(RegexSecurityError, SecurityError)
        assert issubclass(FileRestrictionError, SecurityError)

    def test_mcp_exceptions_inheritance(self) -> None:
        """Test MCP exception inheritance chain."""
        assert issubclass(MCPToolError, MCPError)
        assert issubclass(MCPResourceError, MCPError)
        assert issubclass(MCPTimeoutError, MCPError)
        assert issubclass(MCPValidationError, ValidationError)
