#!/usr/bin/env python3
"""
Unit tests for TestCoverageTool.

Tests for test_coverage tool which identifies untested code elements.
"""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.analysis.test_coverage import (
    ElementType,
    SourceElement,
    TestCoverageResult,
)
from tree_sitter_analyzer.mcp.tools.test_coverage_tool import (
    TestCoverageTool,
)


@pytest.fixture
def tool():
    """Create a TestCoverageTool instance for testing."""
    return TestCoverageTool()


@pytest.fixture
def tool_with_project_root(temp_project_dir):
    """Create a TestCoverageTool instance with a project root."""
    return TestCoverageTool(project_root=str(temp_project_dir))


@pytest.fixture
def mock_coverage_result():
    """Create a mock TestCoverageResult."""
    return TestCoverageResult(
        source_file="/project/src/utils.py",
        language="python",
        total_elements=5,
        tested_elements=3,
        untested_elements=[
            SourceElement(
                name="helper_function",
                element_type=ElementType.FUNCTION,
                line=42,
                file_path="/project/src/utils.py",
            ),
            SourceElement(
                name="DataProcessor",
                element_type=ElementType.CLASS,
                line=15,
                file_path="/project/src/utils.py",
            ),
        ],
        coverage_percent=60.0,
    )


class TestTestCoverageToolInit:
    """Tests for TestCoverageTool initialization."""

    def test_init_without_project_root(self, tool):
        """Test initialization without project root."""
        assert tool is not None
        assert tool.project_root is None
        assert tool.analyzer is not None

    def test_init_with_project_root(self, tool_with_project_root, temp_project_dir):
        """Test initialization with project root."""
        assert tool_with_project_root is not None
        assert tool_with_project_root.project_root == str(temp_project_dir)


class TestTestCoverageToolSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path(self, tool):
        """Test setting project path."""
        tool.set_project_path("/new/project")
        assert tool.project_root == "/new/project"


class TestTestCoverageToolGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_get_tool_definition_name(self, tool):
        """Test tool definition has correct name."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "test_coverage"

    def test_get_tool_definition_has_description(self, tool):
        """Test tool definition has description."""
        definition = tool.get_tool_definition()
        assert "description" in definition
        assert isinstance(definition["description"], str)
        assert len(definition["description"]) > 0
        assert "test coverage" in definition["description"].lower()

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

    def test_get_tool_definition_has_include_tested_property(self, tool):
        """Test tool definition has include_tested property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "include_tested" in properties
        assert properties["include_tested"]["type"] == "boolean"
        assert properties["include_tested"]["default"] is False

    def test_get_tool_definition_has_output_format_property(self, tool):
        """Test tool definition has output_format property."""
        definition = tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]
        assert "output_format" in properties
        assert properties["output_format"]["type"] == "string"
        assert set(properties["output_format"]["enum"]) == {"toon", "json"}


class TestTestCoverageToolExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_single_file_toon_format(
        self, tool, mock_coverage_result, temp_project_dir
    ):
        """Test execute with single file in TOON format."""
        with patch.object(
            tool.analyzer, "analyze_file", return_value=mock_coverage_result
        ):
            with patch.object(
                tool, "_find_test_files", return_value=[]
            ):
                tool.set_project_path(str(temp_project_dir))

                result = await tool.execute({
                    "file_path": "src/utils.py",
                    "output_format": "toon",
                })

        assert result["format"] == "toon"
        assert "content" in result
        assert "summary" in result
        assert result["summary"]["coverage_percent"] == 60.0
        assert result["summary"]["grade"] == "B"
        assert result["summary"]["tested"] == 3
        assert result["summary"]["total"] == 5
        assert result["summary"]["untested_count"] == 2

    @pytest.mark.asyncio
    async def test_execute_single_file_json_format(
        self, tool, mock_coverage_result, temp_project_dir
    ):
        """Test execute with single file in JSON format."""
        with patch.object(
            tool.analyzer, "analyze_file", return_value=mock_coverage_result
        ):
            with patch.object(
                tool, "_find_test_files", return_value=[]
            ):
                tool.set_project_path(str(temp_project_dir))

                result = await tool.execute({
                    "file_path": "src/utils.py",
                    "output_format": "json",
                })

        assert result["file"] == "/project/src/utils.py"
        assert result["coverage_percent"] == 60.0
        assert result["grade"] == "B"
        assert result["tested_elements"] == 3
        assert result["total_elements"] == 5
        assert len(result["untested_elements"]) == 2

    @pytest.mark.asyncio
    async def test_execute_project_wide(self, tool, temp_project_dir):
        """Test execute with project-wide analysis."""
        mock_results = {
            "/project/src/a.py": TestCoverageResult(
                source_file="/project/src/a.py",
                language="python",
                total_elements=10,
                tested_elements=8,
                untested_elements=[],
                coverage_percent=80.0,
            ),
            "/project/src/b.py": TestCoverageResult(
                source_file="/project/src/b.py",
                language="python",
                total_elements=5,
                tested_elements=3,
                untested_elements=[],
                coverage_percent=60.0,
            ),
        }

        with patch.object(
            tool.analyzer, "analyze_project", return_value=mock_results
        ):
            result = await tool.execute({
                "project_root": str(temp_project_dir),
                "output_format": "toon",
            })

        assert result["format"] == "toon"
        assert result["summary"]["files_analyzed"] == 2
        assert result["summary"]["total_elements"] == 15
        assert result["summary"]["tested_elements"] == 11

    @pytest.mark.asyncio
    async def test_execute_full_coverage(self, tool, temp_project_dir):
        """Test execute with fully covered file."""
        full_coverage_result = TestCoverageResult(
            source_file="/project/src/perfect.py",
            language="python",
            total_elements=5,
            tested_elements=5,
            untested_elements=[],
            coverage_percent=100.0,
        )

        with patch.object(
            tool.analyzer, "analyze_file", return_value=full_coverage_result
        ):
            with patch.object(
                tool, "_find_test_files", return_value=[]
            ):
                tool.set_project_path(str(temp_project_dir))

                result = await tool.execute({
                    "file_path": "src/perfect.py",
                    "include_tested": True,
                })

        assert result["summary"]["coverage_percent"] == 100.0
        assert result["summary"]["grade"] == "A"
        assert "All elements are tested" in result["content"]


class TestTestCoverageToolHelpers:
    """Tests for helper methods."""

    def test_element_emoji(self, tool):
        """Test _element_emoji returns correct emojis."""
        assert tool._element_emoji("function") == "🔷"
        assert tool._element_emoji("class") == "📦"
        assert tool._element_emoji("method") == "⚙️"
        assert tool._element_emoji("unknown") == "📍"

    def test_grade_emoji(self, tool):
        """Test _grade_emoji returns correct emojis."""
        assert tool._grade_emoji("A") == "🟢"
        assert tool._grade_emoji("B") == "🔵"
        assert tool._grade_emoji("C") == "🟡"
        assert tool._grade_emoji("D") == "🟠"
        assert tool._grade_emoji("F") == "🔴"
        assert tool._grade_emoji("X") == "⚪"
