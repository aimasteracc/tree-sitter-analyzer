"""
Unit tests for UniversalAnalyzeTool.

Tests for universal_analyze tool which provides code analysis
across multiple programming languages with automatic language detection.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import UniversalAnalyzeTool
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


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

    def test_set_project_path(self, tool):
        """Test setting project path."""
        tool.set_project_path("/new/project")
        assert tool.project_root == "/new/project"

    def test_set_project_path_updates_analysis_engine(self, tool):
        """Test that setting project path updates analysis engine."""
        tool.set_project_path("/new/project")
        # Analysis engine should be recreated with new project root
        assert tool.analysis_engine is not None


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


class TestUniversalAnalyzeToolExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_missing_file_path(self, tool):
        """Test execute fails when file_path is missing."""
        arguments = {}
        with pytest.raises(AnalysisError, match="file_path is required"):
            await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, tool):
        """Test execute fails when file doesn't exist."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/nonexistent.py"
            ),
            patch("pathlib.Path.exists", return_value=False),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(
                AnalysisError, match="Invalid file path: file does not exist"
            ):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_language_not_detected(self, tool):
        """Test execute fails when language cannot be detected."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.unknown"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file",
                return_value="unknown",
            ),
        ):
            arguments = {"file_path": "test.unknown"}
            with pytest.raises(AnalysisError, match="Could not detect language"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_language_not_supported(self, tool):
        """Test execute fails when language is not supported."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.unknown"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file",
                return_value="unsupported",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported",
                return_value=False,
            ),
        ):
            arguments = {"file_path": "test.unknown"}
            with pytest.raises(AnalysisError, match="is not supported by tree-sitter"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_invalid_analysis_type(self, tool):
        """Test execute fails when analysis_type is invalid."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported",
                return_value=True,
            ),
        ):
            arguments = {"file_path": "test.py", "analysis_type": "invalid"}
            with pytest.raises(AnalysisError, match="Invalid analysis_type"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_success_basic_analysis(self, tool):
        """Test successful basic analysis."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})
        mock_analysis_result.to_dict = MagicMock(
            return_value={"elements": [], "line_count": 100}
        )

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported",
                return_value=True,
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "analysis_type": "basic"}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_success_detailed_analysis(self, tool):
        """Test successful detailed analysis."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})
        mock_analysis_result.to_dict = MagicMock(
            return_value={"elements": [], "line_count": 100}
        )

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported",
                return_value=True,
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "analysis_type": "detailed"}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_success_structure_analysis(self, tool):
        """Test successful structure analysis."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})
        mock_analysis_result.to_dict = MagicMock(
            return_value={"elements": [], "line_count": 100}
        )

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported",
                return_value=True,
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "analysis_type": "structure"}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_success_metrics_analysis(self, tool):
        """Test successful metrics analysis."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})
        mock_analysis_result.to_dict = MagicMock(
            return_value={"elements": [], "line_count": 100}
        )

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported",
                return_value=True,
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "analysis_type": "metrics"}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_with_include_ast(self, tool):
        """Test execute with include_ast=True."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})
        mock_analysis_result.to_dict = MagicMock(
            return_value={"elements": [], "line_count": 100}
        )

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported",
                return_value=True,
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "include_ast": True}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_with_include_queries(self, tool):
        """Test execute with include_queries=True."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})
        mock_analysis_result.to_dict = MagicMock(
            return_value={"elements": [], "line_count": 100}
        )

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported",
                return_value=True,
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch.object(
                tool,
                "_get_available_queries",
                new_callable=AsyncMock,
                return_value={"language": "python", "queries": []},
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "include_queries": True}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_with_json_output_format(self, tool):
        """Test execute with output_format='json'."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})
        mock_analysis_result.to_dict = MagicMock(
            return_value={"elements": [], "line_count": 100}
        )

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported",
                return_value=True,
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "output_format": "json"}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_analysis_failure(self, tool):
        """Test execute handles analysis engine failure."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported",
                return_value=True,
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(RuntimeError, match="Failed to analyze file"):
                await tool.execute(arguments)


class TestUniversalAnalyzeToolExtractBasicMetrics:
    """Tests for _extract_basic_metrics method."""

    def test_extract_basic_metrics_empty_elements(self, tool):
        """Test extracting basic metrics with empty elements."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})

        metrics = tool._extract_basic_metrics(mock_analysis_result)
        assert "metrics" in metrics
        assert metrics["metrics"]["elements"]["classes"] == 0
        assert metrics["metrics"]["elements"]["methods"] == 0
        assert metrics["metrics"]["elements"]["fields"] == 0
        assert metrics["metrics"]["elements"]["imports"] == 0

    def test_extract_basic_metrics_with_elements(self, tool):
        """Test extracting basic metrics with elements."""
        mock_class = MagicMock()
        mock_class.element_type = "class"

        mock_method = MagicMock()
        mock_method.element_type = "function"

        mock_field = MagicMock()
        mock_field.element_type = "variable"

        mock_import = MagicMock()
        mock_import.element_type = "import"

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [
            mock_class,
            mock_method,
            mock_field,
            mock_import,
        ]
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})
        mock_analysis_result.annotations = []
        mock_analysis_result.package = None

        metrics = tool._extract_basic_metrics(mock_analysis_result)
        assert metrics["metrics"]["elements"]["classes"] == 1
        assert metrics["metrics"]["elements"]["methods"] == 1
        assert metrics["metrics"]["elements"]["fields"] == 1
        assert metrics["metrics"]["elements"]["imports"] == 1


class TestUniversalAnalyzeToolExtractDetailedMetrics:
    """Tests for _extract_detailed_metrics method."""

    def test_extract_detailed_metrics_includes_complexity(self, tool):
        """Test detailed metrics include complexity information."""
        mock_method = MagicMock()
        mock_method.element_type = "function"
        mock_method.complexity_score = 10

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [mock_method]
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})
        mock_analysis_result.annotations = []

        metrics = tool._extract_detailed_metrics(mock_analysis_result)
        assert "complexity" in metrics["metrics"]
        assert metrics["metrics"]["complexity"]["total"] == 10


class TestUniversalAnalyzeToolExtractStructureInfo:
    """Tests for _extract_structure_info method."""

    def test_extract_structure_info_empty(self, tool):
        """Test extracting structure info with empty elements."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.package = None

        structure = tool._extract_structure_info(mock_analysis_result)
        assert structure["structure"]["classes"] == []
        assert structure["structure"]["methods"] == []
        assert structure["structure"]["fields"] == []
        assert structure["structure"]["imports"] == []

    def test_extract_structure_info_with_classes(self, tool):
        """Test extracting structure info with class elements."""
        mock_class = MagicMock()
        mock_class.element_type = "class"
        mock_class.name = "TestClass"
        mock_class.to_summary_item = MagicMock(return_value={"name": "TestClass"})

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [mock_class]
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        structure = tool._extract_structure_info(mock_analysis_result)
        assert len(structure["structure"]["classes"]) == 1
        assert structure["structure"]["classes"][0]["name"] == "TestClass"


class TestUniversalAnalyzeToolExtractUniversalBasicMetrics:
    """Tests for _extract_universal_basic_metrics method."""

    def test_extract_universal_basic_metrics_empty(self, tool):
        """Test extracting universal basic metrics with empty elements."""
        analysis_dict = {"elements": [], "line_count": 100}

        metrics = tool._extract_universal_basic_metrics(analysis_dict)
        assert "metrics" in metrics
        assert metrics["metrics"]["elements"]["classes"] == 0
        assert metrics["metrics"]["elements"]["methods"] == 0

    def test_extract_universal_basic_metrics_with_elements(self, tool):
        """Test extracting universal basic metrics with elements."""
        mock_class = MagicMock()
        mock_class.element_type = "class"

        mock_method = MagicMock()
        mock_method.element_type = "function"

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [mock_class, mock_method]
        mock_analysis_result.line_count = 100
        mock_analysis_result.get_statistics = MagicMock(return_value={})

        metrics = tool._extract_basic_metrics(mock_analysis_result)
        assert metrics["metrics"]["elements"]["classes"] == 1
        assert metrics["metrics"]["elements"]["methods"] == 1


class TestUniversalAnalyzeToolExtractUniversalDetailedMetrics:
    """Tests for _extract_universal_detailed_metrics method."""

    def test_extract_universal_detailed_metrics_with_query_results(self, tool):
        """Test extracting universal detailed metrics with query results."""
        analysis_dict = {"elements": [], "line_count": 100, "query_results": {}}

        metrics = tool._extract_universal_detailed_metrics(analysis_dict)
        assert "query_results" in metrics


class TestUniversalAnalyzeToolExtractUniversalStructureInfo:
    """Tests for _extract_universal_structure_info method."""

    def test_extract_universal_structure_info(self, tool):
        """Test extracting universal structure info."""
        analysis_dict = {
            "elements": [],
            "line_count": 100,
            "structure": {},
            "queries_executed": [],
        }

        structure = tool._extract_universal_structure_info(analysis_dict)
        assert "structure" in structure
        assert "queries_executed" in structure


class TestUniversalAnalyzeToolGetAvailableQueries:
    """Tests for _get_available_queries method."""

    @pytest.mark.asyncio
    async def test_get_available_queries_java(self, tool):
        """Test getting available queries for Java."""
        result = await tool._get_available_queries("java")
        assert "language" in result
        assert result["language"] == "java"
        assert "queries" in result

    @pytest.mark.asyncio
    async def test_get_available_queries_python(self, tool):
        """Test getting available queries for Python."""
        mock_engine = MagicMock()
        mock_engine.get_supported_languages = MagicMock(
            return_value=["python", "javascript"]
        )
        tool.analysis_engine = mock_engine

        result = await tool._get_available_queries("python")
        assert "language" in result
        assert result["language"] == "python"
        assert "queries" in result
        assert "count" in result
