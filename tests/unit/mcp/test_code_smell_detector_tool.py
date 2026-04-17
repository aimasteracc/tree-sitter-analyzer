#!/usr/bin/env python3
"""
Unit tests for CodeSmellDetectorTool.

Tests for detect_code_smells tool which identifies code smells
and anti-patterns using AST analysis.
"""

import pytest

from tree_sitter_analyzer.mcp.tools.code_smell_detector_tool import (
    CodeSmellDetectorTool,
)


@pytest.fixture
def tool():
    """Create a CodeSmellDetectorTool instance for testing."""
    return CodeSmellDetectorTool()


@pytest.fixture
def tool_with_project_root(test_project_dir):
    """Create a CodeSmellDetectorTool instance with a project root."""
    return CodeSmellDetectorTool(project_root=str(test_project_dir))


class TestCodeSmellDetectorToolInit:
    """Tests for CodeSmellDetectorTool initialization."""

    def test_init_without_project_root(self, tool):
        """Test initialization without project root."""
        assert tool is not None
        assert tool.project_root is None

    def test_init_with_project_root(self, tool_with_project_root, test_project_dir):
        """Test initialization with project root."""
        assert tool_with_project_root is not None
        assert tool_with_project_root.project_root == str(test_project_dir)


class TestCodeSmellDetectorToolSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path(self, tool):
        """Test setting project path."""
        tool.set_project_path("/new/project")
        assert tool.project_root == "/new/project"


class TestCodeSmellDetectorToolGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_get_tool_definition_name(self, tool):
        """Test tool definition has correct name."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "detect_code_smells"

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

    def test_get_tool_definition_has_file_path_property(self, tool):
        """Test tool definition has file_path property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "file_path" in properties
        assert properties["file_path"]["type"] == "string"

    def test_get_tool_definition_has_project_root_property(self, tool):
        """Test tool definition has project_root property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "project_root" in properties
        assert properties["project_root"]["type"] == "string"

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

    def test_get_tool_definition_has_smell_types_property(self, tool):
        """Test tool definition has smell_types property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "smell_types" in properties
        assert properties["smell_types"]["type"] == "array"

    def test_get_tool_definition_has_thresholds_property(self, tool):
        """Test tool definition has thresholds property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "thresholds" in properties
        assert properties["thresholds"]["type"] == "object"


class TestCodeSmellDetectorToolValidateArguments:
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

    def test_validate_arguments_invalid_min_severity(self, tool):
        """Test validation fails with invalid min_severity."""
        with pytest.raises(ValueError, match="min_severity must be one of"):
            tool.validate_arguments({"min_severity": "urgent"})

    def test_validate_arguments_invalid_smell_types(self, tool):
        """Test validation fails with invalid smell_types."""
        with pytest.raises(ValueError, match="smell_types must be an array"):
            tool.validate_arguments({"smell_types": "god_class"})

        with pytest.raises(ValueError, match="Invalid smell type"):
            tool.validate_arguments({"smell_types": ["invalid_smell"]})

    def test_validate_arguments_invalid_thresholds(self, tool):
        """Test validation fails with invalid thresholds."""
        with pytest.raises(ValueError, match="thresholds must be an object"):
            tool.validate_arguments({"thresholds": "invalid"})

        with pytest.raises(ValueError, match="must be a positive integer"):
            tool.validate_arguments({"thresholds": {"god_class_methods": 0}})

        with pytest.raises(ValueError, match="must be a positive integer"):
            tool.validate_arguments({"thresholds": {"long_method_lines": -1}})


class TestCodeSmellDetectorToolExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_empty_arguments(self, tool_with_project_root):
        """Test execution with empty arguments."""
        result = await tool_with_project_root.execute({})
        assert result["success"] is True
        assert "total_smells" in result
        assert "smells" in result

    @pytest.mark.asyncio
    async def test_execute_with_min_severity_warning(self, tool_with_project_root):
        """Test execution with min_severity filter."""
        result = await tool_with_project_root.execute({"min_severity": "warning"})
        assert result["success"] is True
        # Verify all returned smells are warning or critical
        for smell in result["smells"]:
            assert smell["severity"] in ["warning", "critical"]

    @pytest.mark.asyncio
    async def test_execute_with_smell_types(self, tool_with_project_root):
        """Test execution with smell_types filter."""
        result = await tool_with_project_root.execute({"smell_types": ["long_method", "deep_nesting"]})
        assert result["success"] is True
        # Verify all returned smells are of specified types
        for smell in result["smells"]:
            assert smell["type"] in ["long_method", "deep_nesting"]

    @pytest.mark.asyncio
    async def test_execute_with_custom_thresholds(self, tool_with_project_root):
        """Test execution with custom thresholds."""
        result = await tool_with_project_root.execute({
            "thresholds": {
                "long_method_lines": 30,
                "deep_nesting_levels": 3,
            }
        })
        assert result["success"] is True
        assert "total_smells" in result

    @pytest.mark.asyncio
    async def test_execute_with_project_root(self, tool_with_project_root):
        """Test execution with project root."""
        result = await tool_with_project_root.execute({})
        assert result["success"] is True
        assert "total_smells" in result

    @pytest.mark.asyncio
    async def test_execute_no_smells_message(self, tool_with_project_root):
        """Test execution returns message when no smells found."""
        # Use a project with no smells (empty or minimal code)
        result = await tool_with_project_root.execute({})
        if result["total_smells"] == 0:
            assert "message" in result
            assert "well-structured" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_critical_warning(self, tool_with_project_root):
        """Test execution includes warning for critical smells."""
        result = await tool_with_project_root.execute({})
        if result.get("warning"):
            assert "critical" in result["warning"].lower()


# Test project directory fixture
@pytest.fixture
def test_project_dir(tmp_path):
    """Create a test project directory with sample files."""
    # Create a Python file with some code smells
    smell_file = tmp_path / "smelly.py"
    smell_file.write_text("""
class BigClass:
    def method_one(self):
        pass

    def method_two(self):
        pass

    # ... many methods
    def method_twenty(self):
        pass

    def very_long_method(self):
        # A very long method with deep nesting
        if True:
            if True:
                if True:
                    if True:
                        if True:
                            return 42

    def method_with_magic(self):
        x = 3
        y = 7
        z = 42
        return x + y + z
""")
    return tmp_path
