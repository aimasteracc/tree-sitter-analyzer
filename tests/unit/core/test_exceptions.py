#!/usr/bin/env python3
"""
Standardized tests for tree_sitter_analyzer.exceptions module.
Consolidated from redundant 'comprehensive' and 'extended' suites.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.exceptions import (
    AnalysisError,
    MCPError,
    MCPToolError,
    MCPValidationError,
    PathTraversalError,
    RegexSecurityError,
    SecurityError,
    TreeSitterAnalyzerError,
    ValidationError,
    _sanitize_error_context,
    create_mcp_error_response,
    handle_exceptions,
    mcp_exception_handler,
    safe_execute,
    safe_execute_async,
)


class TestExceptionCore:
    """Test base exception hierarchy and serialization."""

    def test_base_exception_creation(self) -> None:
        error = TreeSitterAnalyzerError(
            "Test error", error_code="CUSTOM_001", context={"k": "v"}
        )
        assert str(error) == "Test error"
        assert error.error_code == "CUSTOM_001"
        assert error.context == {"k": "v"}

        d = error.to_dict()
        assert d["error_type"] == "TreeSitterAnalyzerError"
        assert d["error_code"] == "CUSTOM_001"

    def test_inheritance_chain(self) -> None:
        assert issubclass(AnalysisError, TreeSitterAnalyzerError)
        assert issubclass(SecurityError, TreeSitterAnalyzerError)
        assert issubclass(PathTraversalError, SecurityError)
        assert issubclass(MCPToolError, MCPError)
        assert issubclass(MCPValidationError, ValidationError)

    def test_analysis_error_params(self) -> None:
        exc = AnalysisError("failed", file_path=Path("test.py"), language="python")
        assert exc.context["file_path"] == "test.py"
        assert exc.context["language"] == "python"


class TestSecurityExceptions:
    """Test security-specific exception attributes."""

    def test_path_traversal(self) -> None:
        exc = PathTraversalError("traversal", attempted_path="../secret")
        assert exc.attempted_path == "../secret"
        assert exc.security_type == "path_traversal"

    def test_regex_security(self) -> None:
        exc = RegexSecurityError(
            "unsafe", pattern=".*", dangerous_construct="backtracking"
        )
        assert exc.pattern == ".*"
        assert exc.dangerous_construct == "backtracking"


class TestMCPExceptions:
    """Test MCP-specific error handling and sanitization."""

    def test_mcp_tool_error_sanitization(self) -> None:
        params = {
            "password": "secret",  # pragma: allowlist secret
            "file": "safe.py",
            "long": "x" * 1000,
        }
        exc = MCPToolError("failed", tool_name="tool", input_params=params)

        assert exc.context["input_params"]["password"] == "***REDACTED***"
        assert "[TRUNCATED]" in exc.context["input_params"]["long"]
        assert exc.context["input_params"]["file"] == "safe.py"

    def test_mcp_error_response(self) -> None:
        exc = MCPError(
            "failed", context={"token": "secret"}
        )  # pragma: allowlist secret
        resp = create_mcp_error_response(exc, tool_name="test", sanitize_sensitive=True)
        assert resp["success"] is False
        assert resp["error"]["tool"] == "test"
        assert resp["error"]["context"]["token"] == "***REDACTED***"


class TestUtilities:
    """Test functional utilities like safe_execute and decorators."""

    def test_safe_execute_sync(self) -> None:
        assert safe_execute(lambda x: x + 1, 1) == 2
        assert safe_execute(lambda: 1 / 0, default_return=0) == 0

    @pytest.mark.asyncio
    async def test_safe_execute_async(self) -> None:
        async def work():
            return "ok"

        async def fail():
            raise ValueError()

        assert await safe_execute_async(work()) == "ok"
        assert (
            await safe_execute_async(fail(), default_return="err", log_errors=False)
            == "err"
        )

    def test_handle_exceptions_decorator(self) -> None:
        @handle_exceptions(default_return="fallback", log_errors=False)
        def broken():
            raise RuntimeError()

        assert broken() == "fallback"

    @pytest.mark.asyncio
    async def test_mcp_exception_handler_async(self) -> None:
        @mcp_exception_handler("test_tool", include_debug=False)
        async def failing_tool():
            raise ValueError("oops")

        resp = await failing_tool()
        assert resp["success"] is False
        assert resp["error"]["tool"] == "test_tool"


class TestSanitization:
    """Test internal context sanitization logic."""

    def test_sanitize_logic(self) -> None:
        ctx = {
            "api_key": "secret",  # pragma: allowlist secret
            "list": list(range(100)),
            "nested": {"password": "123", "normal": "val"},  # pragma: allowlist secret
        }
        res = _sanitize_error_context(ctx)
        assert res["api_key"] == "***REDACTED***"
        assert res["list"][-1] == "...[TRUNCATED]"
        assert res["nested"]["password"] == "***REDACTED***"
        assert res["nested"]["normal"] == "val"
