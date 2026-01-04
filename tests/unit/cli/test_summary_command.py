#!/usr/bin/env python3
"""
Tests for SummaryCommand
"""

from argparse import Namespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.summary_command import SummaryCommand


@pytest.fixture
def mock_args():
    """Create mock args for BaseCommand initialization."""
    return Namespace(
        file_path="test.py",
        file="test.py",
        query_key=None,
        query_string=None,
        advanced=False,
        table=None,
        structure=False,
        summary=True,
        output_format="text",
        toon_use_tabs=False,
        statistics=False,
        output_file=None,
        suppress_output=False,
        format_type="full",
        language=None,
        include_details=True,
        include_complexity=True,
        include_guidance=False,
        metrics_only=False,
        output_format_param="json",
        format_type_param="full",
        language_param=None,
        filter_expression=None,
        filter=None,
        result_format="json",
        query_key_param=None,
        query_string_param=None,
    )


@pytest.fixture
def command(mock_args):
    """Create SummaryCommand instance for testing."""
    return SummaryCommand(mock_args)


class TestSummaryCommandInit:
    """Tests for SummaryCommand initialization."""

    def test_init(self, command):
        """Test SummaryCommand initialization."""
        assert command is not None
        assert isinstance(command, SummaryCommand)
        assert hasattr(command, "args")

    def test_init_with_args(self, mock_args):
        """Test SummaryCommand initialization with args."""
        command = SummaryCommand(mock_args)
        assert command.args == mock_args


class TestSummaryCommandExecuteAsync:
    """Tests for SummaryCommand.execute_async method."""

    @pytest.mark.asyncio
    async def test_execute_async_success(self, command):
        """Test execute_async returns 0 on success."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_analyze.return_value = MagicMock(
                file_path="test.py",
                language="python",
                line_count=10,
                elements=[],
                node_count=0,
                success=True,
                analysis_time=0.1,
            )
            with patch.object(command, "_output_summary_analysis"):
                result = await command.execute_async("python")
                assert result == 0
                mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_no_analysis_result(self, command):
        """Test execute_async returns 1 when no analysis result."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_analyze.return_value = None
            result = await command.execute_async("python")
            assert result == 1
            mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_calls_output_summary_analysis(self, command):
        """Test execute_async calls _output_summary_analysis."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_analyze.return_value = MagicMock(
                file_path="test.py",
                language="python",
                line_count=10,
                elements=[],
                node_count=0,
                success=True,
                analysis_time=0.1,
            )
            with patch.object(command, "_output_summary_analysis") as mock_output:
                await command.execute_async("python")
                mock_output.assert_called_once()


class TestSummaryCommandOutputSummaryAnalysis:
    """Tests for SummaryCommand._output_summary_analysis method."""

    def test_output_summary_analysis_text(self, command):
        """Test _output_summary_analysis with text format."""
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        command.args.output_format = "text"
        command.args.summary = "classes,methods"
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_section"
        ) as mock_section:
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.output_data"
            ) as mock_data:
                command._output_summary_analysis(analysis_result)
                mock_section.assert_called_once_with("Summary Results")
                assert mock_data.call_count > 0

    def test_output_summary_analysis_json(self, command):
        """Test _output_summary_analysis with JSON format."""
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        command.args.output_format = "json"
        command.args.summary = "classes,methods"
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_json"
        ) as mock_json:
            command._output_summary_analysis(analysis_result)
            mock_json.assert_called_once()

    def test_output_summary_analysis_toon(self, command):
        """Test _output_summary_analysis with TOON format."""
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        command.args.output_format = "toon"
        command.args.summary = "classes,methods"
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.ToonFormatter"
        ) as mock_formatter_class:
            mock_formatter = MagicMock()
            mock_formatter.format.return_value = "formatted_output"
            mock_formatter_class.return_value = mock_formatter
            with patch("builtins.print") as mock_print:
                command._output_summary_analysis(analysis_result)
                # formatter.format is called once, and print is called twice:
                # 1. output_section header
                # 2. formatted output
                mock_formatter_class.assert_called_once_with(use_tabs=False)
                mock_formatter.format.assert_called_once()
                assert mock_print.call_count == 2
                # First call is to section header
                assert mock_print.call_args_list[0][0][0] == "\n--- Summary Results ---"
                # Second call is to formatted output
                assert mock_print.call_args_list[1][0][0] == "formatted_output"

    def test_output_summary_analysis_default_types(self, command):
        """Test _output_summary_analysis with default types."""
        from tree_sitter_analyzer.constants import (
            ELEMENT_TYPE_CLASS,
            ELEMENT_TYPE_FUNCTION,
        )

        # Create mock elements with correct types
        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.element_type = ELEMENT_TYPE_CLASS

        mock_method = MagicMock()
        mock_method.name = "testMethod"
        mock_method.element_type = ELEMENT_TYPE_FUNCTION

        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 10
        analysis_result.elements = [mock_class, mock_method]
        analysis_result.node_count = 2
        analysis_result.success = True
        analysis_result.analysis_time = 0.1

        command.args.output_format = "text"
        command.args.summary = None  # Should default to "classes,methods"
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_section"
        ) as mock_section:
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.output_data"
            ) as mock_data:
                command._output_summary_analysis(analysis_result)
                mock_section.assert_called_once_with("Summary Results")
                assert mock_data.call_count > 0

    def test_output_summary_analysis_custom_types(self, command):
        """Test _output_summary_analysis with custom types."""
        from tree_sitter_analyzer.constants import (
            ELEMENT_TYPE_CLASS,
            ELEMENT_TYPE_VARIABLE,
        )

        # Create mock elements with correct types
        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.element_type = ELEMENT_TYPE_CLASS

        mock_field = MagicMock()
        mock_field.name = "testField"
        mock_field.element_type = ELEMENT_TYPE_VARIABLE

        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 10
        analysis_result.elements = [mock_class, mock_field]
        analysis_result.node_count = 2
        analysis_result.success = True
        analysis_result.analysis_time = 0.1

        command.args.output_format = "text"
        command.args.summary = "classes,fields"
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_section"
        ) as mock_section:
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.output_data"
            ) as mock_data:
                command._output_summary_analysis(analysis_result)
                mock_section.assert_called_once_with("Summary Results")
                assert mock_data.call_count > 0

    def test_output_summary_analysis_all_types(self, command):
        """Test _output_summary_analysis with all types."""
        from tree_sitter_analyzer.constants import (
            ELEMENT_TYPE_CLASS,
            ELEMENT_TYPE_FUNCTION,
            ELEMENT_TYPE_IMPORT,
            ELEMENT_TYPE_VARIABLE,
        )

        # Create mock elements with correct types
        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.element_type = ELEMENT_TYPE_CLASS

        mock_method = MagicMock()
        mock_method.name = "testMethod"
        mock_method.element_type = ELEMENT_TYPE_FUNCTION

        mock_field = MagicMock()
        mock_field.name = "testField"
        mock_field.element_type = ELEMENT_TYPE_VARIABLE

        mock_import = MagicMock()
        mock_import.name = "testImport"
        mock_import.element_type = ELEMENT_TYPE_IMPORT

        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 10
        analysis_result.elements = [mock_class, mock_method, mock_field, mock_import]
        analysis_result.node_count = 4
        analysis_result.success = True
        analysis_result.analysis_time = 0.1

        command.args.output_format = "text"
        command.args.summary = "classes,methods,fields,imports"
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_section"
        ) as mock_section:
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.output_data"
            ) as mock_data:
                command._output_summary_analysis(analysis_result)
                mock_section.assert_called_once_with("Summary Results")
                assert mock_data.call_count > 0


class TestSummaryCommandOutputTextFormat:
    """Tests for SummaryCommand._output_text_format method."""

    def test_output_text_format_basic(self, command):
        """Test _output_text_format with basic summary."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "classes": [],
                "methods": [],
            },
        }
        requested_types = ["classes", "methods"]
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_data:
            command._output_text_format(summary_data, requested_types)
            assert mock_data.call_count > 0

    def test_output_text_format_with_classes(self, command):
        """Test _output_text_format with classes."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "classes": [{"name": "TestClass"}],
                "methods": [],
            },
        }
        requested_types = ["classes"]
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_data:
            command._output_text_format(summary_data, requested_types)
            calls = [str(call) for call in mock_data.call_args_list]
            assert any("Classes (1 items):" in call for call in calls)
            assert any("TestClass" in call for call in calls)

    def test_output_text_format_with_methods(self, command):
        """Test _output_text_format with methods."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "classes": [],
                "methods": [{"name": "testMethod"}],
            },
        }
        requested_types = ["methods"]
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_data:
            command._output_text_format(summary_data, requested_types)
            calls = [str(call) for call in mock_data.call_args_list]
            assert any("Methods (1 items):" in call for call in calls)
            assert any("testMethod" in call for call in calls)

    def test_output_text_format_with_fields(self, command):
        """Test _output_text_format with fields."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "classes": [],
                "methods": [],
                "fields": [{"name": "testField"}],
            },
        }
        requested_types = ["fields"]
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_data:
            command._output_text_format(summary_data, requested_types)
            calls = [str(call) for call in mock_data.call_args_list]
            assert any("Fields (1 items):" in call for call in calls)
            assert any("testField" in call for call in calls)

    def test_output_text_format_with_imports(self, command):
        """Test _output_text_format with imports."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "classes": [],
                "methods": [],
                "imports": [{"name": "testImport"}],
            },
        }
        requested_types = ["imports"]
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_data:
            command._output_text_format(summary_data, requested_types)
            calls = [str(call) for call in mock_data.call_args_list]
            assert any("Imports (1 items):" in call for call in calls)
            assert any("testImport" in call for call in calls)

    def test_output_text_format_multiple_types(self, command):
        """Test _output_text_format with multiple types."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "classes": [{"name": "TestClass"}],
                "methods": [{"name": "testMethod"}],
            },
        }
        requested_types = ["classes", "methods"]
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_data:
            command._output_text_format(summary_data, requested_types)
            calls = [str(call) for call in mock_data.call_args_list]
            assert any("Classes (1 items):" in call for call in calls)
            assert any("TestClass" in call for call in calls)
            assert any("Methods (1 items):" in call for call in calls)
            assert any("testMethod" in call for call in calls)

    def test_output_text_format_empty_elements(self, command):
        """Test _output_text_format with empty elements."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "classes": [],
                "methods": [],
            },
        }
        requested_types = ["classes", "methods"]
        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_data:
            command._output_text_format(summary_data, requested_types)
            calls = [str(call) for call in mock_data.call_args_list]
            assert any("Classes (0 items):" in call for call in calls)
            assert any("Methods (0 items):" in call for call in calls)
