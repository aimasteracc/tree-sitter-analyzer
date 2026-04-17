"""
Unit tests for JavaPatternAnalysisTool.

Tests for java_patterns tool which provides Java-specific pattern analysis
including Lambda expressions, Stream API chains, and Spring annotations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.java_patterns_tool import (
    JavaPatternAnalysisTool,
)


@pytest.fixture
def tool():
    """Create a JavaPatternAnalysisTool instance for testing."""
    return JavaPatternAnalysisTool()


@pytest.fixture
def tool_with_project_root():
    """Create a JavaPatternAnalysisTool instance with a project root."""
    return JavaPatternAnalysisTool(project_root="/test/project")


@pytest.fixture
def sample_java_code():
    """Sample Java code with lambda, stream, and Spring patterns."""
    return """
import org.springframework.stereotype.Service;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class UserService {
    private List<String> users;

    public List<String> getActiveUsers() {
        return users.stream()
            .filter(u -> u != null)
            .filter(String::isEmpty)
            .collect(Collectors.toList());
    }

    public void processUser(Runnable processor) {
        processor.run();
    }
}
"""


class TestJavaPatternAnalysisToolInit:
    """Tests for JavaPatternAnalysisTool initialization."""

    def test_init_without_project_root(self, tool):
        """Test initialization without project root."""
        assert tool is not None
        assert tool.project_root is None

    def test_init_with_project_root(self, tool_with_project_root):
        """Test initialization with project root."""
        assert tool_with_project_root is not None
        assert tool_with_project_root.project_root == "/test/project"


class TestJavaPatternAnalysisToolGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_get_tool_definition_name(self, tool):
        """Test tool definition has correct name."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "java_patterns"

    def test_get_tool_definition_has_description(self, tool):
        """Test tool definition has description."""
        definition = tool.get_tool_definition()
        assert "description" in definition
        assert isinstance(definition["description"], str)
        assert len(definition["description"]) > 0
        assert "Lambda" in definition["description"]
        assert "Stream" in definition["description"]

    def test_get_tool_definition_has_input_schema(self, tool):
        """Test tool definition has input schema."""
        definition = tool.get_tool_definition()
        assert "inputSchema" in definition
        assert isinstance(definition["inputSchema"], dict)

    def test_get_tool_definition_has_file_path_property(self, tool):
        """Test schema has file_path property."""
        definition = tool.get_tool_definition()
        assert "file_path" in definition["inputSchema"]["properties"]
        assert definition["inputSchema"]["properties"]["file_path"]["type"] == "string"

    def test_get_tool_definition_has_project_root_property(self, tool):
        """Test schema has project_root property."""
        definition = tool.get_tool_definition()
        assert "project_root" in definition["inputSchema"]["properties"]
        assert definition["inputSchema"]["properties"]["project_root"]["type"] == "string"

    def test_get_tool_definition_has_pattern_types_property(self, tool):
        """Test schema has pattern_types property."""
        definition = tool.get_tool_definition()
        assert "pattern_types" in definition["inputSchema"]["properties"]
        assert definition["inputSchema"]["properties"]["pattern_types"]["type"] == "array"

    def test_get_tool_definition_has_include_code_snippets_property(self, tool):
        """Test schema has include_code_snippets property."""
        definition = tool.get_tool_definition()
        assert "include_code_snippets" in definition["inputSchema"]["properties"]
        assert definition["inputSchema"]["properties"]["include_code_snippets"]["type"] == "boolean"


class TestJavaPatternAnalysisToolValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_arguments_valid_with_file_path(self, tool):
        """Test validation with valid file_path arguments."""
        arguments = {"file_path": "test.java", "include_code_snippets": True}
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_valid_with_project_root(self, tool):
        """Test validation with valid project_root arguments."""
        arguments = {"project_root": "/project", "pattern_types": ["lambda", "stream"]}
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_invalid_file_path_type(self, tool):
        """Test validation fails when file_path is not a string."""
        arguments = {"file_path": 123}
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_project_root_type(self, tool):
        """Test validation fails when project_root is not a string."""
        arguments = {"project_root": 123}
        with pytest.raises(ValueError, match="project_root must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_pattern_types_type(self, tool):
        """Test validation fails when pattern_types is not a list."""
        arguments = {"project_root": "/project", "pattern_types": "lambda"}
        with pytest.raises(ValueError, match="pattern_types must be an array"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_pattern_type_value(self, tool):
        """Test validation fails with invalid pattern type."""
        arguments = {"project_root": "/project", "pattern_types": ["invalid"]}
        with pytest.raises(ValueError, match="Invalid pattern type"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_include_code_snippets_type(self, tool):
        """Test validation fails when include_code_snippets is not a boolean."""
        arguments = {"file_path": "test.java", "include_code_snippets": "true"}
        with pytest.raises(ValueError, match="include_code_snippets must be a boolean"):
            tool.validate_arguments(arguments)


class TestJavaPatternAnalysisToolShouldInclude:
    """Tests for _should_include helper method."""

    def test_should_include_with_no_pattern_filter(self, tool):
        """Test all patterns included when no filter."""
        assert tool._should_include("lambda", None) is True
        assert tool._should_include("stream", None) is True
        assert tool._should_include("spring", None) is True

    def test_should_include_with_pattern_filter(self, tool):
        """Test pattern filtering works correctly."""
        patterns = ["lambda", "stream"]
        assert tool._should_include("lambda", patterns) is True
        assert tool._should_include("stream", patterns) is True
        assert tool._should_include("spring", patterns) is False


class TestJavaPatternAnalysisToolExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_with_single_file_success(self, tool, sample_java_code):
        """Test execute succeeds for single Java file."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.java"
            ),
            patch("pathlib.Path.read_text", return_value=sample_java_code),
        ):
            arguments = {"file_path": "test.java"}
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["files_analyzed"] == 1
            assert "patterns" in result

    @pytest.mark.asyncio
    async def test_execute_filters_pattern_types(self, tool, sample_java_code):
        """Test execute filters by pattern types."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.java"
            ),
            patch("pathlib.Path.read_text", return_value=sample_java_code),
        ):
            arguments = {"file_path": "test.java", "pattern_types": ["lambda"]}
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert "lambdas" in result["patterns"]
            # stream_chains should not be included
            assert "streams" not in result["patterns"]

    @pytest.mark.asyncio
    async def test_execute_without_code_snippets(self, tool, sample_java_code):
        """Test execute with include_code_snippets=False."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.java"
            ),
            patch("pathlib.Path.read_text", return_value=sample_java_code),
        ):
            arguments = {"file_path": "test.java", "include_code_snippets": False}
            result = await tool.execute(arguments)
            assert result["success"] is True
            # Check that text fields are None when snippets disabled
            if result["patterns"].get("lambdas", {}).get("expressions"):
                assert result["patterns"]["lambdas"]["expressions"][0]["text"] is None

    @pytest.mark.asyncio
    async def test_execute_file_read_error(self, tool):
        """Test execute handles file read errors."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.java"
            ),
            patch("pathlib.Path.read_text", side_effect=OSError("File not found")),
        ):
            arguments = {"file_path": "test.java"}
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_with_project_root_scans_files(
        self, tool, sample_java_code
    ):
        """Test execute with project_root scans all Java files."""
        mock_files = [
            MagicMock(path="src/File1.java", parts=["src", "File1.java"]),
            MagicMock(path="src/File2.java", parts=["src", "File2.java"]),
        ]
        for f in mock_files:
            f.relative_to = MagicMock(return_value=MagicMock(__str__=lambda s: f.path))

        with (
            patch.object(
                tool, "resolve_and_validate_directory_path", return_value="/project"
            ),
            patch("pathlib.Path.rglob", return_value=mock_files),
            patch("pathlib.Path.read_text", return_value=sample_java_code),
        ):
            arguments = {"project_root": "/project"}
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["files_analyzed"] >= 0

    @pytest.mark.asyncio
    async def test_execute_with_project_root_no_files_found(self, tool):
        """Test execute with project_root when no Java files found."""
        with (
            patch.object(
                tool, "resolve_and_validate_directory_path", return_value="/project"
            ),
            patch("pathlib.Path.rglob", return_value=[]),
        ):
            arguments = {"project_root": "/project"}
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["files_analyzed"] == 0
            assert "message" in result


class TestJavaPatternAnalysisToolSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path(self, tool):
        """Test setting project path."""
        tool.set_project_path("/new/project")
        assert tool.project_root == "/new/project"
