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
    _convert_analysis_result,
)


@pytest.fixture
def tool():
    """Create an AnalyzeCodeStructureTool instance for testing."""
    return AnalyzeCodeStructureTool()


@pytest.fixture
def tool_with_project_root():
    """Create an AnalyzeCodeStructureTool instance with a project root."""
    return AnalyzeCodeStructureTool(project_root="/test/project")


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
            result = await tool.execute(arguments)

            assert result["success"] is False
            assert result["verdict"] == "ERROR"
            assert result["error"] == "Failed to analyze structure for file: test.py"

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
            with pytest.raises(ValueError, match="Invalid format_type"):
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

        metadata = _convert_analysis_result(mock_analysis_result)
        assert "statistics" in metadata
        assert metadata["statistics"]["total_lines"] == 100
