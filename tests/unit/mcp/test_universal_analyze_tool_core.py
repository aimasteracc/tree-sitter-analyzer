"""
Unit tests for UniversalAnalyzeTool — init, validation, and definition.

Tests for universal_analyze tool which provides code analysis
across multiple programming languages with automatic language detection.
"""

import pytest

from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import UniversalAnalyzeTool


@pytest.fixture
def tool():
    """Create a UniversalAnalyzeTool instance for testing."""
    return UniversalAnalyzeTool()


@pytest.fixture
def tool_with_project_root():
    """Create a UniversalAnalyzeTool instance with a project root."""
    return UniversalAnalyzeTool(project_root="/test/project")


class TestUniversalAnalyzeToolInit:
    """Tests for UniversalAnalyzeTool initialization."""

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


class TestUniversalAnalyzeToolSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path_updates_analysis_engine(self, tool):
        """Test that setting project path updates analysis engine."""
        tool.set_project_path("/new/project")
        # Both the project root and the analysis engine must reflect the new path
        assert tool.project_root == "/new/project"
        assert tool.analysis_engine is not None
        assert tool.project_root == "/new/project"


class TestUniversalAnalyzeToolGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_get_tool_definition_name(self, tool):
        """Test tool definition has correct name."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "analyze_code_universal"

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

    def test_get_tool_definition_schema_has_language(self, tool):
        """Test schema has language property."""
        schema = tool.get_tool_definition()["inputSchema"]
        assert "language" in schema["properties"]
        assert schema["properties"]["language"]["type"] == "string"

    def test_get_tool_definition_schema_has_analysis_type(self, tool):
        """Test schema has analysis_type property."""
        schema = tool.get_tool_definition()["inputSchema"]
        assert "analysis_type" in schema["properties"]
        assert schema["properties"]["analysis_type"]["type"] == "string"
        assert "enum" in schema["properties"]["analysis_type"]
        assert set(schema["properties"]["analysis_type"]["enum"]) == {
            "basic",
            "detailed",
            "structure",
            "metrics",
        }

    def test_get_tool_definition_schema_has_include_ast(self, tool):
        """Test schema has include_ast property."""
        schema = tool.get_tool_definition()["inputSchema"]
        assert "include_ast" in schema["properties"]
        assert schema["properties"]["include_ast"]["type"] == "boolean"

    def test_get_tool_definition_schema_has_include_queries(self, tool):
        """Test schema has include_queries property."""
        schema = tool.get_tool_definition()["inputSchema"]
        assert "include_queries" in schema["properties"]
        assert schema["properties"]["include_queries"]["type"] == "boolean"

    def test_get_tool_definition_schema_has_output_format(self, tool):
        """Test schema has output_format property."""
        schema = tool.get_tool_definition()["inputSchema"]
        assert "output_format" in schema["properties"]
        assert schema["properties"]["output_format"]["type"] == "string"
        assert "enum" in schema["properties"]["output_format"]
        assert set(schema["properties"]["output_format"]["enum"]) == {"json", "toon"}


class TestUniversalAnalyzeToolValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_arguments_valid_basic(self, tool):
        """Test validation with valid basic arguments."""
        arguments = {"file_path": "test.py"}
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_with_language(self, tool):
        """Test validation with language specified."""
        arguments = {"file_path": "test.py", "language": "python"}
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_with_analysis_type(self, tool):
        """Test validation with analysis_type specified."""
        arguments = {"file_path": "test.py", "analysis_type": "detailed"}
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

    def test_validate_arguments_invalid_language_type(self, tool):
        """Test validation fails when language is not a string."""
        arguments = {"file_path": "test.py", "language": 123}
        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_analysis_type_type(self, tool):
        """Test validation fails when analysis_type is not a string."""
        arguments = {"file_path": "test.py", "analysis_type": 123}
        with pytest.raises(ValueError, match="analysis_type must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_analysis_type_value(self, tool):
        """Test validation fails when analysis_type is invalid."""
        arguments = {"file_path": "test.py", "analysis_type": "invalid"}
        with pytest.raises(ValueError, match="analysis_type must be one of"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_include_ast_type(self, tool):
        """Test validation fails when include_ast is not a boolean."""
        arguments = {"file_path": "test.py", "include_ast": "true"}
        with pytest.raises(ValueError, match="include_ast must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_include_queries_type(self, tool):
        """Test validation fails when include_queries is not a boolean."""
        arguments = {"file_path": "test.py", "include_queries": "true"}
        with pytest.raises(ValueError, match="include_queries must be a boolean"):
            tool.validate_arguments(arguments)
