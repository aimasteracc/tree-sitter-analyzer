#!/usr/bin/env python3
"""
Unit tests for CIReportTool.

Tests for ci_report tool which generates CI/CD friendly reports.
"""

import pytest

from tree_sitter_analyzer.mcp.tools.ci_report_tool import (
    CIReportTool,
)


@pytest.fixture
def tool():
    """Create a CIReportTool instance for testing."""
    return CIReportTool()


@pytest.fixture
def tool_with_project_root(test_project_dir):
    """Create a CIReportTool instance with a project root."""
    return CIReportTool(project_root=str(test_project_dir))


class TestCIReportToolInit:
    """Tests for CIReportTool initialization."""

    def test_init_without_project_root(self, tool):
        """Test initialization without project root."""
        assert tool is not None
        assert tool.project_root is None

    def test_init_with_project_root(self, tool_with_project_root, test_project_dir):
        """Test initialization with project root."""
        assert tool_with_project_root is not None
        assert tool_with_project_root.project_root == str(test_project_dir)


class TestCIReportToolSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path(self, tool):
        """Test setting project path."""
        tool.set_project_path("/new/project")
        assert tool.project_root == "/new/project"


class TestCIReportToolGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_get_tool_definition_name(self, tool):
        """Test tool definition has correct name."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "ci_report"

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

    def test_get_tool_definition_has_max_cycles_property(self, tool):
        """Test tool definition has max_cycles property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "max_cycles" in properties
        assert properties["max_cycles"]["type"] == "integer"

    def test_get_tool_definition_has_max_critical_property(self, tool):
        """Test tool definition has max_critical property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "max_critical" in properties
        assert properties["max_critical"]["type"] == "integer"

    def test_get_tool_definition_has_output_format_property(self, tool):
        """Test tool definition has output_format property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "output_format" in properties
        assert properties["output_format"]["type"] == "string"
        assert set(properties["output_format"]["enum"]) == {"json", "summary"}


class TestCIReportToolValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_arguments_empty(self, tool):
        """Test validation with empty arguments."""
        assert tool.validate_arguments({}) is True

    def test_validate_arguments_invalid_min_grade(self, tool):
        """Test validation fails with invalid min_grade."""
        with pytest.raises(ValueError, match="min_grade must be one of"):
            tool.validate_arguments({"min_grade": "E"})

    def test_validate_arguments_invalid_max_cycles(self, tool):
        """Test validation fails with negative max_cycles."""
        with pytest.raises(ValueError, match="max_cycles must be a non-negative integer"):
            tool.validate_arguments({"max_cycles": -1})

    def test_validate_arguments_invalid_max_critical(self, tool):
        """Test validation fails with negative max_critical."""
        with pytest.raises(ValueError, match="max_critical must be a non-negative integer"):
            tool.validate_arguments({"max_critical": -1})

    def test_validate_arguments_invalid_output_format(self, tool):
        """Test validation fails with invalid output_format."""
        with pytest.raises(ValueError, match="output_format must be one of"):
            tool.validate_arguments({"output_format": "xml"})


class TestCIReportToolExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_empty_arguments(self, tool_with_project_root):
        """Test execution with empty arguments."""
        result = await tool_with_project_root.execute({})
        assert result["success"] is True
        assert "passed" in result
        assert "total_files" in result
        assert "grade_distribution" in result

    @pytest.mark.asyncio
    async def test_execute_with_min_grade(self, tool_with_project_root):
        """Test execution with min_grade filter."""
        result = await tool_with_project_root.execute({"min_grade": "B"})
        assert result["success"] is True
        assert "passed" in result

    @pytest.mark.asyncio
    async def test_execute_with_max_cycles(self, tool_with_project_root):
        """Test execution with max_cycles limit."""
        result = await tool_with_project_root.execute({"max_cycles": 5})
        assert result["success"] is True
        assert "cycle_count" in result

    @pytest.mark.asyncio
    async def test_execute_json_format(self, tool_with_project_root):
        """Test execution with JSON output format."""
        result = await tool_with_project_root.execute({"output_format": "json"})
        assert result["success"] is True
        assert result["format"] == "json"
        assert "data" in result

    @pytest.mark.asyncio
    async def test_execute_summary_format(self, tool_with_project_root):
        """Test execution with summary output format."""
        result = await tool_with_project_root.execute({"output_format": "summary"})
        assert result["success"] is True
        assert "passed" in result
        assert "grade_distribution" in result

    @pytest.mark.asyncio
    async def test_execute_includes_critical_files(self, tool_with_project_root):
        """Test execution includes critical files list."""
        result = await tool_with_project_root.execute({})
        assert result["success"] is True
        assert "critical_files" in result

    @pytest.mark.asyncio
    async def test_execute_failed_checks_when_not_passed(self, tool_with_project_root):
        """Test execution includes failed checks when not passed."""
        result = await tool_with_project_root.execute({"min_grade": "A"})
        assert result["success"] is True
        if not result["passed"]:
            assert "failed_checks" in result
            assert "error" in result


# Test project directory fixture
@pytest.fixture
def test_project_dir(tmp_path):
    """Create a test project directory with sample files."""
    # Create a Python file with good health
    good_file = tmp_path / "good.py"
    good_file.write_text("""
def simple_function(x):
    return x * 2
""")

    # Create a Python file with poor health
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("""
""" + "\n".join([f"# comment line {i}" for i in range(50)]) + """

class BigClass:
    pass

class AnotherBigClass:
    pass

class YetAnotherBigClass:
    pass
""")
    return tmp_path
