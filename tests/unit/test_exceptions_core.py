"""Unit tests for _exceptions_core — exception hierarchy and context propagation."""

import pytest

from tree_sitter_analyzer.exceptions.core import (
    AnalysisError,
    ConfigurationError,
    FileHandlingError,
    LanguageNotSupportedError,
    MCPError,
    ParseError,
    PluginError,
    QueryError,
    TreeSitterAnalyzerError,
    ValidationError,
)


class TestTreeSitterAnalyzerError:
    """Tests for the base exception class."""

    def test_message_and_error_code(self):
        exc = TreeSitterAnalyzerError("test error")
        assert str(exc) == "test error"
        assert exc.message == "test error"
        assert exc.error_code == "TreeSitterAnalyzerError"

    def test_custom_error_code(self):
        exc = TreeSitterAnalyzerError("msg", error_code="CUSTOM_001")
        assert exc.error_code == "CUSTOM_001"

    def test_default_context_is_empty(self):
        exc = TreeSitterAnalyzerError("msg")
        assert exc.context == {}

    def test_custom_context(self):
        exc = TreeSitterAnalyzerError("msg", context={"key": "value"})
        assert exc.context == {"key": "value"}

    def test_to_dict(self):
        exc = TreeSitterAnalyzerError("msg", error_code="E1", context={"k": "v"})
        d = exc.to_dict()
        assert d["error_type"] == "TreeSitterAnalyzerError"
        assert d["error_code"] == "E1"
        assert d["message"] == "msg"
        assert d["context"] == {"k": "v"}

    def test_is_catchable_as_exception(self):
        with pytest.raises(TreeSitterAnalyzerError) as exc_info:
            raise TreeSitterAnalyzerError("boom")
        assert exc_info.value.message == "boom"


class TestAnalysisError:
    """Tests for AnalysisError."""

    def test_with_file_path_and_language(self):
        exc = AnalysisError("parse failed", file_path="/test.py", language="python")
        assert exc.context["file_path"] == "/test.py"
        assert exc.context["language"] == "python"

    def test_without_optional_fields(self):
        exc = AnalysisError("generic error")
        assert "file_path" not in exc.context
        assert "language" not in exc.context


class TestParseError:
    """Tests for ParseError."""

    def test_with_source_info(self):
        exc = ParseError("bad syntax", language="java", source_info={"line": 42})
        assert exc.context["language"] == "java"
        assert exc.context["line"] == 42


class TestLanguageNotSupportedError:
    """Tests for LanguageNotSupportedError."""

    def test_message_includes_language(self):
        exc = LanguageNotSupportedError("brainfuck")
        assert "brainfuck" in str(exc)
        assert exc.context["language"] == "brainfuck"

    def test_message_includes_supported_list(self):
        exc = LanguageNotSupportedError(
            "brainfuck", supported_languages=["python", "java"]
        )
        assert "python" in str(exc)
        assert "java" in str(exc)

    def test_without_supported_list(self):
        exc = LanguageNotSupportedError("cobol")
        assert "Supported languages" not in str(exc)


class TestPluginError:
    """Tests for PluginError."""

    def test_with_plugin_and_operation(self):
        exc = PluginError("load failed", plugin_name="cpp", operation="register")
        assert exc.context["plugin_name"] == "cpp"
        assert exc.context["operation"] == "register"


class TestQueryError:
    """Tests for QueryError."""

    def test_with_query_details(self):
        exc = QueryError(
            "query failed",
            query_name="functions",
            query_string="(function_definition) @fn",
            language="python",
        )
        assert exc.context["query_name"] == "functions"
        assert exc.context["query_string"] == "(function_definition) @fn"


class TestFileHandlingError:
    """Tests for FileHandlingError."""

    def test_with_file_and_operation(self):
        exc = FileHandlingError("read error", file_path="/a.py", operation="read")
        assert exc.context["file_path"] == "/a.py"
        assert exc.context["operation"] == "read"


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_with_config_key_and_value(self):
        exc = ConfigurationError("bad config", config_key="max_depth", config_value=-1)
        assert exc.context["config_key"] == "max_depth"
        assert exc.context["config_value"] == -1

    def test_none_value_not_stored(self):
        exc = ConfigurationError("bad config", config_key="k", config_value=None)
        assert "config_value" not in exc.context


class TestValidationError:
    """Tests for ValidationError."""

    def test_with_validation_type(self):
        exc = ValidationError(
            "invalid", validation_type="path", invalid_value="../../../etc/passwd"
        )
        assert exc.context["validation_type"] == "path"
        assert exc.context["invalid_value"] == "../../../etc/passwd"


class TestMCPError:
    """Tests for MCPError."""

    def test_with_tool_and_resource(self):
        exc = MCPError(
            "tool error", tool_name="analyze", resource_uri="file:///test.py"
        )
        assert exc.context["tool_name"] == "analyze"
        assert exc.context["resource_uri"] == "file:///test.py"


class TestExceptionHierarchy:
    """Tests for exception inheritance."""

    def test_all_inherit_from_base(self):
        for exc_cls in [
            AnalysisError,
            ParseError,
            LanguageNotSupportedError,
            PluginError,
            QueryError,
            FileHandlingError,
            ConfigurationError,
            ValidationError,
            MCPError,
        ]:
            assert issubclass(exc_cls, TreeSitterAnalyzerError)

    def test_all_catchable_as_base(self):
        with pytest.raises(TreeSitterAnalyzerError):
            raise QueryError("test", query_name="q")

    def test_to_dict_includes_concrete_class_name(self):
        exc = QueryError("test")
        assert exc.to_dict()["error_type"] == "QueryError"
