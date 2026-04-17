#!/usr/bin/env python3
"""
Unit tests for CodeCloneDetectionTool.

Tests for detect_code_clones tool which identifies duplicate
code patterns using AST fingerprinting.
"""

import pytest

from tree_sitter_analyzer.mcp.tools.code_clone_detection_tool import (
    CodeCloneDetectionTool,
)


@pytest.fixture
def tool():
    """Create a CodeCloneDetectionTool instance for testing."""
    return CodeCloneDetectionTool()


@pytest.fixture
def tool_with_project_root(test_project_dir):
    """Create a CodeCloneDetectionTool instance with a project root."""
    return CodeCloneDetectionTool(project_root=str(test_project_dir))


class TestCodeCloneDetectionToolInit:
    """Tests for CodeCloneDetectionTool initialization."""

    def test_init_without_project_root(self, tool):
        """Test initialization without project root."""
        assert tool is not None
        assert tool.project_root is None

    def test_init_with_project_root(self, tool_with_project_root, test_project_dir):
        """Test initialization with project root."""
        assert tool_with_project_root is not None
        assert tool_with_project_root.project_root == str(test_project_dir)


class TestCodeCloneDetectionToolSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path(self, tool):
        """Test setting project path."""
        tool.set_project_path("/new/project")
        assert tool.project_root == "/new/project"


class TestCodeCloneDetectionToolGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_get_tool_definition_name(self, tool):
        """Test tool definition has correct name."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "detect_code_clones"

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
        assert "properties" in definition["inputSchema"]

    def test_get_tool_definition_has_min_lines_property(self, tool):
        """Test tool definition has min_lines property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "min_lines" in properties
        assert properties["min_lines"]["type"] == "integer"

    def test_get_tool_definition_has_min_similarity_property(self, tool):
        """Test tool definition has min_similarity property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "min_similarity" in properties
        assert properties["min_similarity"]["type"] == "number"

    def test_get_tool_definition_has_min_severity_property(self, tool):
        """Test tool definition has min_severity property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "min_severity" in properties
        assert properties["min_severity"]["type"] == "string"
        assert "enum" in properties["min_severity"]
        assert set(properties["min_severity"]["enum"]) == {
            "info", "warning", "critical"
        }

    def test_get_tool_definition_has_clone_types_property(self, tool):
        """Test tool definition has clone_types property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "clone_types" in properties
        assert properties["clone_types"]["type"] == "array"


class TestCodeCloneDetectionToolValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_arguments_empty(self, tool):
        """Test validation with empty arguments."""
        assert tool.validate_arguments({}) is True

    def test_validate_arguments_with_file_path(self, tool):
        """Test validation with file_path."""
        assert tool.validate_arguments({"file_path": "src/main.py"}) is True

    def test_validate_arguments_invalid_file_path(self, tool):
        """Test validation fails with non-string file_path."""
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments({"file_path": 123})

    def test_validate_arguments_invalid_project_root(self, tool):
        """Test validation fails with non-string project_root."""
        with pytest.raises(ValueError, match="project_root must be a string"):
            tool.validate_arguments({"project_root": 123})

    def test_validate_arguments_invalid_min_lines(self, tool):
        """Test validation fails with invalid min_lines."""
        with pytest.raises(ValueError, match="min_lines must be a positive integer"):
            tool.validate_arguments({"min_lines": 0})

        with pytest.raises(ValueError, match="min_lines must be a positive integer"):
            tool.validate_arguments({"min_lines": -1})

    def test_validate_arguments_invalid_min_similarity(self, tool):
        """Test validation fails with invalid min_similarity."""
        with pytest.raises(ValueError, match="min_similarity must be a number"):
            tool.validate_arguments({"min_similarity": "high"})

        with pytest.raises(ValueError, match="min_similarity must be between 0.0 and 1.0"):
            tool.validate_arguments({"min_similarity": 1.5})

        with pytest.raises(ValueError, match="min_similarity must be between 0.0 and 1.0"):
            tool.validate_arguments({"min_similarity": -0.1})

    def test_validate_arguments_invalid_min_severity(self, tool):
        """Test validation fails with invalid min_severity."""
        with pytest.raises(ValueError, match="min_severity must be one of"):
            tool.validate_arguments({"min_severity": "urgent"})

    def test_validate_arguments_invalid_clone_types(self, tool):
        """Test validation fails with invalid clone_types."""
        with pytest.raises(ValueError, match="clone_types must be an array"):
            tool.validate_arguments({"clone_types": "type_1_exact"})

        with pytest.raises(ValueError, match="Invalid clone type"):
            tool.validate_arguments({"clone_types": ["invalid_type"]})


class TestCodeCloneDetectionToolExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_empty_arguments(self, tool_with_project_root):
        """Test execution with empty arguments."""
        result = await tool_with_project_root.execute({})
        assert result["success"] is True
        assert "total_clones" in result
        assert "clones" in result

    @pytest.mark.asyncio
    async def test_execute_with_min_lines(self, tool_with_project_root):
        """Test execution with min_lines filter."""
        result = await tool_with_project_root.execute({"min_lines": 10})
        assert result["success"] is True
        assert "total_clones" in result

    @pytest.mark.asyncio
    async def test_execute_with_min_severity_warning(self, tool_with_project_root):
        """Test execution with min_severity filter."""
        result = await tool_with_project_root.execute({"min_severity": "warning"})
        assert result["success"] is True
        # Verify all returned clones are warning or critical
        for clone in result["clones"]:
            assert clone["severity"] in ["warning", "critical"]

    @pytest.mark.asyncio
    async def test_execute_with_clone_types(self, tool_with_project_root):
        """Test execution with clone_types filter."""
        result = await tool_with_project_root.execute({"clone_types": ["type_1_exact"]})
        assert result["success"] is True
        # Verify all returned clones are type_1_exact
        for clone in result["clones"]:
            assert clone["type"] == "type_1_exact"

    @pytest.mark.asyncio
    async def test_execute_with_project_root(self, tool_with_project_root):
        """Test execution with project root."""
        result = await tool_with_project_root.execute({})
        assert result["success"] is True
        assert "total_clones" in result

    @pytest.mark.asyncio
    async def test_execute_invalid_file_path_raises(self, tool_with_project_root):
        """Test execution with invalid file path raises error."""
        # The error handler wraps ValueError in AnalysisError
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError
        with pytest.raises(AnalysisError, match="file_path must be a string"):
            await tool_with_project_root.execute({"file_path": 123})


# Test project directory fixture
@pytest.fixture
def test_project_dir(tmp_path):
    """Create a test project directory with sample files."""
    # Create a simple Python file with duplicate code
    sample_file = tmp_path / "sample.py"
    sample_file.write_text("""
def function_one():
    result = []
    for i in range(10):
        result.append(i * 2)
    return result

def function_two():
    result = []
    for i in range(10):
        result.append(i * 2)
    return result
""")
    return tmp_path
