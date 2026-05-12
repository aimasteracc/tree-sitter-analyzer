#!/usr/bin/env python3
"""Coverage boost tests for TableCommand uncovered lines."""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.table_command import TableCommand
from tree_sitter_analyzer.constants import (
    ELEMENT_TYPE_SQL_FUNCTION,
    ELEMENT_TYPE_SQL_INDEX,
    ELEMENT_TYPE_SQL_PROCEDURE,
    ELEMENT_TYPE_SQL_TABLE,
    ELEMENT_TYPE_SQL_TRIGGER,
    ELEMENT_TYPE_SQL_VIEW,
)


@pytest.fixture
def command():
    """Create a TableCommand with minimal args."""
    args = MagicMock()
    args.table = "full"
    args.include_javadoc = False
    return TableCommand(args)


class TestConvertToFormatterFormat:
    """Tests for _convert_to_formatter_format (line 182)."""

    def test_convert_to_formatter_format_basic(self, command):
        """Test _convert_to_formatter_format returns expected structure."""
        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 42
        analysis_result.elements = []
        analysis_result.analysis_time = 0.5

        result = command._convert_to_formatter_format(analysis_result)

        assert result["file_path"] == "test.py"
        assert result["language"] == "python"
        assert result["line_count"] == 42
        assert result["elements"] == []
        assert result["analysis_metadata"]["analyzer_version"] == "2.0.0"

    def test_convert_to_formatter_format_with_elements(self, command):
        """Test _convert_to_formatter_format with elements."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_elem = MagicMock()
        mock_elem.name = "TestClass"
        mock_elem.element_type = ELEMENT_TYPE_CLASS
        mock_elem.start_line = 1
        mock_elem.end_line = 10
        mock_elem.text = "class TestClass"
        mock_elem.level = 1
        mock_elem.url = ""
        mock_elem.alt = ""
        mock_elem.language = ""
        mock_elem.line_count = 0
        mock_elem.list_type = ""
        mock_elem.item_count = 0
        mock_elem.column_count = 0
        mock_elem.row_count = 0

        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 42
        analysis_result.elements = [mock_elem]
        analysis_result.analysis_time = 0.5

        result = command._convert_to_formatter_format(analysis_result)

        assert len(result["elements"]) == 1
        assert result["elements"][0]["name"] == "TestClass"
        assert result["elements"][0]["type"] == ELEMENT_TYPE_CLASS


class TestConvertToStructureFormatPackage:
    """Tests for _convert_to_structure_format with package handling (lines 154-155, 253)."""

    def test_convert_with_package_object(self, command):
        """Test _convert_to_structure_format when analysis_result has package attr."""
        mock_package = MagicMock()
        mock_package.name = "com.example"

        analysis_result = MagicMock()
        analysis_result.file_path = "test.java"
        analysis_result.language = "java"
        analysis_result.line_count = 100
        analysis_result.elements = []
        analysis_result.package = mock_package

        result = command._convert_to_structure_format(analysis_result, "java")
        assert result["package"]["name"] == "com.example"

    def test_convert_with_default_package_java(self, command):
        """Test _convert_to_structure_format uses _get_default_package_name for java (line 253)."""
        analysis_result = MagicMock()
        analysis_result.file_path = "test.java"
        analysis_result.language = "java"
        analysis_result.line_count = 100
        analysis_result.elements = []
        # No package attribute -> falls back to _get_default_package_name
        del analysis_result.package

        result = command._convert_to_structure_format(analysis_result, "java")
        assert result["package"]["name"] == "unknown"

    def test_convert_with_default_package_python(self, command):
        """Test _convert_to_structure_format uses _get_default_package_name for python (line 253)."""
        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 100
        analysis_result.elements = []
        del analysis_result.package

        result = command._convert_to_structure_format(analysis_result, "python")
        assert result["package"]["name"] == ""

    def test_convert_with_package_element(self, command):
        """Test _convert_to_structure_format when element is PACKAGE type."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_PACKAGE

        mock_pkg = MagicMock()
        mock_pkg.name = "org.example"
        mock_pkg.element_type = ELEMENT_TYPE_PACKAGE

        analysis_result = MagicMock()
        analysis_result.file_path = "test.java"
        analysis_result.language = "java"
        analysis_result.line_count = 100
        analysis_result.elements = [mock_pkg]

        result = command._convert_to_structure_format(analysis_result, "java")
        assert result["package"]["name"] == "org.example"


class TestConvertToStructureFormatSQL:
    """Tests for _convert_to_structure_format with SQL elements (lines 272, 280)."""

    def test_convert_with_sql_table(self, command):
        """Test _convert_to_structure_format with SQL table element."""
        mock_elem = MagicMock()
        mock_elem.name = "users"
        mock_elem.element_type = ELEMENT_TYPE_SQL_TABLE
        mock_elem.columns = []
        mock_elem.parameters = []
        mock_elem.dependencies = []
        mock_elem.source_tables = []
        mock_elem.return_type = ""
        mock_elem.start_line = 1
        mock_elem.end_line = 10

        analysis_result = MagicMock()
        analysis_result.file_path = "test.sql"
        analysis_result.language = "sql"
        analysis_result.line_count = 50
        analysis_result.elements = [mock_elem]
        del analysis_result.package

        result = command._convert_to_structure_format(analysis_result, "sql")
        assert len(result["methods"]) == 1
        assert result["methods"][0]["name"] == "users"
        assert result["methods"][0]["sql_type"] == "table"

    def test_convert_with_sql_view(self, command):
        """Test _convert_to_structure_format with SQL view element."""
        mock_elem = MagicMock()
        mock_elem.name = "active_users"
        mock_elem.element_type = ELEMENT_TYPE_SQL_VIEW
        mock_elem.columns = []
        mock_elem.parameters = []
        mock_elem.dependencies = []
        mock_elem.source_tables = []
        mock_elem.return_type = ""
        mock_elem.start_line = 1
        mock_elem.end_line = 5

        analysis_result = MagicMock()
        analysis_result.file_path = "test.sql"
        analysis_result.language = "sql"
        analysis_result.line_count = 50
        analysis_result.elements = [mock_elem]
        del analysis_result.package

        result = command._convert_to_structure_format(analysis_result, "sql")
        assert len(result["methods"]) == 1
        assert result["methods"][0]["sql_type"] == "view"

    def test_convert_with_all_sql_types(self, command):
        """Test _convert_to_structure_format with all SQL element types."""
        sql_types = [
            (ELEMENT_TYPE_SQL_TABLE, "table"),
            (ELEMENT_TYPE_SQL_VIEW, "view"),
            (ELEMENT_TYPE_SQL_PROCEDURE, "procedure"),
            (ELEMENT_TYPE_SQL_FUNCTION, "sql_function"),
            (ELEMENT_TYPE_SQL_TRIGGER, "trigger"),
            (ELEMENT_TYPE_SQL_INDEX, "index"),
        ]

        elements = []
        for elem_type, _ in sql_types:
            mock_elem = MagicMock()
            mock_elem.name = f"elem_{elem_type}"
            mock_elem.element_type = elem_type
            mock_elem.columns = []
            mock_elem.parameters = []
            mock_elem.dependencies = []
            mock_elem.source_tables = []
            mock_elem.return_type = ""
            mock_elem.start_line = 1
            mock_elem.end_line = 5
            elements.append(mock_elem)

        analysis_result = MagicMock()
        analysis_result.file_path = "test.sql"
        analysis_result.language = "sql"
        analysis_result.line_count = 100
        analysis_result.elements = elements
        del analysis_result.package

        result = command._convert_to_structure_format(analysis_result, "sql")
        assert len(result["methods"]) == 6
        assert result["statistics"]["method_count"] == 6


class TestConvertToStructureFormatException:
    """Tests for _convert_to_structure_format exception handler (lines 282-284)."""

    def test_convert_with_element_exception(self, command):
        """Test _convert_to_structure_format handles element processing exception."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        bad_elem = MagicMock()
        bad_elem.element_type = ELEMENT_TYPE_CLASS
        bad_elem.name = "BadClass"
        bad_elem.visibility = "public"
        bad_elem.start_line = 1
        bad_elem.end_line = 10

        good_elem = MagicMock()
        good_elem.name = "GoodClass"
        good_elem.element_type = ELEMENT_TYPE_CLASS
        good_elem.visibility = "public"
        good_elem.start_line = 1
        good_elem.end_line = 10

        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 10
        analysis_result.elements = [bad_elem, good_elem]
        # Remove package attribute to trigger _get_default_package_name path
        del analysis_result.package

        with patch.object(
            command,
            "_convert_class_element",
            side_effect=[Exception("Boom"), {"name": "GoodClass"}],
        ):
            with patch(
                "tree_sitter_analyzer.cli.commands.table_command.output_error"
            ) as mock_err:
                result = command._convert_to_structure_format(analysis_result, "python")
                mock_err.assert_called_once()
                # Should continue processing despite exception
                assert "file_path" in result
                assert len(result["classes"]) == 1
                assert result["classes"][0]["name"] == "GoodClass"


class TestConvertSQLElement:
    """Tests for _convert_sql_element (lines 407-417)."""

    def test_convert_sql_element_basic(self, command):
        """Test _convert_sql_element with basic SQL element."""
        mock_elem = MagicMock()
        mock_elem.name = "test_table"
        mock_elem.element_type = ELEMENT_TYPE_SQL_TABLE
        mock_elem.columns = [{"name": "id", "type": "INT"}]
        mock_elem.parameters = []
        mock_elem.dependencies = []
        mock_elem.source_tables = []
        mock_elem.return_type = ""
        mock_elem.start_line = 1
        mock_elem.end_line = 10

        result = command._convert_sql_element(mock_elem, "sql")

        assert result["name"] == "test_table"
        assert result["sql_type"] == "table"
        assert result["visibility"] == "public"
        assert result["columns"] == [{"name": "id", "type": "INT"}]
        assert result["parameters"] == []

    def test_convert_sql_element_with_all_metadata(self, command):
        """Test _convert_sql_element with full metadata."""
        mock_elem = MagicMock()
        mock_elem.name = "sp_get_users"
        mock_elem.element_type = ELEMENT_TYPE_SQL_PROCEDURE
        mock_elem.columns = [{"name": "result_id", "type": "INT"}]
        mock_elem.parameters = ["@user_id INT", "@status VARCHAR"]
        mock_elem.dependencies = ["users"]
        mock_elem.source_tables = ["users", "profiles"]
        mock_elem.return_type = "TABLE"
        mock_elem.start_line = 5
        mock_elem.end_line = 25

        result = command._convert_sql_element(mock_elem, "sql")

        assert result["name"] == "sp_get_users"
        assert result["sql_type"] == "procedure"
        assert result["return_type"] == "TABLE"
        assert result["dependencies"] == ["users"]
        assert result["source_tables"] == ["users", "profiles"]
        assert len(result["columns"]) == 1
        assert result["line_range"]["start"] == 5
        assert result["line_range"]["end"] == 25

    def test_convert_sql_element_no_attributes(self, command):
        """Test _convert_sql_element with element missing optional attributes."""
        mock_elem = MagicMock(spec=[])  # No attributes at all

        result = command._convert_sql_element(mock_elem, "sql")

        assert "name" in result
        assert result["sql_type"] is not None
        assert result["columns"] == []
        assert result["dependencies"] == []
        assert result["source_tables"] == []

    def test_convert_sql_element_return_type_fallback(self, command):
        """Test _convert_sql_element with empty return_type (line 420-422)."""
        mock_elem = MagicMock()
        mock_elem.name = "test_proc"
        mock_elem.element_type = ELEMENT_TYPE_SQL_PROCEDURE
        mock_elem.columns = []
        mock_elem.parameters = []
        mock_elem.dependencies = []
        mock_elem.source_tables = []
        mock_elem.return_type = None  # Falsy
        mock_elem.start_line = 1
        mock_elem.end_line = 5

        result = command._convert_sql_element(mock_elem, "sql")
        assert result["return_type"] == ""  # Should not fallback to element_type


class TestProcessSQLParameters:
    """Tests for _process_sql_parameters (lines 440-443)."""

    def test_process_sql_params_empty_list(self, command):
        """Test _process_sql_parameters with empty list."""
        result = command._process_sql_parameters([])
        assert result == []

    def test_process_sql_params_none(self, command):
        """Test _process_sql_parameters with None (line 440-441)."""
        result = command._process_sql_parameters(None)
        assert result == []

    def test_process_sql_params_falsy_zero(self, command):
        """Test _process_sql_parameters with falsy value 0."""
        result = command._process_sql_parameters(0)
        assert result == []

    def test_process_sql_params_empty_string(self, command):
        """Test _process_sql_parameters with empty string."""
        result = command._process_sql_parameters("")
        assert result == []

    def test_process_sql_params_list_of_strings(self, command):
        """Test _process_sql_parameters with list of strings (line 443-449)."""
        params = ["@user_id INT", "@status VARCHAR(50)", "@flag BIT"]
        result = command._process_sql_parameters(params)
        assert len(result) == 3
        assert result[0]["name"] == "@user_id INT"
        assert result[0]["type"] == "Any"
        assert result[1]["name"] == "@status VARCHAR(50)"
        assert result[2]["name"] == "@flag BIT"

    def test_process_sql_params_list_of_dicts(self, command):
        """Test _process_sql_parameters with list of dicts."""
        params = [
            {"name": "user_id", "type": "INT"},
            {"name": "status", "type": "VARCHAR"},
        ]
        result = command._process_sql_parameters(params)
        assert len(result) == 2
        assert result[0] == {"name": "user_id", "type": "INT"}
        assert result[1] == {"name": "status", "type": "VARCHAR"}

    def test_process_sql_params_non_list(self, command):
        """Test _process_sql_parameters with non-list value (else branch line 451-452)."""
        params = "single_param"
        result = command._process_sql_parameters(params)
        assert len(result) == 1
        assert result[0]["name"] == "single_param"
        assert result[0]["type"] == "Any"

    def test_process_sql_params_mixed_list(self, command):
        """Test _process_sql_parameters with mixed types in list."""
        params = [
            "@param1 INT",
            {"name": "param2", "type": "VARCHAR"},
            "@param3 FLOAT",
        ]
        result = command._process_sql_parameters(params)
        assert len(result) == 3
        assert result[0]["name"] == "@param1 INT"
        assert result[1] == {"name": "param2", "type": "VARCHAR"}
        assert result[2]["name"] == "@param3 FLOAT"
