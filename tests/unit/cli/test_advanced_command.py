#!/usr/bin/env python3
"""
Unit tests for AdvancedCommand.

Tests for advanced CLI command which provides detailed analysis
with statistics and metrics.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.advanced_command import AdvancedCommand
from tree_sitter_analyzer.models import AnalysisResult


@pytest.fixture
def mock_args():
    """Create mock arguments for testing."""
    from argparse import Namespace

    return Namespace(
        file_path="/test/file.py",
        statistics=False,
        output_format="text",
        toon_use_tabs=False,
    )


@pytest.fixture
def command(mock_args):
    """Create an AdvancedCommand instance for testing."""
    return AdvancedCommand(mock_args)


@pytest.fixture
def mock_analysis_result():
    """Create a mock analysis result."""
    result = MagicMock(spec=AnalysisResult)
    result.success = True
    result.line_count = 100
    result.node_count = 50
    result.elements = []
    result.file_path = "/test/file.py"
    result.language = "python"
    result.analysis_time = 0.5
    return result


class TestAdvancedCommandInit:
    """Tests for AdvancedCommand initialization."""

    def test_init(self, command):
        """Test initialization."""
        assert command is not None
        assert hasattr(command, "execute_async")
        assert hasattr(command, "analyze_file")

    def test_init_with_args(self, command):
        """Test initialization with arguments."""
        command.args = MagicMock()
        command.args.statistics = False
        command.args.output_format = "text"
        assert command.args.statistics is False
        assert command.args.output_format == "text"


class TestAdvancedCommandExecuteAsync:
    """Tests for execute_async method."""

    @pytest.mark.asyncio
    async def test_execute_async_success(self, command, mock_analysis_result):
        """Test successful execution."""
        with (
            patch.object(
                command,
                "analyze_file",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch.object(command, "_output_full_analysis") as mock_output,
        ):
            command.args = MagicMock()
            command.args.statistics = False

            result = await command.execute_async("python")

            assert result == 0
            mock_output.assert_called_once_with(mock_analysis_result)

    @pytest.mark.asyncio
    async def test_execute_async_with_statistics(self, command, mock_analysis_result):
        """Test execution with statistics flag."""
        with (
            patch.object(
                command,
                "analyze_file",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch.object(command, "_output_statistics") as mock_output,
        ):
            command.args = MagicMock()
            command.args.statistics = True

            result = await command.execute_async("python")

            assert result == 0
            mock_output.assert_called_once_with(mock_analysis_result)

    @pytest.mark.asyncio
    async def test_execute_async_no_analysis_result(self, command):
        """Test execution when analysis returns None."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock, return_value=None
        ):
            command.args = MagicMock()
            command.args.statistics = False

            result = await command.execute_async("python")

            assert result == 1


class TestAdvancedCommandCalculateFileMetrics:
    """Tests for _calculate_file_metrics method."""

    def test_calculate_file_metrics_python(self, command, tmp_path):
        """Test calculating metrics for Python file."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            "# This is a comment\n"
            "def hello():\n"
            "    print('world')\n"
            "\n"
            "# Another comment\n"
        )

        metrics = command._calculate_file_metrics(str(test_file), "python")

        assert metrics["total_lines"] == 5
        assert metrics["code_lines"] == 2
        assert metrics["comment_lines"] == 2
        assert metrics["blank_lines"] == 1

    def test_calculate_file_metrics_java(self, command, tmp_path):
        """Test calculating metrics for Java file."""
        test_file = tmp_path / "test.java"
        test_file.write_text(
            "/* Multi-line\n"
            "   comment */\n"
            "public class Test {\n"
            "    // Single line comment\n"
            "    public void method() {}\n"
            "}\n"
        )

        metrics = command._calculate_file_metrics(str(test_file), "java")

        assert metrics["total_lines"] == 6
        assert metrics["code_lines"] == 3
        assert metrics["comment_lines"] == 3
        assert metrics["blank_lines"] == 0

    def test_calculate_file_metrics_sql(self, command, tmp_path):
        """Test calculating metrics for SQL file."""
        test_file = tmp_path / "test.sql"
        test_file.write_text(
            "-- SQL comment\nSELECT * FROM table;\n\n-- Another comment\n"
        )

        metrics = command._calculate_file_metrics(str(test_file), "sql")

        assert metrics["total_lines"] == 4
        assert metrics["code_lines"] == 1
        assert metrics["comment_lines"] == 2
        assert metrics["blank_lines"] == 1

    def test_calculate_file_metrics_html(self, command, tmp_path):
        """Test calculating metrics for HTML file."""
        test_file = tmp_path / "test.html"
        test_file.write_text("<!-- HTML comment -->\n<div>Hello</div>\n\n")

        metrics = command._calculate_file_metrics(str(test_file), "html")

        assert metrics["total_lines"] == 3
        assert metrics["code_lines"] == 1
        assert metrics["comment_lines"] == 1
        assert metrics["blank_lines"] == 1

    def test_calculate_file_metrics_empty_file(self, command, tmp_path):
        """Test calculating metrics for empty file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("")

        metrics = command._calculate_file_metrics(str(test_file), "python")

        assert metrics["total_lines"] == 0
        assert metrics["code_lines"] == 0
        assert metrics["comment_lines"] == 0
        assert metrics["blank_lines"] == 0

    def test_calculate_file_metrics_file_read_error(self, command):
        """Test calculating metrics when file read fails."""
        metrics = command._calculate_file_metrics("/nonexistent/file.py", "python")

        # Should return default values on error
        assert metrics["total_lines"] == 0
        assert metrics["code_lines"] == 0
        assert metrics["comment_lines"] == 0
        assert metrics["blank_lines"] == 0


class TestAdvancedCommandOutputStatistics:
    """Tests for _output_statistics method."""

    def test_output_statistics_text(self, command, mock_analysis_result):
        """Test output statistics in text format."""
        command.args = MagicMock()
        command.args.output_format = "text"

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.advanced_command.output_section"
            ) as mock_section,
            patch(
                "tree_sitter_analyzer.cli.commands.advanced_command.output_data"
            ) as mock_data,
        ):
            command._output_statistics(mock_analysis_result)

            mock_section.assert_called_once_with("Statistics")
            assert (
                mock_data.call_count >= 4
            )  # line_count, element_count, node_count, language

    def test_output_statistics_json(self, command, mock_analysis_result):
        """Test output statistics in JSON format."""
        command.args = MagicMock()
        command.args.output_format = "json"

        with (
            patch("tree_sitter_analyzer.cli.commands.advanced_command.output_section"),
            patch(
                "tree_sitter_analyzer.cli.commands.advanced_command.output_json"
            ) as mock_json,
        ):
            command._output_statistics(mock_analysis_result)

            mock_json.assert_called_once()
            call_args = mock_json.call_args[0][0]
            assert call_args["line_count"] == 100
            assert call_args["element_count"] == 0
            assert call_args["node_count"] == 50
            assert call_args["language"] == "python"

    def test_output_statistics_toon(self, command, mock_analysis_result):
        """Test output statistics in toon format."""
        command.args = MagicMock()
        command.args.output_format = "toon"
        command.args.toon_use_tabs = False

        with (
            patch("tree_sitter_analyzer.cli.commands.advanced_command.output_section"),
            patch(
                "tree_sitter_analyzer.cli.commands.advanced_command.ToonFormatter"
            ) as mock_formatter,
        ):
            mock_formatter_instance = MagicMock()
            mock_formatter.return_value = mock_formatter_instance
            mock_formatter_instance.format.return_value = "formatted_output"

            command._output_statistics(mock_analysis_result)

            mock_formatter.assert_called_once_with(use_tabs=False)
            mock_formatter_instance.format.assert_called_once()


class TestAdvancedCommandOutputFullAnalysis:
    """Tests for _output_full_analysis method."""

    def test_output_full_analysis_text(self, command, mock_analysis_result):
        """Test output full analysis in text format."""
        command.args = MagicMock()
        command.args.output_format = "text"

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.advanced_command.output_section"
            ) as mock_section,
            patch("tree_sitter_analyzer.cli.commands.advanced_command.output_data"),
            patch.object(command, "_output_text_analysis") as mock_text,
        ):
            command._output_full_analysis(mock_analysis_result)

            mock_section.assert_called_once_with("Advanced Analysis Results")
            mock_text.assert_called_once_with(mock_analysis_result)

    def test_output_full_analysis_json(self, command, mock_analysis_result):
        """Test output full analysis in JSON format."""
        command.args = MagicMock()
        command.args.output_format = "json"

        with (
            patch("tree_sitter_analyzer.cli.commands.advanced_command.output_section"),
            patch(
                "tree_sitter_analyzer.cli.commands.advanced_command.output_json"
            ) as mock_json,
        ):
            command._output_full_analysis(mock_analysis_result)

            mock_json.assert_called_once()
            call_args = mock_json.call_args[0][0]
            assert call_args["file_path"] == "/test/file.py"
            assert call_args["language"] == "python"
            assert call_args["line_count"] == 100
            assert call_args["element_count"] == 0
            assert call_args["success"] is True

    def test_output_full_analysis_toon(self, command, mock_analysis_result):
        """Test output full analysis in toon format."""
        command.args = MagicMock()
        command.args.output_format = "toon"
        command.args.toon_use_tabs = False

        with (
            patch("tree_sitter_analyzer.cli.commands.advanced_command.output_section"),
            patch(
                "tree_sitter_analyzer.cli.commands.advanced_command.ToonFormatter"
            ) as mock_formatter,
        ):
            mock_formatter_instance = MagicMock()
            mock_formatter.return_value = mock_formatter_instance
            mock_formatter_instance.format.return_value = "formatted_output"

            command._output_full_analysis(mock_analysis_result)

            mock_formatter.assert_called_once_with(use_tabs=False)
            mock_formatter_instance.format.assert_called_once()


class TestAdvancedCommandOutputTextAnalysis:
    """Tests for _output_text_analysis method."""

    def test_output_text_analysis_basic(self, command, mock_analysis_result):
        """Test basic text analysis output."""
        with (
            patch(
                "tree_sitter_analyzer.cli.commands.advanced_command.output_data"
            ) as mock_data,
            patch.object(
                command,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                },
            ),
        ):
            command._output_text_analysis(mock_analysis_result)

            # Should output multiple data lines
            assert mock_data.call_count >= 10

    def test_output_text_analysis_no_methods(self, command, mock_analysis_result):
        """Test text analysis when no methods present."""
        mock_analysis_result.elements = []

        with (
            patch(
                "tree_sitter_analyzer.cli.commands.advanced_command.output_data"
            ) as mock_data,
            patch.object(
                command,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                },
            ),
        ):
            command._output_text_analysis(mock_analysis_result)

            # Verify complexity is 0 when no methods
            output_calls = [str(call) for call in mock_data.call_args_list]
            assert any("Total Complexity: 0" in call for call in output_calls)
            assert any("Average Complexity: 0.00" in call for call in output_calls)
            assert any("Max Complexity: 0" in call for call in output_calls)
