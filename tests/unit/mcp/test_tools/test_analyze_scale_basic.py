"""
Unit tests for AnalyzeScaleTool.

Tests for analyze_code_scale tool which provides code scale analysis
including metrics about complexity, size, and structure.
"""

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool


@pytest.fixture
def tool():
    """Create an AnalyzeScaleTool instance for testing."""
    return AnalyzeScaleTool()


@pytest.fixture
def tool_with_project_root():
    """Create an AnalyzeScaleTool instance with a project root."""
    return AnalyzeScaleTool(project_root="/test/project")


class TestAnalyzeScaleToolInit:
    """Tests for AnalyzeScaleTool initialization."""

    def test_init_without_project_root(self, tool):
        """Test initialization without project root."""
        assert tool is not None
        assert tool.project_root is None
        assert tool.analysis_engine is not None

    def test_init_with_project_root(self, tool_with_project_root):
        """Test initialization with project root."""
        assert tool_with_project_root is not None
        assert tool_with_project_root.project_root == "/test/project"
        assert tool_with_project_root.analysis_engine is not None


class TestAnalyzeScaleToolGetToolSchema:
    """Tests for get_tool_schema method."""

    def test_get_tool_schema_structure(self, tool):
        """Test tool schema has correct structure."""
        schema = tool.get_tool_schema()
        assert isinstance(schema, dict)
        assert "type" in schema
        assert "properties" in schema
        assert schema["type"] == "object"

    def test_get_tool_schema_has_file_path_property(self, tool):
        """Test schema has file_path property."""
        schema = tool.get_tool_schema()
        assert "file_path" in schema["properties"]
        assert schema["properties"]["file_path"]["type"] == "string"

    def test_get_tool_schema_has_file_paths_property(self, tool):
        """Test schema has file_paths property for batch mode."""
        schema = tool.get_tool_schema()
        assert "file_paths" in schema["properties"]
        assert schema["properties"]["file_paths"]["type"] == "array"

    def test_get_tool_schema_has_metrics_only_property(self, tool):
        """Test schema has metrics_only property."""
        schema = tool.get_tool_schema()
        assert "metrics_only" in schema["properties"]
        assert schema["properties"]["metrics_only"]["type"] == "boolean"

    def test_get_tool_schema_has_language_property(self, tool):
        """Test schema has language property."""
        schema = tool.get_tool_schema()
        assert "language" in schema["properties"]
        assert schema["properties"]["language"]["type"] == "string"

    def test_get_tool_schema_has_include_complexity_property(self, tool):
        """Test schema has include_complexity property."""
        schema = tool.get_tool_schema()
        assert "include_complexity" in schema["properties"]
        assert schema["properties"]["include_complexity"]["type"] == "boolean"

    def test_get_tool_schema_has_include_details_property(self, tool):
        """Test schema has include_details property."""
        schema = tool.get_tool_schema()
        assert "include_details" in schema["properties"]
        assert schema["properties"]["include_details"]["type"] == "boolean"

    def test_get_tool_schema_has_include_guidance_property(self, tool):
        """Test schema has include_guidance property."""
        schema = tool.get_tool_schema()
        assert "include_guidance" in schema["properties"]
        assert schema["properties"]["include_guidance"]["type"] == "boolean"

    def test_get_tool_schema_has_output_format_property(self, tool):
        """Test schema has output_format property."""
        schema = tool.get_tool_schema()
        assert "output_format" in schema["properties"]
        assert schema["properties"]["output_format"]["type"] == "string"
        assert "enum" in schema["properties"]["output_format"]
        assert "json" in schema["properties"]["output_format"]["enum"]
        assert "toon" in schema["properties"]["output_format"]["enum"]


class TestAnalyzeScaleToolGetToolDefinition:
    """Tests for get_tool_definition method."""

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


class TestAnalyzeScaleToolValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_arguments_valid_single_mode(self, tool):
        """Test validation with valid single mode arguments."""
        arguments = {
            "file_path": "test.py",
            "language": "python",
            "include_complexity": True,
            "include_details": False,
            "include_guidance": True,
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_valid_batch_mode(self, tool):
        """Test validation with valid batch mode arguments."""
        arguments = {
            "file_paths": ["test1.py", "test2.py"],
            "metrics_only": True,
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_missing_file_path(self, tool):
        """Test validation fails when file_path is missing."""
        arguments = {"language": "python"}
        with pytest.raises(ValueError, match="Required field 'file_path' is missing"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_empty_file_path(self, tool):
        """Test validation fails when file_path is empty."""
        arguments = {"file_path": ""}
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_file_path_type(self, tool):
        """Test validation fails when file_path is not a string."""
        arguments = {"file_path": 123}
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_language_type(self, tool):
        """Test validation fails when language is not a string."""
        arguments = {"file_path": "test.py", "language": 123}
        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_include_complexity_type(self, tool):
        """Test validation fails when include_complexity is not a boolean."""
        arguments = {"file_path": "test.py", "include_complexity": "true"}
        with pytest.raises(ValueError, match="include_complexity must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_include_details_type(self, tool):
        """Test validation fails when include_details is not a boolean."""
        arguments = {"file_path": "test.py", "include_details": "true"}
        with pytest.raises(ValueError, match="include_details must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_include_guidance_type(self, tool):
        """Test validation fails when include_guidance is not a boolean."""
        arguments = {"file_path": "test.py", "include_guidance": "true"}
        with pytest.raises(ValueError, match="include_guidance must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_mutually_exclusive(self, tool):
        """Test validation fails when both file_path and file_paths are provided."""
        arguments = {"file_path": "test.py", "file_paths": ["test2.py"]}
        with pytest.raises(
            ValueError, match="file_paths is mutually exclusive with file_path"
        ):
            tool.validate_arguments(arguments)

    def test_validate_arguments_empty_file_paths(self, tool):
        """Test validation fails when file_paths is empty."""
        arguments = {"file_paths": [], "metrics_only": True}
        with pytest.raises(ValueError, match="file_paths must be a non-empty list"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_file_paths_type(self, tool):
        """Test validation fails when file_paths is not a list."""
        arguments = {"file_paths": "test.py", "metrics_only": True}
        with pytest.raises(ValueError, match="file_paths must be a non-empty list"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_metrics_only_type(self, tool):
        """Test validation fails when metrics_only is not a boolean."""
        arguments = {"file_paths": ["test.py"], "metrics_only": "true"}
        with pytest.raises(ValueError, match="metrics_only must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_metrics_only_required_for_batch(self, tool):
        """Test validation fails when metrics_only is False in batch mode."""
        arguments = {"file_paths": ["test.py"], "metrics_only": False}
        with pytest.raises(
            ValueError,
            match="metrics_only must be true when using file_paths batch mode",
        ):
            tool.validate_arguments(arguments)
