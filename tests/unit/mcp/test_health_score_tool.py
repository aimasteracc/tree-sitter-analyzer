#!/usr/bin/env python3
"""
Unit tests for HealthScoreTool.

Tests for health_score tool which grades file maintainability.
"""

import pytest

from tree_sitter_analyzer.mcp.tools.health_score_tool import (
    HealthScoreTool,
)


@pytest.fixture
def tool():
    """Create a HealthScoreTool instance for testing."""
    return HealthScoreTool()


@pytest.fixture
def tool_with_project_root(test_project_dir):
    """Create a HealthScoreTool instance with a project root."""
    return HealthScoreTool(project_root=str(test_project_dir))


class TestHealthScoreToolInit:
    """Tests for HealthScoreTool initialization."""

    def test_init_without_project_root(self, tool):
        """Test initialization without project root."""
        assert tool is not None
        assert tool.project_root is None

    def test_init_with_project_root(self, tool_with_project_root, test_project_dir):
        """Test initialization with project root."""
        assert tool_with_project_root is not None
        assert tool_with_project_root.project_root == str(test_project_dir)


class TestHealthScoreToolSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path(self, tool):
        """Test setting project path."""
        tool.set_project_path("/new/project")
        assert tool.project_root == "/new/project"


class TestHealthScoreToolGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_get_tool_definition_name(self, tool):
        """Test tool definition has correct name."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "health_score"

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

    def test_get_tool_definition_has_min_grade_property(self, tool):
        """Test tool definition has min_grade property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "min_grade" in properties
        assert properties["min_grade"]["type"] == "string"
        assert set(properties["min_grade"]["enum"]) == {
            "A", "B", "C", "D", "F"
        }

    def test_get_tool_definition_has_include_suggestions_property(self, tool):
        """Test tool definition has include_suggestions property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "include_suggestions" in properties
        assert properties["include_suggestions"]["type"] == "boolean"


class TestHealthScoreToolValidateArguments:
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

    def test_validate_arguments_invalid_min_grade(self, tool):
        """Test validation fails with invalid min_grade."""
        with pytest.raises(ValueError, match="min_grade must be one of"):
            tool.validate_arguments({"min_grade": "E"})

    def test_validate_arguments_invalid_include_suggestions(self, tool):
        """Test validation fails with non-boolean include_suggestions."""
        with pytest.raises(ValueError, match="include_suggestions must be a boolean"):
            tool.validate_arguments({"include_suggestions": "yes"})


class TestHealthScoreToolExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_empty_arguments(self, tool_with_project_root):
        """Test execution with empty arguments."""
        result = await tool_with_project_root.execute({})
        assert result["success"] is True
        assert "total_files" in result
        assert "grade_distribution" in result

    @pytest.mark.asyncio
    async def test_execute_with_min_grade(self, tool_with_project_root):
        """Test execution with min_grade filter."""
        result = await tool_with_project_root.execute({"min_grade": "B"})
        assert result["success"] is True
        assert "below_threshold" in result

    @pytest.mark.asyncio
    async def test_execute_with_include_suggestions(self, tool_with_project_root):
        """Test execution with suggestions included."""
        result = await tool_with_project_root.execute({"include_suggestions": True})
        assert result["success"] is True
        # Verify suggestions are included in files
        if result["files"]:
            assert "suggestions" in result["files"][0]

    @pytest.mark.asyncio
    async def test_execute_no_files_message(self, tool_with_project_root, tmp_path):
        """Test execution returns message when no files found."""
        # Use an empty directory
        empty_tool = HealthScoreTool(project_root=str(tmp_path))
        result = await empty_tool.execute({})
        if result["total_files"] == 0:
            assert "message" in result


# Test project directory fixture
@pytest.fixture
def test_project_dir(tmp_path):
    """Create a test project directory with sample files."""
    # Create a Python file with good health
    good_file = tmp_path / "good.py"
    good_file.write_text("""
def simple_function(x):
    return x * 2

class GoodClass:
    def method_one(self):
        pass

    def method_two(self):
        pass
""")

    # Create a Python file with poor health
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("""
""" + "\n".join([f"# comment line {i}" for i in range(100)]) + """
def very_long_function_with_many_parameters_and_deep_nesting(arg1, arg2, arg3, arg4, arg5):
    if True:
        if True:
            if True:
                if True:
                    if True:
                        return arg1 + arg2 + arg3 + arg4 + arg5

class BigClass:
    pass

class AnotherBigClass:
    pass

class YetAnotherBigClass:
    pass

class AndOneMoreBigClass:
    pass
""")
    return tmp_path
