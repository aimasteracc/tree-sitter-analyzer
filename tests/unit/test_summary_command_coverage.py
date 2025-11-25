import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tree_sitter_analyzer.cli.commands.summary_command import SummaryCommand
from tree_sitter_analyzer.constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
)


class TestSummaryCommandCoverage(unittest.TestCase):
    def setUp(self):
        self.mock_args = MagicMock()
        self.mock_args.output_format = "text"
        self.mock_args.summary = "classes,methods,fields,imports"
        self.command = SummaryCommand(self.mock_args)
        self.command.analyze_file = AsyncMock()

    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_section")
    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_data")
    def test_execute_async_no_result(self, mock_output_data, mock_output_section):
        """Test execute_async with no analysis result"""
        self.command.analyze_file.return_value = None
        result = asyncio_run(self.command.execute_async("python"))
        self.assertEqual(result, 1)

    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_section")
    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_data")
    def test_execute_async_with_result_text(
        self, mock_output_data, mock_output_section
    ):
        """Test execute_async with result (text output)"""
        mock_result = MagicMock()
        mock_result.elements = []
        mock_result.file_path = "test.py"
        mock_result.language = "python"
        self.command.analyze_file.return_value = mock_result

        result = asyncio_run(self.command.execute_async("python"))
        self.assertEqual(result, 0)
        mock_output_section.assert_called_with("Summary Results")
        # verify output calls
        calls = [str(c) for c in mock_output_data.call_args_list]
        self.assertTrue(any("File: test.py" in c for c in calls))

    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_json")
    def test_execute_async_with_result_json(self, mock_output_json):
        """Test execute_async with result (json output)"""
        self.command.args.output_format = "json"
        mock_result = MagicMock()
        mock_result.elements = []
        mock_result.file_path = "test.py"
        mock_result.language = "python"
        self.command.analyze_file.return_value = mock_result

        result = asyncio_run(self.command.execute_async("python"))
        self.assertEqual(result, 0)
        mock_output_json.assert_called()

    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_data")
    def test_output_summary_analysis_all_types(self, mock_output_data):
        """Test _output_summary_analysis with all element types"""
        mock_result = MagicMock()
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        # Mock elements
        class_elem = MagicMock()
        class_elem.type = ELEMENT_TYPE_CLASS
        class_elem.name = "MyClass"

        method_elem = MagicMock()
        method_elem.type = ELEMENT_TYPE_FUNCTION
        method_elem.name = "my_method"

        field_elem = MagicMock()
        field_elem.type = ELEMENT_TYPE_VARIABLE
        field_elem.name = "my_field"

        import_elem = MagicMock()
        import_elem.type = ELEMENT_TYPE_IMPORT
        import_elem.name = "os"

        mock_result.elements = [class_elem, method_elem, field_elem, import_elem]

        # Mock is_element_of_type behavior logic simply by type attribute check for test simplicity
        # The actual code uses is_element_of_type utility, we should mock that or make our mocks compatible
        # Since is_element_of_type is imported, we can patch it or rely on its logic.
        # Assuming is_element_of_type checks element.type against constant.

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
        ) as mock_check:

            def check_side_effect(elem, type_const):
                return elem.type == type_const

            mock_check.side_effect = check_side_effect

            self.command._output_summary_analysis(mock_result)

            # Check outputs
            calls = [str(c) for c in mock_output_data.call_args_list]
            self.assertTrue(any("Classes (1 items)" in c for c in calls))
            self.assertTrue(any("MyClass" in c for c in calls))
            self.assertTrue(any("Methods (1 items)" in c for c in calls))
            self.assertTrue(any("my_method" in c for c in calls))
            self.assertTrue(any("Fields (1 items)" in c for c in calls))
            self.assertTrue(any("my_field" in c for c in calls))
            self.assertTrue(any("Imports (1 items)" in c for c in calls))
            self.assertTrue(any("os" in c for c in calls))

    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_data")
    def test_output_summary_analysis_filtered_types(self, mock_output_data):
        """Test _output_summary_analysis with specific types requested"""
        self.command.args.summary = "classes"

        mock_result = MagicMock()
        mock_result.file_path = "test.py"
        mock_result.language = "python"

        class_elem = MagicMock()
        class_elem.type = ELEMENT_TYPE_CLASS
        class_elem.name = "MyClass"

        method_elem = MagicMock()
        method_elem.type = ELEMENT_TYPE_FUNCTION
        method_elem.name = "my_method"

        mock_result.elements = [class_elem, method_elem]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
        ) as mock_check:

            def check_side_effect(elem, type_const):
                return elem.type == type_const

            mock_check.side_effect = check_side_effect

            self.command._output_summary_analysis(mock_result)

            calls = [str(c) for c in mock_output_data.call_args_list]
            self.assertTrue(any("Classes (1 items)" in c for c in calls))
            self.assertFalse(any("Methods" in c for c in calls))

    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_data")
    def test_output_summary_analysis_default_types(self, mock_output_data):
        """Test _output_summary_analysis with default types (classes,methods)"""
        self.command.args.summary = None  # None should trigger default

        mock_result = MagicMock()
        mock_result.file_path = "test.py"
        mock_result.language = "python"
        mock_result.elements = []

        self.command._output_summary_analysis(mock_result)
        # Should process classes and methods, but we have empty elements so just check execution doesn't crash


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
