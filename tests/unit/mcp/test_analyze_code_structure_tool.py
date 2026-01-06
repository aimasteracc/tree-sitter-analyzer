#!/usr/bin/env python3
"""
Unit tests for AnalyzeCodeStructureTool.

Tests for analyze_code_structure tool which provides code structure
analysis with detailed overview tables (classes, methods, fields).
"""

from unittest.mock import AsyncMock, MagicMock, patch

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

    def test_set_project_path(self, tool):
        """Test setting project path."""
        tool.set_project_path("/new/project")
        assert tool.project_root == "/new/project"

    def test_set_project_path_updates_analysis_engine(self, tool):
        """Test that setting project path updates analysis engine."""
        tool.set_project_path("/new/project")
        # Analysis engine should be recreated with new project root
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
        with pytest.raises(ValueError, match="format_type must be one of"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_unsupported_format_type(self, tool):
        """Test validation fails when format_type is not supported."""
        arguments = {"file_path": "test.py", "format_type": "html"}
        with pytest.raises(ValueError, match="format_type must be one of"):
            tool.validate_arguments(arguments)

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


class TestAnalyzeCodeStructureToolExecute:
    """Tests for execute method."""

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
            with pytest.raises(ValueError, match="Invalid file path: File not found"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_success_full_format(self, tool, tmp_path):
        """Test successful execution with full format."""
        # Create a test Python file
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    def my_method(self):\n        pass\n")

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 3
        mock_analysis_result.language = "python"
        mock_analysis_result.file_path = str(test_file)
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.get_formatter_for_language",
                return_value=MagicMock(
                    format_structure=MagicMock(return_value="mocked_table_output")
                ),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry"
            ) as mock_registry,
        ):
            mock_registry.is_format_supported.return_value = True
            mock_registry.get_formatter.return_value.format.return_value = "Test output"

            arguments = {
                "file_path": str(test_file),
                "format_type": "full",
                "output_format": "json",
            }
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["format_type"] == "full"
            assert "table_output" in result
            assert "metadata" in result

    @pytest.mark.asyncio
    async def test_execute_success_compact_format(self, tool, tmp_path):
        """Test successful execution with compact format."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    pass\n")

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 2
        mock_analysis_result.language = "python"
        mock_analysis_result.file_path = str(test_file)
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.get_formatter_for_language",
                return_value=MagicMock(
                    format_structure=MagicMock(return_value="mocked_table_output")
                ),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry"
            ) as mock_registry,
        ):
            mock_registry.is_format_supported.return_value = True
            mock_registry.get_formatter.return_value.format.return_value = (
                "Compact output"
            )

            arguments = {
                "file_path": str(test_file),
                "format_type": "compact",
                "output_format": "json",
            }
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["format_type"] == "compact"
            assert "table_output" in result

    @pytest.mark.asyncio
    async def test_execute_success_csv_format(self, tool, tmp_path):
        """Test successful execution with CSV format."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    pass\n")

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 2
        mock_analysis_result.language = "python"
        mock_analysis_result.file_path = str(test_file)
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.get_formatter_for_language",
                return_value=MagicMock(
                    format_structure=MagicMock(return_value="mocked_table_output")
                ),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry"
            ) as mock_registry,
        ):
            mock_registry.is_format_supported.return_value = True
            mock_registry.get_formatter.return_value.format.return_value = "CSV output"

            arguments = {
                "file_path": str(test_file),
                "format_type": "csv",
                "output_format": "json",
            }
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["format_type"] == "csv"
            assert "table_output" in result

    @pytest.mark.asyncio
    async def test_execute_with_language_specified(self, tool, tmp_path):
        """Test execute with language explicitly specified."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    pass\n")

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 2
        mock_analysis_result.language = "python"
        mock_analysis_result.file_path = str(test_file)
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.get_formatter_for_language",
                return_value=MagicMock(
                    format_structure=MagicMock(return_value="mocked_table_output")
                ),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry"
            ) as mock_registry,
        ):
            mock_registry.is_format_supported.return_value = True
            mock_registry.get_formatter.return_value.format.return_value = "Test output"

            arguments = {"file_path": str(test_file), "language": "python"}
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_execute_with_file_output(self, tool, tmp_path):
        """Test execute with file output enabled."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    pass\n")

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 2
        mock_analysis_result.language = "python"
        mock_analysis_result.file_path = str(test_file)
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.get_formatter_for_language",
                return_value=MagicMock(
                    format_structure=MagicMock(return_value="mocked_table_output")
                ),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry"
            ) as mock_registry,
            patch.object(
                tool.file_output_manager,
                "save_to_file",
                return_value="test_analysis.txt",
            ) as mock_save,
        ):
            mock_registry.is_format_supported.return_value = True
            mock_registry.get_formatter.return_value.format.return_value = "Test output"

            arguments = {"file_path": str(test_file), "output_file": "output.txt"}
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["file_saved"] is True
            assert "output_file_path" in result
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_suppress_output(self, tool, tmp_path):
        """Test execute with suppress_output enabled."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    pass\n")

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 2
        mock_analysis_result.language = "python"
        mock_analysis_result.file_path = str(test_file)
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.get_formatter_for_language",
                return_value=MagicMock(
                    format_structure=MagicMock(return_value="mocked_table_output")
                ),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry"
            ) as mock_registry,
            patch.object(
                tool.file_output_manager,
                "save_to_file",
                return_value="test_analysis.txt",
            ) as mock_save,
        ):
            mock_registry.is_format_supported.return_value = True
            mock_registry.get_formatter.return_value.format.return_value = "Test output"

            # suppress_output only works when output_file is also specified
            arguments = {
                "file_path": str(test_file),
                "suppress_output": True,
                "output_file": "output.txt",
                "output_format": "json",
            }
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert "table_output" not in result  # Should be suppressed
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_output_format_json(self, tool, tmp_path):
        """Test execute with output_format='json'."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    pass\n")

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 2
        mock_analysis_result.language = "python"
        mock_analysis_result.file_path = str(test_file)
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.get_formatter_for_language",
                return_value=MagicMock(
                    format_structure=MagicMock(return_value="mocked_table_output")
                ),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry"
            ) as mock_registry,
        ):
            mock_registry.is_format_supported.return_value = True
            mock_registry.get_formatter.return_value.format.return_value = "Test output"

            arguments = {"file_path": str(test_file), "output_format": "json"}
            result = await tool.execute(arguments)

            assert result["success"] is True
            # JSON format should have full response structure
            assert "table_output" in result

    @pytest.mark.asyncio
    async def test_execute_with_output_format_toon(self, tool, tmp_path):
        """Test execute with output_format='toon'."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    pass\n")

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 2
        mock_analysis_result.language = "python"
        mock_analysis_result.file_path = str(test_file)
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.get_formatter_for_language",
                return_value=MagicMock(
                    format_structure=MagicMock(return_value="mocked_table_output")
                ),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry"
            ) as mock_registry,
        ):
            mock_registry.is_format_supported.return_value = True
            mock_registry.get_formatter.return_value.format.return_value = "Test output"

            arguments = {"file_path": str(test_file), "output_format": "toon"}
            result = await tool.execute(arguments)

            assert result["success"] is True
            # Toon format should have toon_content
            assert "toon_content" in result

    @pytest.mark.asyncio
    async def test_execute_analysis_failure(self, tool):
        """Test execute handles analysis engine failure."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(RuntimeError, match="Failed to analyze structure"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_unsupported_format_type(self, tool, tmp_path):
        """Test execute fails with unsupported format type."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    pass\n")

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 2
        mock_analysis_result.language = "python"
        mock_analysis_result.file_path = str(test_file)
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.get_formatter_for_language",
                return_value=MagicMock(
                    format_structure=MagicMock(return_value="mocked_table_output")
                ),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry"
            ) as mock_registry,
        ):
            mock_registry.is_format_supported.return_value = False

            arguments = {"file_path": str(test_file), "format_type": "unsupported"}
            with pytest.raises(ValueError, match="format_type must be one of"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_file_save_error(self, tool, tmp_path):
        """Test execute handles file save error."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    pass\n")

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 2
        mock_analysis_result.language = "python"
        mock_analysis_result.file_path = str(test_file)
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value=str(test_file)
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry.get_formatter_for_language",
                return_value=MagicMock(
                    format_structure=MagicMock(return_value="mocked_table_output")
                ),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry"
            ) as mock_registry,
            patch.object(
                tool.file_output_manager,
                "save_to_file",
                side_effect=Exception("Save error"),
            ),
        ):
            mock_registry.is_format_supported.return_value = True
            mock_registry.get_formatter.return_value.format.return_value = "Test output"

            arguments = {
                "file_path": str(test_file),
                "output_file": "output.txt",
                "output_format": "json",
            }
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["file_saved"] is False
            assert "file_save_error" in result

    @pytest.mark.asyncio
    async def test_extract_metadata_from_result(self, tool):
        """Test metadata extraction from analysis result."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.success = True
        mock_analysis_result.line_count = 100
        mock_analysis_result.language = "python"
        mock_analysis_result.file_path = "/test.py"
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []

        metadata = tool._convert_analysis_result_to_dict(mock_analysis_result)
        assert "statistics" in metadata
        assert metadata["statistics"]["total_lines"] == 100


class TestAnalyzeCodeStructureToolConvertParameters:
    """Tests for _convert_parameters method."""

    def test_convert_parameters_empty(self, tool):
        """Test converting empty parameters."""
        result = tool._convert_parameters([])
        assert result == []

    def test_convert_parameters_dict(self, tool):
        """Test converting dict parameters."""
        parameters = [{"name": "param1", "type": "string"}]
        result = tool._convert_parameters(parameters)
        assert len(result) == 1
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "string"

    def test_convert_parameters_object(self, tool):
        """Test converting object parameters."""
        mock_param = MagicMock()
        mock_param.name = "param1"
        mock_param.param_type = "string"
        parameters = [mock_param]
        result = tool._convert_parameters(parameters)
        assert len(result) == 1
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "string"


class TestAnalyzeCodeStructureToolGetMethodModifiers:
    """Tests for _get_method_modifiers method."""

    def test_get_method_modifiers_none(self, tool):
        """Test getting modifiers with no modifiers."""
        mock_method = MagicMock()
        mock_method.is_static = False
        mock_method.is_final = False
        mock_method.is_abstract = False

        result = tool._get_method_modifiers(mock_method)
        assert result == []

    def test_get_method_modifiers_static(self, tool):
        """Test getting static modifier."""
        mock_method = MagicMock()
        mock_method.is_static = True
        mock_method.is_final = False
        mock_method.is_abstract = False

        result = tool._get_method_modifiers(mock_method)
        assert result == ["static"]

    def test_get_method_modifiers_final(self, tool):
        """Test getting final modifier."""
        mock_method = MagicMock()
        mock_method.is_static = False
        mock_method.is_final = True
        mock_method.is_abstract = False

        result = tool._get_method_modifiers(mock_method)
        assert result == ["final"]

    def test_get_method_modifiers_abstract(self, tool):
        """Test getting abstract modifier."""
        mock_method = MagicMock()
        mock_method.is_static = False
        mock_method.is_final = False
        mock_method.is_abstract = True

        result = tool._get_method_modifiers(mock_method)
        assert result == ["abstract"]

    def test_get_method_modifiers_multiple(self, tool):
        """Test getting multiple modifiers."""
        mock_method = MagicMock()
        mock_method.is_static = True
        mock_method.is_final = True
        mock_method.is_abstract = True

        result = tool._get_method_modifiers(mock_method)
        assert len(result) == 3
        assert "static" in result
        assert "final" in result
        assert "abstract" in result


class TestAnalyzeCodeStructureToolGetFieldModifiers:
    """Tests for _get_field_modifiers method."""

    def test_get_field_modifiers_none(self, tool):
        """Test getting modifiers with no modifiers."""
        mock_field = MagicMock()
        mock_field.visibility = "public"
        mock_field.is_static = False
        mock_field.is_final = False

        result = tool._get_field_modifiers(mock_field)
        # Public visibility is added as a modifier (not package)
        assert result == ["public"]

    def test_get_field_modifiers_private(self, tool):
        """Test getting private visibility."""
        mock_field = MagicMock()
        mock_field.visibility = "private"
        mock_field.is_static = False
        mock_field.is_final = False

        result = tool._get_field_modifiers(mock_field)
        assert result == ["private"]

    def test_get_field_modifiers_static(self, tool):
        """Test getting static modifier."""
        mock_field = MagicMock()
        mock_field.visibility = "public"
        mock_field.is_static = True
        mock_field.is_final = False

        result = tool._get_field_modifiers(mock_field)
        # Public visibility is added as a modifier
        assert result == ["public", "static"]

    def test_get_field_modifiers_multiple(self, tool):
        """Test getting multiple modifiers."""
        mock_field = MagicMock()
        mock_field.visibility = "private"
        mock_field.is_static = True
        mock_field.is_final = True

        result = tool._get_field_modifiers(mock_field)
        assert len(result) == 3
        assert "private" in result
        assert "static" in result
        assert "final" in result


class TestAnalyzeCodeStructureToolGetMethodParameters:
    """Tests for _get_method_parameters method."""

    def test_get_method_parameters_empty(self, tool):
        """Test getting empty parameters."""
        mock_method = MagicMock()
        mock_method.parameters = []

        result = tool._get_method_parameters(mock_method)
        assert result == []

    def test_get_method_parameters_list_of_strings(self, tool):
        """Test getting parameters as list of strings."""
        mock_method = MagicMock()
        mock_method.parameters = ["str param1", "str param2"]

        result = tool._get_method_parameters(mock_method)
        assert len(result) == 2
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "str"
        assert result[1]["name"] == "param2"
        assert result[1]["type"] == "str"

    def test_get_method_parameters_list_of_dicts(self, tool):
        """Test getting parameters as list of dicts."""
        mock_method = MagicMock()
        mock_method.parameters = [{"name": "param1", "type": "string"}]

        result = tool._get_method_parameters(mock_method)
        assert len(result) == 1
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "string"

    def test_get_method_parameters_mixed(self, tool):
        """Test getting mixed parameters."""
        mock_method = MagicMock()
        # Use all string format (the implementation handles this case)
        mock_method.parameters = ["str param1", "int param2"]

        result = tool._get_method_parameters(mock_method)
        assert len(result) == 2
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "str"
        assert result[1]["name"] == "param2"
        assert result[1]["type"] == "int"
