from unittest.mock import AsyncMock, MagicMock, patch

from tree_sitter_analyzer.cli.commands.summary_command import SummaryCommand
from tree_sitter_analyzer.constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
)


class TestSummaryCommandCoverage:
    def setup_method(self):
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
        assert result == 1

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
        assert result == 0
        mock_output_section.assert_called_with("Summary Results")
        # verify output calls
        calls = [str(c) for c in mock_output_data.call_args_list]
        assert any("File: test.py" in c for c in calls)

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
        assert result == 0
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
            assert any("Classes (1 items" in c for c in calls)
            assert any("MyClass" in c for c in calls)
            assert any("Methods (1 items" in c for c in calls)
            assert any("my_method" in c for c in calls)
            assert any("Fields (1 items" in c for c in calls)
            assert any("my_field" in c for c in calls)
            assert any("Imports (1 items" in c for c in calls)
            assert any("os" in c for c in calls)

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
            assert any("Classes (1 items" in c for c in calls)
            assert not any("Methods" in c for c in calls)

    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_data")
    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_section")
    def test_output_summary_analysis_default_types(
        self, mock_output_section, mock_output_data
    ):
        """Test _output_summary_analysis with default types (classes,methods)"""
        self.command.args.summary = None  # None should trigger default

        mock_result = MagicMock()
        mock_result.file_path = "test.py"
        mock_result.language = "python"
        mock_result.elements = []

        self.command._output_summary_analysis(mock_result)
        mock_output_section.assert_called_with("Summary Results")

    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_data")
    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_section")
    def test_text_format_with_method_elements(
        self, mock_output_section, mock_output_data
    ):
        """Test text output with method elements covering lines 95-107, 137-169"""
        self.command.args.summary = "classes,methods,fields,imports"
        self.command.args.output_format = "text"

        class_elem = MagicMock()
        class_elem.type = ELEMENT_TYPE_CLASS
        class_elem.name = "MyClass"
        class_elem.start_line = 10
        class_elem.end_line = 50
        class_elem.visibility = "public"
        class_elem.modifiers = ["static"]

        method_elem = MagicMock()
        method_elem.type = ELEMENT_TYPE_FUNCTION
        method_elem.name = "my_method"
        method_elem.start_line = 15
        method_elem.end_line = 30
        method_elem.visibility = "private"
        method_elem.modifiers = ["async"]
        method_elem.parameters = ["self"]
        method_elem.return_type = "str"

        field_elem = MagicMock()
        field_elem.type = ELEMENT_TYPE_VARIABLE
        field_elem.name = "my_field"
        field_elem.start_line = 12
        field_elem.end_line = 12
        field_elem.visibility = "protected"
        field_elem.modifiers = ["final"]

        import_elem = MagicMock()
        import_elem.type = ELEMENT_TYPE_IMPORT
        import_elem.name = "os"
        import_elem.start_line = 1

        mock_result = MagicMock()
        mock_result.file_path = "test.py"
        mock_result.language = "python"
        mock_result.elements = [class_elem, method_elem, field_elem, import_elem]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
        ) as mock_check:
            mock_check.side_effect = lambda e, t: e.type == t
            self.command._output_summary_analysis(mock_result)

        calls = [str(c) for c in mock_output_data.call_args_list]
        all_output = " ".join(calls)
        assert "File: test.py" in all_output
        assert "MyClass" in all_output
        assert "L10-50" in all_output
        assert "my_method" in all_output
        assert "L15-30" in all_output
        assert "private" in all_output
        assert "my_field" in all_output
        assert "os" in all_output
        assert "static" in all_output
        mock_output_section.assert_called_with("Summary Results")

    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_json")
    def test_json_output_with_methods(self, mock_output_json):
        """Test JSON output path covering lines 130-131"""
        self.command.args.output_format = "json"
        self.command.args.summary = "classes,methods"

        method_elem = MagicMock()
        method_elem.type = ELEMENT_TYPE_FUNCTION
        method_elem.name = "run"
        method_elem.start_line = 5
        method_elem.end_line = 10
        method_elem.visibility = "public"
        method_elem.modifiers = []
        method_elem.parameters = ["x"]
        method_elem.return_type = "int"

        mock_result = MagicMock()
        mock_result.file_path = "app.py"
        mock_result.language = "python"
        mock_result.elements = [method_elem]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
        ) as mock_check:
            mock_check.side_effect = lambda e, t: e.type == t
            self.command._output_summary_analysis(mock_result)

        mock_output_json.assert_called_once()
        data = mock_output_json.call_args[0][0]
        assert data["file_path"] == "app.py"
        assert "methods" in data["summary"]
        assert data["summary"]["methods"][0]["name"] == "run"

    @patch(
        "tree_sitter_analyzer.cli.commands.summary_command._toon_available",
        True,
    )
    @patch("tree_sitter_analyzer.cli.commands.summary_command.ToonFormatter")
    @patch("tree_sitter_analyzer.cli.commands.summary_command.output_section")
    def test_toon_output_with_elements(self, mock_output_section, mock_toon_cls):
        """Test toon output path covering lines 132-135"""
        self.command.args.output_format = "toon"
        self.command.args.summary = "classes"
        self.command.args.toon_use_tabs = True

        mock_formatter = MagicMock()
        mock_formatter.format.return_value = "toon output"
        mock_toon_cls.return_value = mock_formatter

        class_elem = MagicMock()
        class_elem.type = ELEMENT_TYPE_CLASS
        class_elem.name = "Svc"
        class_elem.start_line = 1
        class_elem.end_line = 20
        class_elem.visibility = "public"
        class_elem.modifiers = []

        mock_result = MagicMock()
        mock_result.file_path = "svc.py"
        mock_result.language = "python"
        mock_result.elements = [class_elem]

        with patch(
            "tree_sitter_analyzer.cli.commands.summary_command.is_element_of_type"
        ) as mock_check:
            mock_check.side_effect = lambda e, t: e.type == t
            with patch("builtins.print") as mock_print:
                self.command._output_summary_analysis(mock_result)

        mock_toon_cls.assert_called_once_with(use_tabs=True)
        mock_print.assert_called_once_with("toon output")


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
