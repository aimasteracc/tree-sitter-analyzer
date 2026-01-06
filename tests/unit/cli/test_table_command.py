#!/usr/bin/env python3
"""
Tests for TableCommand
"""

from argparse import Namespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.table_command import TableCommand


@pytest.fixture
def mock_args():
    """Create mock args for BaseCommand initialization."""
    return Namespace(
        file_path="test.py",
        file="test.py",
        query_key=None,
        query_string=None,
        advanced=False,
        table="full",
        structure=False,
        summary=False,
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
        include_javadoc=False,
    )


@pytest.fixture
def command(mock_args):
    """Create TableCommand instance for testing."""
    return TableCommand(mock_args)


class TestTableCommandInit:
    """Tests for TableCommand initialization."""

    def test_init(self, command):
        """Test TableCommand initialization."""
        assert command is not None
        assert isinstance(command, TableCommand)
        assert hasattr(command, "args")

    def test_init_with_args(self, mock_args):
        """Test TableCommand initialization with args."""
        command = TableCommand(mock_args)
        assert command.args == mock_args


class TestTableCommandExecuteAsync:
    """Tests for TableCommand.execute_async method."""

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
            with patch.object(command, "_output_table"):
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
    async def test_execute_async_exception(self, command):
        """Test execute_async handles exceptions."""
        with patch.object(
            command, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_analyze.side_effect = Exception("Test error")
            with patch("tree_sitter_analyzer.cli.commands.table_command.output_error"):
                result = await command.execute_async("python")
                assert result == 1

    @pytest.mark.asyncio
    async def test_execute_async_toon_format(self, command):
        """Test execute_async with toon table type."""
        command.args.table = "toon"
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
            with patch.object(command, "_format_as_toon") as mock_format:
                mock_format.return_value = "formatted_output"
                with patch.object(command, "_output_table"):
                    result = await command.execute_async("python")
                    assert result == 0
                    mock_format.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_async_full_format(self, command):
        """Test execute_async with full table type."""
        command.args.table = "full"
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
            with patch(
                "tree_sitter_analyzer.formatters.formatter_registry.FormatterRegistry"
            ) as mock_registry:
                mock_formatter = MagicMock()
                mock_formatter.format_structure.return_value = "table_output"
                mock_registry.get_formatter_for_language.return_value = mock_formatter
                with patch.object(command, "_output_table"):
                    result = await command.execute_async("python")
                    assert result == 0
                    mock_registry.get_formatter_for_language.assert_called_once()


class TestTableCommandFormatAsToon:
    """Tests for TableCommand._format_as_toon method."""

    def test_format_as_toon_basic(self, command):
        """Test _format_as_toon with basic result."""
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        with patch(
            "tree_sitter_analyzer.formatters.toon_formatter.ToonFormatter"
        ) as mock_formatter_class:
            mock_formatter = MagicMock()
            mock_formatter.format.return_value = "toon_output"
            mock_formatter_class.return_value = mock_formatter
            result = command._format_as_toon(analysis_result)
            assert result == "toon_output"
            mock_formatter_class.assert_called_once()

    def test_format_as_toon_with_tabs(self, command):
        """Test _format_as_toon with use_tabs=True."""
        command.args.toon_use_tabs = True
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        with patch(
            "tree_sitter_analyzer.formatters.toon_formatter.ToonFormatter"
        ) as mock_formatter_class:
            mock_formatter = MagicMock()
            mock_formatter.format.return_value = "toon_output"
            mock_formatter_class.return_value = mock_formatter
            command._format_as_toon(analysis_result)
            mock_formatter_class.assert_called_once_with(use_tabs=True)


class TestTableCommandConvertToToonFormat:
    """Tests for TableCommand._convert_to_toon_format method."""

    def test_convert_to_toon_format_empty(self, command):
        """Test _convert_to_toon_format with empty elements."""
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_toon_format(analysis_result)
        assert result["file_path"] == "test.py"
        assert result["language"] == "python"
        assert result["classes"] == []
        assert result["methods"] == []
        assert result["fields"] == []
        assert result["imports"] == []

    def test_convert_to_toon_format_with_class(self, command):
        """Test _convert_to_toon_format with class element."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.visibility = "public"
        mock_class.start_line = 1
        mock_class.end_line = 10
        mock_class.element_type = ELEMENT_TYPE_CLASS

        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[mock_class],
            node_count=1,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_toon_format(analysis_result)
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "TestClass"

    def test_convert_to_toon_format_with_method(self, command):
        """Test _convert_to_toon_format with method element."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_FUNCTION

        mock_method = MagicMock()
        mock_method.name = "testMethod"
        mock_method.visibility = "public"
        mock_method.start_line = 5
        mock_method.end_line = 10
        mock_method.element_type = ELEMENT_TYPE_FUNCTION

        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[mock_method],
            node_count=1,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_toon_format(analysis_result)
        assert len(result["methods"]) == 1
        assert result["methods"][0]["name"] == "testMethod"

    def test_convert_to_toon_format_with_field(self, command):
        """Test _convert_to_toon_format with field element."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_VARIABLE

        mock_field = MagicMock()
        mock_field.name = "testField"
        mock_field.type_annotation = "int"
        mock_field.start_line = 3
        mock_field.end_line = 3
        mock_field.element_type = ELEMENT_TYPE_VARIABLE

        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[mock_field],
            node_count=1,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_toon_format(analysis_result)
        assert len(result["fields"]) == 1
        assert result["fields"][0]["name"] == "testField"

    def test_convert_to_toon_format_with_import(self, command):
        """Test _convert_to_toon_format with import element."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_IMPORT

        mock_import = MagicMock()
        mock_import.name = "os"
        mock_import.is_static = False
        mock_import.is_wildcard = False
        mock_import.import_statement = "import os"
        mock_import.start_line = 1
        mock_import.end_line = 1
        mock_import.element_type = ELEMENT_TYPE_IMPORT

        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[mock_import],
            node_count=1,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_toon_format(analysis_result)
        assert len(result["imports"]) == 1
        assert result["imports"][0]["name"] == "os"

    def test_convert_to_toon_format_statistics(self, command):
        """Test _convert_to_toon_format includes statistics."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.visibility = "public"
        mock_class.start_line = 1
        mock_class.end_line = 10
        mock_class.element_type = ELEMENT_TYPE_CLASS

        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[mock_class],
            node_count=1,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_toon_format(analysis_result)
        stats = result["statistics"]
        assert stats["class_count"] == 1
        assert stats["method_count"] == 0
        assert stats["field_count"] == 0
        assert stats["import_count"] == 0
        assert stats["total_lines"] == 10


class TestTableCommandGetDefaultPackageName:
    """Tests for TableCommand._get_default_package_name method."""

    def test_get_default_package_name_java(self, command):
        """Test _get_default_package_name for Java."""
        result = command._get_default_package_name("java")
        assert result == "unknown"

    def test_get_default_package_name_kotlin(self, command):
        """Test _get_default_package_name for Kotlin."""
        result = command._get_default_package_name("kotlin")
        assert result == "unknown"

    def test_get_default_package_name_python(self, command):
        """Test _get_default_package_name for Python."""
        result = command._get_default_package_name("python")
        assert result == ""

    def test_get_default_package_name_javascript(self, command):
        """Test _get_default_package_name for JavaScript."""
        result = command._get_default_package_name("javascript")
        assert result == ""

    def test_get_default_package_name_cpp(self, command):
        """Test _get_default_package_name for C++."""
        result = command._get_default_package_name("cpp")
        assert result == "unknown"


class TestTableCommandConvertToStructureFormat:
    """Tests for TableCommand._convert_to_structure_format method."""

    def test_convert_to_structure_format_empty(self, command):
        """Test _convert_to_structure_format with empty elements."""
        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[],
            node_count=0,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_structure_format(analysis_result, "python")
        assert result["file_path"] == "test.py"
        assert result["language"] == "python"
        assert result["classes"] == []
        assert result["methods"] == []
        assert result["fields"] == []
        assert result["imports"] == []

    def test_convert_to_structure_format_with_class(self, command):
        """Test _convert_to_structure_format with class element."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.visibility = "public"
        mock_class.start_line = 1
        mock_class.end_line = 10
        mock_class.class_type = "class"
        mock_class.element_type = ELEMENT_TYPE_CLASS

        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[mock_class],
            node_count=1,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_structure_format(analysis_result, "python")
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "TestClass"

    def test_convert_to_structure_format_with_method(self, command):
        """Test _convert_to_structure_format with method element."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_FUNCTION

        mock_method = MagicMock()
        mock_method.name = "testMethod"
        mock_method.visibility = "public"
        mock_method.return_type = "void"
        mock_method.parameters = []
        mock_method.start_line = 5
        mock_method.end_line = 10
        mock_method.element_type = ELEMENT_TYPE_FUNCTION

        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[mock_method],
            node_count=1,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_structure_format(analysis_result, "python")
        assert len(result["methods"]) == 1
        assert result["methods"][0]["name"] == "testMethod"

    def test_convert_to_structure_format_with_field(self, command):
        """Test _convert_to_structure_format with field element."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_VARIABLE

        mock_field = MagicMock()
        mock_field.name = "testField"
        mock_field.variable_type = "int"
        mock_field.visibility = "public"
        mock_field.start_line = 3
        mock_field.end_line = 3
        mock_field.element_type = ELEMENT_TYPE_VARIABLE

        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[mock_field],
            node_count=1,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_structure_format(analysis_result, "python")
        assert len(result["fields"]) == 1
        assert result["fields"][0]["name"] == "testField"

    def test_convert_to_structure_format_statistics(self, command):
        """Test _convert_to_structure_format includes statistics."""
        from tree_sitter_analyzer.constants import (
            ELEMENT_TYPE_CLASS,
            ELEMENT_TYPE_FUNCTION,
        )

        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.visibility = "public"
        mock_class.start_line = 1
        mock_class.end_line = 10
        mock_class.class_type = "class"
        mock_class.element_type = ELEMENT_TYPE_CLASS

        mock_method = MagicMock()
        mock_method.name = "testMethod"
        mock_method.visibility = "public"
        mock_method.return_type = "void"
        mock_method.parameters = []
        mock_method.start_line = 5
        mock_method.end_line = 10
        mock_method.element_type = ELEMENT_TYPE_FUNCTION

        analysis_result = MagicMock(
            file_path="test.py",
            language="python",
            line_count=10,
            elements=[mock_class, mock_method],
            node_count=2,
            success=True,
            analysis_time=0.1,
        )
        result = command._convert_to_structure_format(analysis_result, "python")
        stats = result["statistics"]
        assert stats["class_count"] == 1
        assert stats["method_count"] == 1
        assert stats["field_count"] == 0
        assert stats["import_count"] == 0


class TestTableCommandConvertClassElement:
    """Tests for TableCommand._convert_class_element method."""

    def test_convert_class_element_basic(self, command):
        """Test _convert_class_element with basic class."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.visibility = "public"
        mock_class.start_line = 1
        mock_class.end_line = 10
        mock_class.class_type = "class"
        mock_class.element_type = ELEMENT_TYPE_CLASS

        result = command._convert_class_element(mock_class, 0, "python")
        assert result["name"] == "TestClass"
        assert result["type"] == "class"
        assert result["visibility"] == "public"

    def test_convert_class_element_no_name(self, command):
        """Test _convert_class_element with no name."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_class = MagicMock()
        mock_class.name = None
        mock_class.visibility = "public"
        mock_class.start_line = 1
        mock_class.end_line = 10
        mock_class.class_type = "class"
        mock_class.element_type = ELEMENT_TYPE_CLASS

        result = command._convert_class_element(mock_class, 0, "python")
        assert result["name"] == "UnknownClass_0"

    def test_convert_class_element_interface(self, command):
        """Test _convert_class_element with interface."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_class = MagicMock()
        mock_class.name = "TestInterface"
        mock_class.visibility = "public"
        mock_class.start_line = 1
        mock_class.end_line = 10
        mock_class.class_type = "interface"
        mock_class.element_type = ELEMENT_TYPE_CLASS

        result = command._convert_class_element(mock_class, 0, "java")
        assert result["type"] == "interface"


class TestTableCommandConvertFunctionElement:
    """Tests for TableCommand._convert_function_element method."""

    def test_convert_function_element_basic(self, command):
        """Test _convert_function_element with basic function."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_FUNCTION

        mock_function = MagicMock()
        mock_function.name = "testFunction"
        mock_function.visibility = "public"
        mock_function.return_type = "void"
        mock_function.parameters = []
        mock_function.start_line = 5
        mock_function.end_line = 10
        mock_function.is_constructor = False
        mock_function.is_static = False
        mock_function.complexity_score = 1
        mock_function.element_type = ELEMENT_TYPE_FUNCTION
        # Explicitly set is_private to False to avoid MagicMock default behavior
        mock_function.is_private = False

        result = command._convert_function_element(mock_function, "python")
        assert result["name"] == "testFunction"
        assert result["visibility"] == "public"
        assert result["return_type"] == "void"
        assert result["parameters"] == []

    def test_convert_function_element_with_parameters(self, command):
        """Test _convert_function_element with parameters."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_FUNCTION

        mock_function = MagicMock()
        mock_function.name = "testFunction"
        mock_function.visibility = "public"
        mock_function.return_type = "void"
        mock_function.parameters = ["param1", "param2"]
        mock_function.start_line = 5
        mock_function.end_line = 10
        mock_function.is_constructor = False
        mock_function.is_static = False
        mock_function.complexity_score = 1
        mock_function.element_type = ELEMENT_TYPE_FUNCTION

        result = command._convert_function_element(mock_function, "python")
        assert len(result["parameters"]) == 2
        assert result["parameters"][0]["name"] == "param1"
        assert result["parameters"][1]["name"] == "param2"

    def test_convert_function_element_constructor(self, command):
        """Test _convert_function_element with constructor."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_FUNCTION

        mock_function = MagicMock()
        mock_function.name = "__init__"
        mock_function.visibility = "public"
        mock_function.return_type = "None"
        mock_function.parameters = ["self"]
        mock_function.start_line = 5
        mock_function.end_line = 10
        mock_function.is_constructor = True
        mock_function.is_static = False
        mock_function.complexity_score = 1
        mock_function.element_type = ELEMENT_TYPE_FUNCTION

        result = command._convert_function_element(mock_function, "python")
        assert result["is_constructor"] is True

    def test_convert_function_element_with_javadoc(self, command):
        """Test _convert_function_element with javadoc enabled."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_FUNCTION

        command.args.include_javadoc = True
        mock_function = MagicMock()
        mock_function.name = "testFunction"
        mock_function.visibility = "public"
        mock_function.return_type = "void"
        mock_function.parameters = []
        mock_function.start_line = 5
        mock_function.end_line = 10
        mock_function.is_constructor = False
        mock_function.is_static = False
        mock_function.complexity_score = 1
        mock_function.docstring = "Test function"
        mock_function.element_type = ELEMENT_TYPE_FUNCTION

        result = command._convert_function_element(mock_function, "python")
        assert result["javadoc"] == "Test function"


class TestTableCommandConvertVariableElement:
    """Tests for TableCommand._convert_variable_element method."""

    def test_convert_variable_element_basic(self, command):
        """Test _convert_variable_element with basic variable."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_VARIABLE

        mock_variable = MagicMock()
        mock_variable.name = "testVar"
        mock_variable.visibility = "public"
        mock_variable.variable_type = "int"
        mock_variable.modifiers = []
        mock_variable.start_line = 3
        mock_variable.end_line = 3
        mock_variable.element_type = ELEMENT_TYPE_VARIABLE
        # Explicitly set is_private to False to avoid MagicMock default behavior
        mock_variable.is_private = False

        result = command._convert_variable_element(mock_variable, "python")
        assert result["name"] == "testVar"
        assert result["type"] == "int"
        assert result["visibility"] == "public"

    def test_convert_variable_element_python(self, command):
        """Test _convert_variable_element for Python."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_VARIABLE

        mock_variable = MagicMock()
        mock_variable.name = "testVar"
        mock_variable.visibility = "public"
        mock_variable.variable_type = "str"
        mock_variable.modifiers = []
        mock_variable.start_line = 3
        mock_variable.end_line = 3
        mock_variable.element_type = ELEMENT_TYPE_VARIABLE

        result = command._convert_variable_element(mock_variable, "python")
        assert result["type"] == "str"

    def test_convert_variable_element_with_javadoc(self, command):
        """Test _convert_variable_element with javadoc enabled."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_VARIABLE

        command.args.include_javadoc = True
        mock_variable = MagicMock()
        mock_variable.name = "testVar"
        mock_variable.visibility = "public"
        mock_variable.variable_type = "int"
        mock_variable.modifiers = []
        mock_variable.start_line = 3
        mock_variable.end_line = 3
        mock_variable.docstring = "Test variable"
        mock_variable.element_type = ELEMENT_TYPE_VARIABLE

        result = command._convert_variable_element(mock_variable, "python")
        assert result["javadoc"] == "Test variable"


class TestTableCommandConvertImportElement:
    """Tests for TableCommand._convert_import_element method."""

    def test_convert_import_element_basic(self, command):
        """Test _convert_import_element with basic import."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_IMPORT

        mock_import = MagicMock()
        mock_import.name = "os"
        mock_import.raw_text = "import os"
        mock_import.module_name = "os"
        mock_import.element_type = ELEMENT_TYPE_IMPORT

        result = command._convert_import_element(mock_import)
        assert result["name"] == "os"
        assert result["statement"] == "import os"
        assert result["raw_text"] == "import os"

    def test_convert_import_element_no_raw_text(self, command):
        """Test _convert_import_element without raw_text."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_IMPORT

        mock_import = MagicMock()
        mock_import.name = "sys"
        mock_import.raw_text = ""
        mock_import.module_name = "sys"
        mock_import.element_type = ELEMENT_TYPE_IMPORT

        result = command._convert_import_element(mock_import)
        assert result["statement"] == "import sys"
        assert result["raw_text"] == "import sys"


class TestTableCommandProcessParameters:
    """Tests for TableCommand._process_parameters method."""

    def test_process_parameters_empty(self, command):
        """Test _process_parameters with empty parameters."""
        result = command._process_parameters([], "python")
        assert result == []

    def test_process_parameters_string(self, command):
        """Test _process_parameters with string parameters."""
        result = command._process_parameters("param1, param2, param3", "python")
        assert len(result) == 3
        assert result[0]["name"] == "param1"
        assert result[1]["name"] == "param2"
        assert result[2]["name"] == "param3"

    def test_process_parameters_list(self, command):
        """Test _process_parameters with list parameters."""
        result = command._process_parameters(["param1", "param2"], "python")
        assert len(result) == 2
        assert result[0]["name"] == "param1"
        assert result[1]["name"] == "param2"

    def test_process_parameters_python_type_suffix(self, command):
        """Test _process_parameters with Python type suffix."""
        result = command._process_parameters(["param1: str", "param2: int"], "python")
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "str"
        assert result[1]["name"] == "param2"
        assert result[1]["type"] == "int"

    def test_process_parameters_java_format(self, command):
        """Test _process_parameters with Java format."""
        result = command._process_parameters(["String param1", "int param2"], "java")
        assert result[0]["name"] == "param1"
        assert result[0]["type"] == "String"
        assert result[1]["name"] == "param2"
        assert result[1]["type"] == "int"


class TestTableCommandGetElementVisibility:
    """Tests for TableCommand._get_element_visibility method."""

    def test_get_element_visibility_public(self, command):
        """Test _get_element_visibility with public visibility."""
        mock_element = MagicMock()
        mock_element.visibility = "public"
        mock_element.is_private = False
        mock_element.is_public = True

        result = command._get_element_visibility(mock_element)
        assert result == "public"

    def test_get_element_visibility_private(self, command):
        """Test _get_element_visibility with private visibility."""
        mock_element = MagicMock()
        mock_element.visibility = "private"
        mock_element.is_private = True
        mock_element.is_public = False

        result = command._get_element_visibility(mock_element)
        assert result == "private"

    def test_get_element_visibility_default(self, command):
        """Test _get_element_visibility with default visibility."""
        mock_element = MagicMock()
        mock_element.visibility = "public"
        mock_element.is_private = False
        mock_element.is_public = False

        result = command._get_element_visibility(mock_element)
        assert result == "public"


class TestTableCommandOutputTable:
    """Tests for TableCommand._output_table method."""

    def test_output_table_basic(self, command):
        """Test _output_table with basic output."""
        table_output = "table content"
        with patch("sys.stdout.buffer.write") as mock_write:
            command._output_table(table_output)
            mock_write.assert_called_once_with(table_output.encode("utf-8"))

    def test_output_table_unicode(self, command):
        """Test _output_table with unicode content."""
        table_output = "テーブル出力"
        with patch("sys.stdout.buffer.write") as mock_write:
            command._output_table(table_output)
            mock_write.assert_called_once_with(table_output.encode("utf-8"))
