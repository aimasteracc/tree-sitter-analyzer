#!/usr/bin/env python3
"""
Unit tests for AdvancedCommand.

Tests for advanced CLI command which provides detailed analysis
with statistics and metrics.
"""

from argparse import Namespace
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

    def test_execute_outputs_json_error_when_file_missing(
        self,
        tmp_path,
    ):
        """Missing file path with --output-format json emits failure envelope."""
        missing = tmp_path / "missing.ts"
        args = Namespace(
            file_path=str(missing),
            output_format="json",
            project_root=str(tmp_path),
            output_format_explicit=True,
            statistics=False,
            language=None,
        )
        command = AdvancedCommand(args)

        with patch(
            "tree_sitter_analyzer.cli.commands.base_command.output_json"
        ) as mock_output_json:
            rc = command.execute()

        assert rc == 1
        envelope = mock_output_json.call_args.args[0]
        assert envelope["success"] is False
        assert envelope["error_type"] == "validation"
        assert "file not found" in envelope["error"].lower()

    def test_execute_outputs_json_error_when_analysis_fails(self, tmp_path):
        """Analysis engine failure with --output-format json emits failure envelope."""
        target = tmp_path / "broken.ts"
        target.write_text("class A {}")
        args = Namespace(
            file_path=str(target),
            output_format="json",
            project_root=str(tmp_path),
            output_format_explicit=True,
            statistics=False,
            language="typescript",
        )
        command = AdvancedCommand(args)
        command.analysis_engine.analyze = AsyncMock(
            return_value=MagicMock(success=False, error_message="boom")
        )

        with patch(
            "tree_sitter_analyzer.cli.commands.base_command.output_json"
        ) as mock_output_json:
            rc = command.execute()

        assert rc == 1
        envelope = mock_output_json.call_args.args[0]
        assert envelope["success"] is False
        assert envelope["error_type"] == "runtime"
        assert "analysis failed: boom" in envelope["error"].lower()


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


class TestR37yCanonicalEnvelope:
    """r37y (dogfood): CLI ``--advanced`` JSON output was missing
    ``summary_line``, ``agent_summary``, and ``verdict`` entirely.
    Every other CLI/MCP surface emits them. This test pins the contract.
    """

    def test_full_analysis_emits_canonical_envelope(
        self, command, mock_analysis_result
    ):
        """``--advanced --format json`` must include summary_line + verdict + agent_summary."""
        command.args = MagicMock()
        command.args.statistics = False
        command.args.output_format = "json"

        captured: dict[str, object] = {}
        with patch(
            "tree_sitter_analyzer.cli.commands.advanced_command.output_json",
            side_effect=lambda d: captured.update(d),
        ):
            command._output_full_analysis(mock_analysis_result)

        assert captured.get("verdict") == "INFO"
        assert isinstance(captured.get("summary_line"), str)
        assert captured["summary_line"]  # non-empty
        agent_summary = captured.get("agent_summary")
        assert isinstance(agent_summary, dict)
        assert agent_summary["verdict"] == "INFO"
        assert agent_summary["summary_line"] == captured["summary_line"]
        # File path should appear in headline so agents can grep for it.
        assert mock_analysis_result.file_path in captured["summary_line"]

    def test_statistics_emits_canonical_envelope(self, command, mock_analysis_result):
        """``--advanced --statistics --format json`` also exposes envelope."""
        command.args = MagicMock()
        command.args.statistics = True
        command.args.output_format = "json"

        captured: dict[str, object] = {}
        with patch(
            "tree_sitter_analyzer.cli.commands.advanced_command.output_json",
            side_effect=lambda d: captured.update(d),
        ):
            command._output_statistics(mock_analysis_result)

        assert captured.get("verdict") == "INFO"
        assert isinstance(captured.get("summary_line"), str)
        assert captured["summary_line"]
        assert captured.get("agent_summary", {}).get("verdict") == "INFO"
        # mode=stats appears so callers can distinguish stats vs full mode.
        assert "mode=stats" in captured["summary_line"]

    def test_full_mode_label_differs_from_stats(self, command, mock_analysis_result):
        """summary_line carries mode= label to distinguish dispatch paths."""
        command.args = MagicMock()
        command.args.output_format = "json"
        command.args.statistics = False

        full_captured: dict[str, object] = {}
        with patch(
            "tree_sitter_analyzer.cli.commands.advanced_command.output_json",
            side_effect=lambda d: full_captured.update(d),
        ):
            command._output_full_analysis(mock_analysis_result)

        command.args.statistics = True
        stats_captured: dict[str, object] = {}
        with patch(
            "tree_sitter_analyzer.cli.commands.advanced_command.output_json",
            side_effect=lambda d: stats_captured.update(d),
        ):
            command._output_statistics(mock_analysis_result)

        assert "mode=full" in full_captured["summary_line"]
        assert "mode=stats" in stats_captured["summary_line"]
