#!/usr/bin/env python3
"""
Comprehensive tests for tree_sitter_analyzer.cli.commands.summary_command module.

This module provides comprehensive test coverage for the SummaryCommand class.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.summary_command import SummaryCommand
from tree_sitter_analyzer.models import AnalysisResult


class TestSummaryCommandInitialization:
    """Test SummaryCommand initialization."""

    def test_init_with_args(self):
        """Test initialization with args."""
        args = MagicMock()
        cmd = SummaryCommand(args)
        assert cmd.args == args

    def test_inherits_from_base_command(self):
        """Test that SummaryCommand inherits from BaseCommand."""
        from tree_sitter_analyzer.cli.commands.base_command import BaseCommand

        assert issubclass(SummaryCommand, BaseCommand)


class TestExecuteAsync:
    """Test execute_async method."""

    @pytest.fixture
    def command(self):
        """Create a SummaryCommand instance."""
        args = MagicMock()
        args.summary = "classes,methods"
        args.output_format = "text"
        return SummaryCommand(args)

    @pytest.mark.asyncio
    async def test_execute_async_success(self, command):
        """Test successful execute_async."""
        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = []
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch.object(
            command, "analyze_file", new_callable=AsyncMock, return_value=mock_result
        ):
            with patch.object(command, "_output_summary_analysis"):
                result = await command.execute_async("python")

        assert result == 0

    @pytest.mark.asyncio
    async def test_execute_async_with_none_result(self, command):
        """Test execute_async when analyze_file returns None."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock, return_value=None
        ):
            result = await command.execute_async("python")

        assert result == 1

    @pytest.mark.asyncio
    async def test_execute_async_calls_output_summary(self, command):
        """Test that execute_async calls _output_summary_analysis."""
        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = []
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch.object(
            command, "analyze_file", new_callable=AsyncMock, return_value=mock_result
        ):
            with patch.object(command, "_output_summary_analysis") as mock_output:
                await command.execute_async("python")

        mock_output.assert_called_once_with(mock_result)


class TestOutputSummaryAnalysis:
    """Test _output_summary_analysis method."""

    @pytest.fixture
    def command(self):
        """Create a SummaryCommand instance."""
        args = MagicMock()
        args.summary = "classes,methods"
        args.output_format = "text"
        return SummaryCommand(args)

    def test_output_summary_with_classes_and_methods(self, command):
        """Test outputting summary with classes and methods."""
        # Create mock elements
        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.element_type = "class_declaration"

        mock_method = MagicMock()
        mock_method.name = "test_method"
        mock_method.element_type = "function_definition"

        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = [mock_class, mock_method]
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch("tree_sitter_analyzer.cli.commands.summary_command.output_section"):
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
            ) as mock_is_type:
                # Mock is_element_of_type to return appropriate values
                def side_effect(element, element_type):
                    if element == mock_class and element_type == "class_declaration":
                        return True
                    if element == mock_method and element_type == "function_definition":
                        return True
                    return False

                mock_is_type.side_effect = side_effect

                with patch.object(command, "_output_text_format") as mock_text_output:
                    command._output_summary_analysis(mock_result)

                # Verify text output was called
                assert mock_text_output.called

    def test_output_summary_with_json_format(self, command):
        """Test outputting summary in JSON format."""
        command.args.output_format = "json"

        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = []
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch("tree_sitter_analyzer.cli.commands.summary_command.output_section"):
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
            ):
                with patch(
                    "tree_sitter_analyzer.cli.commands.summary_command.output_json"
                ) as mock_json:
                    command._output_summary_analysis(mock_result)

                assert mock_json.called

    def test_output_summary_with_custom_types(self, command):
        """Test outputting summary with custom types."""
        command.args.summary = "classes,methods,fields,imports"

        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.element_type = "class_declaration"

        mock_method = MagicMock()
        mock_method.name = "test_method"
        mock_method.element_type = "function_definition"

        mock_field = MagicMock()
        mock_field.name = "test_field"
        mock_field.element_type = "variable_declaration"

        mock_import = MagicMock()
        mock_import.name = "os"
        mock_import.element_type = "import_statement"

        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = [mock_class, mock_method, mock_field, mock_import]
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch("tree_sitter_analyzer.cli.commands.summary_command.output_section"):
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
            ) as mock_is_type:

                def side_effect(element, element_type):
                    type_map = {
                        mock_class: "class_declaration",
                        mock_method: "function_definition",
                        mock_field: "variable_declaration",
                        mock_import: "import_statement",
                    }
                    return element in type_map and type_map[element] == element_type

                mock_is_type.side_effect = side_effect

                with patch.object(command, "_output_text_format") as mock_text_output:
                    command._output_summary_analysis(mock_result)

                # Verify the call was made and check the data
                assert mock_text_output.called
                call_args = mock_text_output.call_args[0]
                summary_data = call_args[0]

                assert "classes" in summary_data["summary"]
                assert "methods" in summary_data["summary"]
                assert "fields" in summary_data["summary"]
                assert "imports" in summary_data["summary"]

    def test_output_summary_with_empty_summary_types(self, command):
        """Test outputting summary with empty summary types (uses defaults)."""
        command.args.summary = ""

        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = []
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch("tree_sitter_analyzer.cli.commands.summary_command.output_section"):
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
            ):
                with patch.object(command, "_output_text_format") as mock_text_output:
                    command._output_summary_analysis(mock_result)

                # Should use default types: classes, methods
                assert mock_text_output.called
                call_args = mock_text_output.call_args[0]
                requested_types = call_args[1]
                assert requested_types == ["classes", "methods"]

    def test_output_summary_with_none_summary_types(self, command):
        """Test outputting summary with None summary types."""
        command.args.summary = None

        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = []
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch("tree_sitter_analyzer.cli.commands.summary_command.output_section"):
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
            ):
                with patch.object(command, "_output_text_format") as mock_text_output:
                    command._output_summary_analysis(mock_result)

                # Should use default types: classes, methods
                assert mock_text_output.called
                call_args = mock_text_output.call_args[0]
                requested_types = call_args[1]
                assert requested_types == ["classes", "methods"]

    def test_output_summary_with_whitespace_in_types(self, command):
        """Test outputting summary with whitespace in types."""
        command.args.summary = "  classes  ,  methods  ,  fields  "

        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = []
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch("tree_sitter_analyzer.cli.commands.summary_command.output_section"):
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
            ):
                with patch.object(command, "_output_text_format") as mock_text_output:
                    command._output_summary_analysis(mock_result)

                # Should strip whitespace
                assert mock_text_output.called
                call_args = mock_text_output.call_args[0]
                requested_types = call_args[1]
                assert requested_types == ["classes", "methods", "fields"]

    def test_output_summary_filters_elements_correctly(self, command):
        """Test that elements are filtered correctly by type."""
        command.args.summary = "classes"

        mock_class = MagicMock()
        mock_class.name = "TestClass"

        mock_method = MagicMock()
        mock_method.name = "test_method"

        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = [mock_class, mock_method]
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch("tree_sitter_analyzer.cli.commands.summary_command.output_section"):
            # Import constants to use real values
            from tree_sitter_analyzer.constants import (
                ELEMENT_TYPE_CLASS,
                ELEMENT_TYPE_FUNCTION,
            )

            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
            ) as mock_is_type:
                # Only mock_class should match class type
                def side_effect(element, element_type):
                    if element == mock_class and element_type == ELEMENT_TYPE_CLASS:
                        return True
                    if element == mock_method and element_type == ELEMENT_TYPE_FUNCTION:
                        return True
                    return False

                mock_is_type.side_effect = side_effect

                with patch.object(command, "_output_text_format") as mock_text_output:
                    command._output_summary_analysis(mock_result)

                call_args = mock_text_output.call_args[0]
                summary_data = call_args[0]

                # Should only have classes, not methods (since only classes were requested)
                assert "classes" in summary_data["summary"]
                assert len(summary_data["summary"]["classes"]) == 1
                assert summary_data["summary"]["classes"][0]["name"] == "TestClass"
                # methods should not be in summary since not requested
                assert "methods" not in summary_data["summary"]


class TestOutputTextFormat:
    """Test _output_text_format method."""

    @pytest.fixture
    def command(self):
        """Create a SummaryCommand instance."""
        args = MagicMock()
        args.summary = "classes,methods"
        args.output_format = "text"
        return SummaryCommand(args)

    def test_output_text_format_with_classes(self, command):
        """Test text format output with classes."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "classes": [
                    {"name": "Class1"},
                    {"name": "Class2"},
                ]
            },
        }
        requested_types = ["classes"]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_output:
            command._output_text_format(summary_data, requested_types)

            # Check that output_data was called with expected values
            calls = [str(call) for call in mock_output.call_args_list]
            assert any("test.py" in str(call) for call in calls)
            assert any("python" in str(call) for call in calls)
            assert any("Classes" in str(call) for call in calls)
            assert any("Class1" in str(call) for call in calls)
            assert any("Class2" in str(call) for call in calls)

    def test_output_text_format_with_methods(self, command):
        """Test text format output with methods."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "methods": [
                    {"name": "method1"},
                    {"name": "method2"},
                ]
            },
        }
        requested_types = ["methods"]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_output:
            command._output_text_format(summary_data, requested_types)

            calls = [str(call) for call in mock_output.call_args_list]
            assert any("Methods" in str(call) for call in calls)
            assert any("method1" in str(call) for call in calls)
            assert any("method2" in str(call) for call in calls)

    def test_output_text_format_with_fields(self, command):
        """Test text format output with fields."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "fields": [
                    {"name": "field1"},
                ]
            },
        }
        requested_types = ["fields"]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_output:
            command._output_text_format(summary_data, requested_types)

            calls = [str(call) for call in mock_output.call_args_list]
            assert any("Fields" in str(call) for call in calls)
            assert any("field1" in str(call) for call in calls)

    def test_output_text_format_with_imports(self, command):
        """Test text format output with imports."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "imports": [
                    {"name": "os"},
                    {"name": "sys"},
                ]
            },
        }
        requested_types = ["imports"]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_output:
            command._output_text_format(summary_data, requested_types)

            calls = [str(call) for call in mock_output.call_args_list]
            assert any("Imports" in str(call) for call in calls)
            assert any("os" in str(call) for call in calls)
            assert any("sys" in str(call) for call in calls)

    def test_output_text_format_with_multiple_types(self, command):
        """Test text format output with multiple types."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "classes": [{"name": "MyClass"}],
                "methods": [{"name": "my_method"}],
                "fields": [{"name": "my_field"}],
                "imports": [{"name": "os"}],
            },
        }
        requested_types = ["classes", "methods", "fields", "imports"]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_output:
            command._output_text_format(summary_data, requested_types)

            calls = [str(call) for call in mock_output.call_args_list]
            assert any("Classes" in str(call) for call in calls)
            assert any("Methods" in str(call) for call in calls)
            assert any("Fields" in str(call) for call in calls)
            assert any("Imports" in str(call) for call in calls)

    def test_output_text_format_with_empty_elements(self, command):
        """Test text format output with empty elements."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {"classes": []},
        }
        requested_types = ["classes"]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_output:
            command._output_text_format(summary_data, requested_types)

            calls = [str(call) for call in mock_output.call_args_list]
            # Should show 0 items
            assert any(
                "0 items" in str(call) or "(0 items)" in str(call) for call in calls
            )

    def test_output_text_format_with_unknown_type(self, command):
        """Test text format output with unknown type."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {"unknown_type": [{"name": "test"}]},
        }
        requested_types = ["unknown_type"]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_output:
            command._output_text_format(summary_data, requested_types)

            # Should still output with the unknown type name
            calls = [str(call) for call in mock_output.call_args_list]
            assert any("unknown_type" in str(call) for call in calls)

    def test_output_text_format_displays_counts(self, command):
        """Test that text format displays counts correctly."""
        summary_data = {
            "file_path": "test.py",
            "language": "python",
            "summary": {
                "classes": [
                    {"name": "Class1"},
                    {"name": "Class2"},
                    {"name": "Class3"},
                ]
            },
        }
        requested_types = ["classes"]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.output_data"
        ) as mock_output:
            command._output_text_format(summary_data, requested_types)

            calls = [str(call) for call in mock_output.call_args_list]
            # Should show count
            assert any(
                "3 items" in str(call) or "(3 items)" in str(call) for call in calls
            )


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def command(self):
        """Create a SummaryCommand instance."""
        args = MagicMock()
        args.summary = "classes"
        args.output_format = "text"
        return SummaryCommand(args)

    def test_element_without_name_attribute(self, command):
        """Test handling element without name attribute."""
        mock_element = MagicMock(spec=[])  # No 'name' attribute
        delattr(mock_element, "name")  # Ensure no name attribute

        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = [mock_element]
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch("tree_sitter_analyzer.cli.commands.summary_command.output_section"):
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type",
                return_value=True,
            ):
                with patch.object(command, "_output_text_format") as mock_text_output:
                    command._output_summary_analysis(mock_result)

                # Should use "unknown" for elements without name
                call_args = mock_text_output.call_args[0]
                summary_data = call_args[0]
                assert summary_data["summary"]["classes"][0]["name"] == "unknown"

    def test_large_number_of_elements(self, command):
        """Test handling large number of elements."""
        command.args.summary = "methods"

        # Create 1000 mock elements
        mock_elements = []
        for i in range(1000):
            mock_element = MagicMock()
            mock_element.name = f"method_{i}"
            mock_elements.append(mock_element)

        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = mock_elements
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch("tree_sitter_analyzer.cli.commands.summary_command.output_section"):
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type",
                return_value=True,
            ):
                with patch.object(command, "_output_text_format") as mock_text_output:
                    command._output_summary_analysis(mock_result)

                call_args = mock_text_output.call_args[0]
                summary_data = call_args[0]
                assert len(summary_data["summary"]["methods"]) == 1000

    def test_single_element_type_requested(self, command):
        """Test requesting only a single element type."""
        command.args.summary = "classes"

        mock_class = MagicMock()
        mock_class.name = "TestClass"

        mock_result = MagicMock(spec=AnalysisResult)
        mock_result.elements = [mock_class]
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        with patch("tree_sitter_analyzer.cli.commands.summary_command.output_section"):
            with patch(
                "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type",
                return_value=True,
            ):
                with patch.object(command, "_output_text_format") as mock_text_output:
                    command._output_summary_analysis(mock_result)

                call_args = mock_text_output.call_args[0]
                summary_data = call_args[0]
                # Should only have classes in summary
                assert "classes" in summary_data["summary"]
                assert "methods" not in summary_data["summary"]
                assert "fields" not in summary_data["summary"]
                assert "imports" not in summary_data["summary"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
