"""Unit tests for _exceptions_mcp_types — MCP exception hierarchy."""

import pytest

from tree_sitter_analyzer.exceptions.core import (
    MCPError,
    TreeSitterAnalyzerError,
    ValidationError,
)
from tree_sitter_analyzer.exceptions.mcp_types import (
    MCPResourceError,
    MCPTimeoutError,
    MCPToolError,
    MCPValidationError,
)

# ---------------------------------------------------------------------------
# MCPToolError
# ---------------------------------------------------------------------------


class TestMCPToolError:
    """Tests for MCPToolError construction and attribute storage."""

    def test_basic_message(self):
        exc = MCPToolError("tool failed")
        assert str(exc) == "tool failed"

    def test_tool_name_stored(self):
        exc = MCPToolError("failed", tool_name="analyze_code")
        assert exc.tool_name == "analyze_code"
        assert exc.context.get("tool_name") == "analyze_code"

    def test_execution_stage_stored(self):
        exc = MCPToolError("failed", execution_stage="validation")
        assert exc.execution_stage == "validation"
        assert exc.context["execution_stage"] == "validation"

    def test_input_params_stored_and_sanitized(self):
        params = {"path": "/some/file.py", "token": "secret-value"}
        exc = MCPToolError("failed", input_params=params)
        assert exc.input_params == params
        sanitized = exc.context["input_params"]
        # Sensitive key must be redacted
        assert sanitized["token"] == "***REDACTED***"
        # Non-sensitive key should be preserved
        assert sanitized["path"] == "/some/file.py"

    def test_sensitive_keys_redacted(self):
        sensitive_keys = [
            "password",
            "key",
            "secret",
            "auth",
            "api_key",
            "access_token",
        ]
        for key in sensitive_keys:
            exc = MCPToolError("x", input_params={key: "my-value"})
            assert exc.context["input_params"][key] == "***REDACTED***", (
                f"Key {key!r} should be redacted"
            )

    def test_long_param_value_truncated(self):
        long_val = "x" * 200
        exc = MCPToolError("x", input_params={"big": long_val})
        stored = exc.context["input_params"]["big"]
        assert len(stored) < len(long_val)
        assert "TRUNCATED" in stored

    def test_without_optional_fields(self):
        exc = MCPToolError("bare error")
        assert exc.tool_name is None
        assert exc.input_params is None
        assert exc.execution_stage is None

    def test_inherits_from_mcp_error(self):
        exc = MCPToolError("msg")
        assert isinstance(exc, MCPError)

    def test_inherits_from_tree_sitter_error(self):
        exc = MCPToolError("msg")
        assert isinstance(exc, TreeSitterAnalyzerError)

    def test_to_dict_includes_context(self):
        exc = MCPToolError("fail", tool_name="my_tool", execution_stage="run")
        d = exc.to_dict()
        assert d["context"]["tool_name"] == "my_tool"
        assert d["context"]["execution_stage"] == "run"

    def test_empty_input_params_not_added_to_context(self):
        exc = MCPToolError("msg", input_params={})
        # Empty dict is falsy — should NOT appear in context
        assert "input_params" not in exc.context

    def test_extra_kwargs_forwarded(self):
        exc = MCPToolError("msg", tool_name="t", context={"extra": "data"})
        assert exc.context["extra"] == "data"
        assert exc.context["tool_name"] == "t"


# ---------------------------------------------------------------------------
# MCPResourceError
# ---------------------------------------------------------------------------


class TestMCPResourceError:
    """Tests for MCPResourceError construction and attribute storage."""

    def test_basic_message(self):
        exc = MCPResourceError("resource unavailable")
        assert str(exc) == "resource unavailable"

    def test_resource_uri_stored(self):
        exc = MCPResourceError("fail", resource_uri="file:///x.py")
        assert exc.resource_uri == "file:///x.py"

    def test_resource_type_in_context(self):
        exc = MCPResourceError("fail", resource_type="file")
        assert exc.resource_type == "file"
        assert exc.context["resource_type"] == "file"

    def test_access_mode_in_context(self):
        exc = MCPResourceError("fail", access_mode="read")
        assert exc.access_mode == "read"
        assert exc.context["access_mode"] == "read"

    def test_without_optional_fields(self):
        exc = MCPResourceError("msg")
        assert exc.resource_uri is None
        assert exc.resource_type is None
        assert exc.access_mode is None

    def test_inherits_from_mcp_error(self):
        exc = MCPResourceError("msg")
        assert isinstance(exc, MCPError)

    def test_inherits_from_tree_sitter_error(self):
        exc = MCPResourceError("msg")
        assert isinstance(exc, TreeSitterAnalyzerError)

    def test_resource_type_none_not_in_context(self):
        exc = MCPResourceError("msg", resource_type=None)
        assert "resource_type" not in exc.context

    def test_all_fields_populated(self):
        exc = MCPResourceError(
            "access denied",
            resource_uri="file:///a.py",
            resource_type="file",
            access_mode="write",
        )
        assert exc.resource_uri == "file:///a.py"
        assert exc.resource_type == "file"
        assert exc.access_mode == "write"
        assert exc.context["resource_type"] == "file"
        assert exc.context["access_mode"] == "write"


# ---------------------------------------------------------------------------
# MCPTimeoutError
# ---------------------------------------------------------------------------


class TestMCPTimeoutError:
    """Tests for MCPTimeoutError construction."""

    def test_basic_message(self):
        exc = MCPTimeoutError("timed out")
        assert str(exc) == "timed out"

    def test_timeout_seconds_stored(self):
        exc = MCPTimeoutError("slow", timeout_seconds=30.0)
        assert exc.timeout_seconds == 30.0
        assert exc.context["timeout_seconds"] == 30.0

    def test_operation_type_stored(self):
        exc = MCPTimeoutError("slow", operation_type="index")
        assert exc.operation_type == "index"
        assert exc.context["operation_type"] == "index"

    def test_without_optional_fields(self):
        exc = MCPTimeoutError("msg")
        assert exc.timeout_seconds is None
        assert exc.operation_type is None

    def test_inherits_from_mcp_error(self):
        exc = MCPTimeoutError("msg")
        assert isinstance(exc, MCPError)


# ---------------------------------------------------------------------------
# MCPValidationError
# ---------------------------------------------------------------------------


class TestMCPValidationError:
    """Tests for MCPValidationError construction."""

    def test_basic_message(self):
        exc = MCPValidationError("bad input")
        assert str(exc) == "bad input"

    def test_tool_name_in_context(self):
        exc = MCPValidationError("bad", tool_name="run_analysis")
        assert exc.tool_name == "run_analysis"
        assert exc.context["tool_name"] == "run_analysis"

    def test_parameter_name_in_context(self):
        exc = MCPValidationError("bad", parameter_name="depth")
        assert exc.parameter_name == "depth"
        assert exc.context["parameter_name"] == "depth"

    def test_validation_rule_in_context(self):
        exc = MCPValidationError("bad", validation_rule="must_be_positive")
        assert exc.validation_rule == "must_be_positive"
        assert exc.context["validation_rule"] == "must_be_positive"

    def test_parameter_value_in_context(self):
        exc = MCPValidationError("bad", parameter_value=42)
        assert exc.context["parameter_value"] == 42

    def test_long_parameter_value_truncated(self):
        long_val = "y" * 300
        exc = MCPValidationError("bad", parameter_value=long_val)
        stored = exc.context["parameter_value"]
        assert "TRUNCATED" in stored

    def test_none_parameter_value_not_in_context(self):
        exc = MCPValidationError("bad", parameter_value=None)
        assert "parameter_value" not in exc.context

    def test_inherits_from_validation_error(self):
        exc = MCPValidationError("bad")
        assert isinstance(exc, ValidationError)

    def test_inherits_from_tree_sitter_error(self):
        exc = MCPValidationError("bad")
        assert isinstance(exc, TreeSitterAnalyzerError)

    def test_validation_type_is_mcp_parameter(self):
        exc = MCPValidationError("bad")
        assert exc.context.get("validation_type") == "mcp_parameter"

    def test_without_optional_fields(self):
        exc = MCPValidationError("bare")
        assert exc.tool_name is None
        assert exc.parameter_name is None
        assert exc.validation_rule is None


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """All MCP exception types live in the correct hierarchy."""

    def test_mcp_tool_error_is_exception(self):
        exc = MCPToolError("msg")
        assert isinstance(exc, Exception)

    def test_mcp_resource_error_is_exception(self):
        exc = MCPResourceError("msg")
        assert isinstance(exc, Exception)

    def test_mcp_timeout_error_is_exception(self):
        exc = MCPTimeoutError("msg")
        assert isinstance(exc, Exception)

    def test_mcp_validation_error_is_exception(self):
        exc = MCPValidationError("msg")
        assert isinstance(exc, Exception)

    def test_mcp_tool_error_can_be_caught_as_mcp_error(self):
        with pytest.raises(MCPError):
            raise MCPToolError("boom")

    def test_mcp_resource_error_can_be_caught_as_mcp_error(self):
        with pytest.raises(MCPError):
            raise MCPResourceError("boom")

    def test_mcp_validation_error_can_be_caught_as_validation_error(self):
        with pytest.raises(ValidationError):
            raise MCPValidationError("boom")
