"""
Unit tests for UniversalAnalyzeTool — execute method.

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
