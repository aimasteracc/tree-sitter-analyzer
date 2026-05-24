#!/usr/bin/env python3
"""
Tests for TableCommand — core init, execute, toon format, package name.
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
