#!/usr/bin/env python3
"""
Extended tests for tree_sitter_analyzer.exceptions module

Tests for handle_exception, safe_execute, create_error_response,
handle_exceptions decorator, and MCP-specific exceptions.
"""

import pytest

from tree_sitter_analyzer.exceptions import (
    AnalysisError,
    FileRestrictionError,
    MCPResourceError,
    MCPTimeoutError,
    MCPToolError,
    MCPValidationError,
    PathTraversalError,
    RegexSecurityError,
    SecurityError,
    TreeSitterAnalyzerError,
    create_error_response,
    create_mcp_error_response,
    handle_exception,
    handle_exceptions,
    mcp_exception_handler,
    safe_execute,
    safe_execute_async,
)


class TestHandleException:
    """Tests for handle_exception utility function"""

    def test_handle_exception_logs_and_reraises(self):
        """Test that handle_exception logs and re-raises the original exception"""
        exception = TreeSitterAnalyzerError("Test error")
        with pytest.raises(TreeSitterAnalyzerError):
            handle_exception(exception)

    def test_handle_exception_with_context(self):
        """Test handle_exception with additional context"""
        exception = TreeSitterAnalyzerError("Test error")
        context = {"key": "value"}
        with pytest.raises(TreeSitterAnalyzerError):
            handle_exception(exception, context=context)

    def test_handle_exception_reraise_as_different_type(self):
        """Test re-raising as different exception type"""
        original = ValueError("Original error")
        # TreeSitterAnalyzerError subclasses have specific signature requirements
        with pytest.raises(TreeSitterAnalyzerError):
            handle_exception(original, reraise_as=TreeSitterAnalyzerError)

    def test_handle_exception_reraise_non_tree_sitter_error(self):
        """Test re-raising as non-TreeSitterAnalyzerError type"""
        original = ValueError("Original error")
        with pytest.raises(RuntimeError):
            handle_exception(original, reraise_as=RuntimeError)

    def test_handle_exception_with_exception_context(self):
        """Test handle_exception when exception has context attribute"""
        exception = AnalysisError("Test", file_path="test.py")
        with pytest.raises(AnalysisError):
            handle_exception(exception, context={"extra": "data"})


class TestSafeExecute:
    """Tests for safe_execute utility function"""

    def test_safe_execute_success(self):
        """Test successful function execution"""
        result = safe_execute(lambda x: x * 2, 5)
        assert result == 10

    def test_safe_execute_with_exception(self):
        """Test safe_execute with exception returns default"""

        def failing_func():
            raise ValueError("Test error")

        result = safe_execute(failing_func, default_return="default")
        assert result == "default"

    def test_safe_execute_specific_exception_types(self):
        """Test safe_execute with specific exception types"""

        def failing_func():
            raise KeyError("Key error")

        result = safe_execute(
            failing_func, default_return="caught", exception_types=(KeyError,)
        )
        assert result == "caught"

    def test_safe_execute_uncaught_exception(self):
        """Test safe_execute doesn't catch non-matching exceptions"""

        def failing_func():
            raise RuntimeError("Runtime error")

        with pytest.raises(RuntimeError):
            safe_execute(
                failing_func, default_return="default", exception_types=(ValueError,)
            )

    def test_safe_execute_with_log_errors_false(self):
        """Test safe_execute with logging disabled"""

        def failing_func():
            raise ValueError("Test error")

        result = safe_execute(failing_func, default_return="default", log_errors=False)
        assert result == "default"

    def test_safe_execute_with_kwargs(self):
        """Test safe_execute with keyword arguments"""

        def func_with_kwargs(a, b, c=3):
            return a + b + c

        result = safe_execute(func_with_kwargs, 1, 2, c=10)
        assert result == 13


class TestCreateErrorResponse:
    """Tests for create_error_response utility function"""

    def test_create_error_response_basic(self):
        """Test basic error response creation"""
        exception = ValueError("Test error")
        response = create_error_response(exception)

        assert response["success"] is False
        assert response["error"]["type"] == "ValueError"
        assert response["error"]["message"] == "Test error"

    def test_create_error_response_with_context(self):
        """Test error response with exception context"""
        exception = AnalysisError("Test", file_path="test.py")
        response = create_error_response(exception)

        assert "context" in response["error"]
        assert response["error"]["context"]["file_path"] == "test.py"

    def test_create_error_response_with_traceback(self):
        """Test error response with traceback"""
        exception = ValueError("Test error")
        response = create_error_response(exception, include_traceback=True)

        assert "traceback" in response["error"]

    def test_create_error_response_with_error_code(self):
        """Test error response with error code"""
        exception = TreeSitterAnalyzerError("Test", error_code="CUSTOM_CODE")
        response = create_error_response(exception)

        assert response["error"]["code"] == "CUSTOM_CODE"


class TestHandleExceptionsDecorator:
    """Tests for handle_exceptions decorator"""

    def test_handle_exceptions_success(self):
        """Test decorator with successful function"""

        @handle_exceptions(default_return="default")
        def successful_func():
            return "success"

        assert successful_func() == "success"

    def test_handle_exceptions_with_exception(self):
        """Test decorator returns default on exception"""

        @handle_exceptions(default_return="default", log_errors=False)
        def failing_func():
            raise ValueError("Error")

        assert failing_func() == "default"

    def test_handle_exceptions_reraise(self):
        """Test decorator re-raises as specified exception"""

        @handle_exceptions(reraise_as=AnalysisError, log_errors=False)
        def failing_func():
            raise ValueError("Error")

        with pytest.raises(AnalysisError):
            failing_func()

    def test_handle_exceptions_reraise_non_tree_sitter(self):
        """Test decorator re-raises as non-TreeSitterAnalyzerError"""

        @handle_exceptions(reraise_as=RuntimeError, log_errors=False)
        def failing_func():
            raise ValueError("Error")

        with pytest.raises(RuntimeError):
            failing_func()

    def test_handle_exceptions_specific_exception_types(self):
        """Test decorator with specific exception types"""

        @handle_exceptions(
            default_return="caught", exception_types=(KeyError,), log_errors=False
        )
        def failing_func():
            raise KeyError("Key error")

        assert failing_func() == "caught"


class TestMCPExceptions:
    """Tests for MCP-specific exception classes"""

    def test_mcp_tool_error_sanitize_params(self):
        """Test MCPToolError parameter sanitization"""
        params = {
            "password": "secret123",  # pragma: allowlist secret
            "normal_param": "value",
            "api_token": "abc123",  # pragma: allowlist secret
            "long_value": "x" * 200,
        }
        error = MCPToolError("Tool failed", tool_name="test_tool", input_params=params)

        assert error.context["input_params"]["password"] == "***REDACTED***"
        assert error.context["input_params"]["normal_param"] == "value"
        assert error.context["input_params"]["api_token"] == "***REDACTED***"
        assert "TRUNCATED" in error.context["input_params"]["long_value"]

    def test_mcp_resource_error(self):
        """Test MCPResourceError creation"""
        error = MCPResourceError(
            "Resource not found",
            resource_uri="code://file/test.py",
            resource_type="file",
            access_mode="read",
        )

        assert error.resource_uri == "code://file/test.py"
        assert error.resource_type == "file"
        assert error.access_mode == "read"
        assert error.context["resource_type"] == "file"

    def test_mcp_timeout_error(self):
        """Test MCPTimeoutError creation"""
        error = MCPTimeoutError(
            "Operation timed out", timeout_seconds=30.0, operation_type="analysis"
        )

        assert error.timeout_seconds == 30.0
        assert error.operation_type == "analysis"
        assert error.context["timeout_seconds"] == 30.0

    def test_mcp_validation_error(self):
        """Test MCPValidationError creation"""
        error = MCPValidationError(
            "Invalid parameter",
            tool_name="analyze_file",
            parameter_name="file_path",
            parameter_value="x" * 300,
            validation_rule="must_exist",
        )

        assert error.tool_name == "analyze_file"
        assert error.parameter_name == "file_path"
        assert "TRUNCATED" in error.context["parameter_value"]

    def test_file_restriction_error(self):
        """Test FileRestrictionError creation"""
        error = FileRestrictionError(
            "Access denied",
            file_path="/etc/passwd",
            current_mode="read-only",
            allowed_patterns=["*.py", "*.txt"],
        )

        assert error.current_mode == "read-only"
        assert error.allowed_patterns == ["*.py", "*.txt"]
        assert error.context["current_mode"] == "read-only"


class TestCreateMCPErrorResponse:
    """Tests for create_mcp_error_response function"""

    def test_create_mcp_error_response_basic(self):
        """Test basic MCP error response"""
        error = MCPToolError("Tool failed", tool_name="test_tool")
        response = create_mcp_error_response(error, tool_name="test_tool")

        assert response["success"] is False
        assert response["error"]["type"] == "MCPToolError"
        assert response["error"]["tool"] == "test_tool"
        assert "timestamp" in response["error"]

    def test_create_mcp_error_response_with_debug(self):
        """Test MCP error response with debug info"""
        error = ValueError("Test error")
        response = create_mcp_error_response(error, include_debug_info=True)

        assert "debug" in response["error"]
        assert "traceback" in response["error"]["debug"]

    def test_create_mcp_error_response_with_timeout(self):
        """Test MCP error response for timeout error"""
        error = MCPTimeoutError("Timed out", timeout_seconds=30.0)
        response = create_mcp_error_response(error)

        assert response["error"]["timeout_seconds"] == 30.0

    def test_create_mcp_error_response_with_file_restriction(self):
        """Test MCP error response for file restriction error"""
        error = FileRestrictionError(
            "Denied", current_mode="read-only", allowed_patterns=["*.py"]
        )
        response = create_mcp_error_response(error)

        assert response["error"]["current_mode"] == "read-only"
        assert response["error"]["allowed_patterns"] == ["*.py"]

    def test_create_mcp_error_response_sanitization(self):
        """Test MCP error response context sanitization"""
        error = MCPToolError(
            "Failed",
            tool_name="test",
            input_params={"api_key": "secret123", "normal": "value"},
        )
        response = create_mcp_error_response(error, sanitize_sensitive=True)

        context = response["error"]["context"]
        assert context["input_params"]["api_key"] == "***REDACTED***"
        assert context["input_params"]["normal"] == "value"


class TestSafeExecuteAsync:
    """Tests for safe_execute_async function"""

    @pytest.mark.asyncio
    async def test_safe_execute_async_success(self):
        """Test successful async execution"""

        async def async_func():
            return "success"

        result = await safe_execute_async(async_func())
        assert result == "success"

    @pytest.mark.asyncio
    async def test_safe_execute_async_with_exception(self):
        """Test async execution with exception returns default"""

        async def failing_async():
            raise ValueError("Error")

        result = await safe_execute_async(
            failing_async(), default_return="default", log_errors=False
        )
        assert result == "default"

    @pytest.mark.asyncio
    async def test_safe_execute_async_with_tool_name(self):
        """Test async execution with tool name context"""

        async def failing_async():
            raise ValueError("Error")

        result = await safe_execute_async(
            failing_async(), default_return="default", tool_name="test_tool"
        )
        assert result == "default"


class TestMCPExceptionHandler:
    """Tests for mcp_exception_handler decorator"""

    @pytest.mark.asyncio
    async def test_mcp_exception_handler_async_success(self):
        """Test decorator with successful async function"""

        @mcp_exception_handler("test_tool")
        async def async_func():
            return "success"

        result = await async_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_mcp_exception_handler_async_failure(self):
        """Test decorator with failing async function"""

        @mcp_exception_handler("test_tool", include_debug=False)
        async def failing_async():
            raise ValueError("Error")

        result = await failing_async()
        assert result["success"] is False
        assert result["error"]["tool"] == "test_tool"

    def test_mcp_exception_handler_sync_success(self):
        """Test decorator with successful sync function"""

        @mcp_exception_handler("test_tool")
        def sync_func():
            return "success"

        result = sync_func()
        assert result == "success"

    def test_mcp_exception_handler_sync_failure(self):
        """Test decorator with failing sync function"""

        @mcp_exception_handler("test_tool", include_debug=False)
        def failing_sync():
            raise ValueError("Error")

        result = failing_sync()
        assert result["success"] is False
        assert result["error"]["tool"] == "test_tool"


class TestSecurityExceptions:
    """Tests for security exception classes"""

    def test_security_error_with_type_and_path(self):
        """Test SecurityError with all parameters"""
        error = SecurityError(
            "Access denied", security_type="path_traversal", file_path="/etc/passwd"
        )

        assert error.security_type == "path_traversal"
        assert error.file_path == "/etc/passwd"

    def test_path_traversal_error(self):
        """Test PathTraversalError"""
        error = PathTraversalError(
            "Path traversal detected", attempted_path="../../../etc/passwd"
        )

        assert error.attempted_path == "../../../etc/passwd"
        assert error.context["attempted_path"] == "../../../etc/passwd"

    def test_regex_security_error(self):
        """Test RegexSecurityError"""
        error = RegexSecurityError(
            "Dangerous regex pattern",
            pattern="(a+)+",
            dangerous_construct="catastrophic backtracking",
        )

        assert error.pattern == "(a+)+"
        assert error.dangerous_construct == "catastrophic backtracking"
