#!/usr/bin/env python3
"""
Unit tests for AnalyzeCodeStructureTool.

Tests for analyze_code_structure tool which provides code structure
analysis with detailed overview tables (classes, methods, fields).
"""

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)


@pytest.fixture
def tool():
    """Create an AnalyzeCodeStructureTool instance for testing."""
    return AnalyzeCodeStructureTool()


@pytest.fixture
def tool_with_project_root():
    """Create an AnalyzeCodeStructureTool instance with a project root."""
    return AnalyzeCodeStructureTool(project_root="/test/project")


class TestAnalyzeCodeStructureToolInit:
    """Tests for AnalyzeCodeStructureTool initialization."""

    def test_init_without_project_root(self, tool):
        """Test initialization without project root."""
        assert tool is not None
        assert tool.project_root is None
        assert tool.analysis_engine is not None
        assert tool.file_output_manager is not None

    def test_init_with_project_root(self, tool_with_project_root):
        """Test initialization with project root."""
        assert tool_with_project_root is not None
        assert tool_with_project_root.project_root == "/test/project"
        assert tool_with_project_root.analysis_engine is not None
        assert tool_with_project_root.file_output_manager is not None


class TestAnalyzeCodeStructureToolSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path_updates_analysis_engine(self, tool):
        """Test that setting project path updates analysis engine."""
        tool.set_project_path("/new/project")
        # Both the project root and the analysis engine must reflect the new path
        assert tool.project_root == "/new/project"
        assert tool.analysis_engine is not None


class TestAnalyzeCodeStructureToolGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_get_tool_definition_name(self, tool):
        """Test tool definition has correct name."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "analyze_code_structure"

    def test_get_tool_definition_has_description(self, tool):
        """Test tool definition has description."""
        definition = tool.get_tool_definition()
        assert "description" in definition
        assert isinstance(definition["description"], str)
        assert len(definition["description"]) > 0

    def test_get_tool_definition_has_input_schema(self, tool):
        """Test tool definition has input schema."""
        definition = tool.get_tool_definition()
        assert "inputSchema" in definition
        assert isinstance(definition["inputSchema"], dict)

    def test_get_tool_definition_schema_has_file_path(self, tool):
        """Test schema has file_path property."""
        schema = tool.get_tool_definition()["inputSchema"]
        assert "file_path" in schema["properties"]
        assert schema["properties"]["file_path"]["type"] == "string"

    def test_get_tool_definition_schema_has_format_type(self, tool):
        """Test schema has format_type property."""
        schema = tool.get_tool_definition()["inputSchema"]
        assert "format_type" in schema["properties"]
        assert schema["properties"]["format_type"]["type"] == "string"
        assert set(schema["properties"]["format_type"]["enum"]) == {
            "full",
            "compact",
            "csv",
        }

    def test_get_tool_definition_schema_has_language(self, tool):
        """Test schema has language property."""
        schema = tool.get_tool_definition()["inputSchema"]
        assert "language" in schema["properties"]
        assert schema["properties"]["language"]["type"] == "string"

    def test_get_tool_definition_schema_has_output_file(self, tool):
        """Test schema has output_file property."""
        schema = tool.get_tool_definition()["inputSchema"]
        assert "output_file" in schema["properties"]
        assert schema["properties"]["output_file"]["type"] == "string"

    def test_get_tool_definition_schema_has_suppress_output(self, tool):
        """Test schema has suppress_output property."""
        schema = tool.get_tool_definition()["inputSchema"]
        assert "suppress_output" in schema["properties"]
        assert schema["properties"]["suppress_output"]["type"] == "boolean"

    def test_get_tool_definition_schema_has_output_format(self, tool):
        """Test schema has output_format property."""
        schema = tool.get_tool_definition()["inputSchema"]
        assert "output_format" in schema["properties"]
        assert schema["properties"]["output_format"]["type"] == "string"
        assert set(schema["properties"]["output_format"]["enum"]) == {"json", "toon"}


class TestAnalyzeCodeStructureToolValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_arguments_valid_basic(self, tool):
        """Test validation with valid basic arguments."""
        arguments = {"file_path": "test.py"}
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_with_format_type(self, tool):
        """Test validation with format_type specified."""
        arguments = {"file_path": "test.py", "format_type": "full"}
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_with_language(self, tool):
        """Test validation with language specified."""
        arguments = {"file_path": "test.py", "language": "python"}
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_with_output_file(self, tool):
        """Test validation with output_file specified."""
        arguments = {"file_path": "test.py", "output_file": "output.txt"}
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_with_suppress_output(self, tool):
        """Test validation with suppress_output specified."""
        arguments = {"file_path": "test.py", "suppress_output": True}
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_missing_file_path(self, tool):
        """Test validation fails when file_path is missing."""
        arguments = {}
        with pytest.raises(ValueError, match="Required field 'file_path' is missing"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_file_path_type(self, tool):
        """Test validation fails when file_path is not a string."""
        arguments = {"file_path": 123}
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_empty_file_path(self, tool):
        """Test validation fails when file_path is empty."""
        arguments = {"file_path": "  "}
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_format_type(self, tool):
        """Test validation fails when format_type is invalid."""
        arguments = {"file_path": "test.py", "format_type": "invalid"}
        with pytest.raises(ValueError, match="Invalid format_type"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_unsupported_format_type(self, tool):
        """Test validation fails when format_type is not supported."""
        arguments = {"file_path": "test.py", "format_type": "html"}
        with pytest.raises(ValueError, match="Invalid format_type"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_unsupported_format_type_enumerates_valid(self, tool):
        """Error message must enumerate valid format_type values (issue #449)."""
        arguments = {"file_path": "test.py", "format_type": "html"}
        try:
            tool.validate_arguments(arguments)
            assert False, "Should have raised ValueError"
        except ValueError as exc:
            error_msg = str(exc)
            # Verify all valid formats are enumerated
            assert "compact" in error_msg
            assert "csv" in error_msg
            assert "full" in error_msg
            assert "signatures" in error_msg
            assert "html" in error_msg  # The invalid value
            assert "Valid values:" in error_msg

    def test_validate_arguments_invalid_language_type(self, tool):
        """Test validation fails when language is not a string."""
        arguments = {"file_path": "test.py", "language": 123}
        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_output_file_type(self, tool):
        """Test validation fails when output_file is not a string."""
        arguments = {"file_path": "test.py", "output_file": 123}
        with pytest.raises(ValueError, match="output_file must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_empty_output_file(self, tool):
        """Test validation fails when output_file is empty."""
        arguments = {"file_path": "test.py", "output_file": "  "}
        with pytest.raises(ValueError, match="output_file cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_suppress_output_type(self, tool):
        """Test validation fails when suppress_output is not a boolean."""
        arguments = {"file_path": "test.py", "suppress_output": "true"}
        with pytest.raises(ValueError, match="suppress_output must be a boolean"):
            tool.validate_arguments(arguments)


@pytest.mark.asyncio
class TestAnalyzeSurfacesParseErrors:
    """#572: a wrong-language / corrupt file must not be reported as a clean
    INFO with phantom symbols. tree-sitter's parse error is surfaced as
    parse_errors + verdict WARN so an agent doesn't trust the garbage."""

    async def test_wrong_language_file_flags_parse_errors(self, tmp_path):
        # C++ source in a .py file parses with errors (phantom 'public' class).
        f = tmp_path / "evil.py"
        f.write_text("class Foo { public: int x; void bar() {} };\n")
        tool = AnalyzeCodeStructureTool(project_root=str(tmp_path))
        result = await tool.execute({"file_path": str(f), "output_format": "json"})
        assert result["parse_errors"] is True
        assert result["verdict"] == "WARN"
        assert result["agent_summary"]["verdict"] == "WARN"

    async def test_valid_file_has_no_parse_errors_flag(self, tmp_path):
        # Regression: a clean parse keeps the INFO envelope, no parse_errors key.
        f = tmp_path / "good.py"
        f.write_text("class Foo:\n    def bar(self):\n        return 1\n")
        tool = AnalyzeCodeStructureTool(project_root=str(tmp_path))
        result = await tool.execute({"file_path": str(f), "output_format": "json"})
        assert "parse_errors" not in result
        assert result["verdict"] == "INFO"

    async def test_relative_file_path_with_project_root_still_flags(self, tmp_path):
        # Codex #682 P1: a project-relative file_path (the common MCP shape) must
        # use the resolved path for the validity check. The raw "evil.py" does
        # not exist from the pytest cwd, so a check against file_path would skip
        # and report the phantom symbols as clean.
        (tmp_path / "evil.py").write_text("class Foo { public: int x; };\n")
        tool = AnalyzeCodeStructureTool(project_root=str(tmp_path))
        result = await tool.execute({"file_path": "evil.py", "output_format": "json"})
        assert result["parse_errors"] is True
        assert result["verdict"] == "WARN"
