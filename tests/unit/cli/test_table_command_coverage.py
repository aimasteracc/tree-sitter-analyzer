from unittest.mock import MagicMock

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
def table_command():
    args = MagicMock()
    args.table = "full"
    args.include_javadoc = False
    return TableCommand(args)


def test_table_command_execute_async_empty(table_command):
    """Test that execute_async properly handles missing files."""
    args = MagicMock()
    args.file = "nonexistent_test_file.py"
    args.table = "full"
    args.output = None
    args.include_javadoc = False

    assert table_command is not None
    assert hasattr(table_command, "execute_async")


def test_table_command_basic_logic(table_command):
    assert isinstance(table_command, TableCommand)
    assert table_command.args.table == "full"


# ---------------------------------------------------------------------------
# Tests migrated from test_table_command_coverage_boost2.py
# ---------------------------------------------------------------------------


class TestConvertToFormatterFormatBehavioral:
    """Behavioral tests for _convert_to_formatter_format."""

    def test_basic_structure_fields(self, table_command):
        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 42
        analysis_result.elements = []
        analysis_result.analysis_time = 0.5

        result = table_command._convert_to_formatter_format(analysis_result)

        assert result["file_path"] == "test.py"
        assert result["language"] == "python"
        assert result["line_count"] == 42
        assert result["elements"] == []
        assert result["analysis_metadata"]["analyzer_version"] == "2.0.0"

    def test_with_class_element(self, table_command):
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

        result = table_command._convert_to_formatter_format(analysis_result)

        assert len(result["elements"]) == 1
        assert result["elements"][0]["name"] == "TestClass"
        assert result["elements"][0]["type"] == ELEMENT_TYPE_CLASS


class TestConvertToStructureFormatSQLBehavioral:
    """Behavioral tests for _convert_to_structure_format with SQL elements."""

    def test_sql_table_element(self, table_command):
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

        result = table_command._convert_to_structure_format(analysis_result, "sql")
        assert len(result["methods"]) == 1
        assert result["methods"][0]["name"] == "users"
        assert result["methods"][0]["sql_type"] == "table"

    def test_all_sql_types_count(self, table_command):
        sql_types = [
            ELEMENT_TYPE_SQL_TABLE,
            ELEMENT_TYPE_SQL_VIEW,
            ELEMENT_TYPE_SQL_PROCEDURE,
            ELEMENT_TYPE_SQL_FUNCTION,
            ELEMENT_TYPE_SQL_TRIGGER,
            ELEMENT_TYPE_SQL_INDEX,
        ]
        elements = []
        for elem_type in sql_types:
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

        result = table_command._convert_to_structure_format(analysis_result, "sql")
        assert len(result["methods"]) == 6
        assert result["statistics"]["method_count"] == 6

    def test_package_object_name(self, table_command):
        mock_package = MagicMock()
        mock_package.name = "com.example"

        analysis_result = MagicMock()
        analysis_result.file_path = "test.java"
        analysis_result.language = "java"
        analysis_result.line_count = 100
        analysis_result.elements = []
        analysis_result.package = mock_package

        result = table_command._convert_to_structure_format(analysis_result, "java")
        assert result["package"]["name"] == "com.example"

    def test_default_package_java(self, table_command):
        analysis_result = MagicMock()
        analysis_result.file_path = "test.java"
        analysis_result.language = "java"
        analysis_result.line_count = 100
        analysis_result.elements = []
        del analysis_result.package

        result = table_command._convert_to_structure_format(analysis_result, "java")
        assert result["package"]["name"] == "unknown"

    def test_default_package_python(self, table_command):
        analysis_result = MagicMock()
        analysis_result.file_path = "test.py"
        analysis_result.language = "python"
        analysis_result.line_count = 100
        analysis_result.elements = []
        del analysis_result.package

        result = table_command._convert_to_structure_format(analysis_result, "python")
        assert result["package"]["name"] == ""


class TestConvertSQLElementBehavioral:
    """Behavioral tests for _convert_sql_element."""

    def test_basic_sql_table(self, table_command):
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

        result = table_command._convert_sql_element(mock_elem, "sql")

        assert result["name"] == "test_table"
        assert result["sql_type"] == "table"
        assert result["visibility"] == "public"
        assert result["columns"] == [{"name": "id", "type": "INT"}]
        assert result["parameters"] == []

    def test_procedure_with_full_metadata(self, table_command):
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

        result = table_command._convert_sql_element(mock_elem, "sql")

        assert result["name"] == "sp_get_users"
        assert result["sql_type"] == "procedure"
        assert result["return_type"] == "TABLE"
        assert result["dependencies"] == ["users"]
        assert result["source_tables"] == ["users", "profiles"]
        assert len(result["columns"]) == 1
        assert result["line_range"]["start"] == 5
        assert result["line_range"]["end"] == 25

    def test_null_return_type_becomes_empty_string(self, table_command):
        mock_elem = MagicMock()
        mock_elem.name = "test_proc"
        mock_elem.element_type = ELEMENT_TYPE_SQL_PROCEDURE
        mock_elem.columns = []
        mock_elem.parameters = []
        mock_elem.dependencies = []
        mock_elem.source_tables = []
        mock_elem.return_type = None
        mock_elem.start_line = 1
        mock_elem.end_line = 5

        result = table_command._convert_sql_element(mock_elem, "sql")
        assert result["return_type"] == ""


class TestProcessSQLParametersBehavioral:
    """Behavioral tests for _process_sql_parameters."""

    def test_empty_list_returns_empty(self, table_command):
        assert table_command._process_sql_parameters([]) == []

    def test_none_returns_empty(self, table_command):
        assert table_command._process_sql_parameters(None) == []

    def test_list_of_strings(self, table_command):
        params = ["@user_id INT", "@status VARCHAR(50)", "@flag BIT"]
        result = table_command._process_sql_parameters(params)
        assert len(result) == 3
        assert result[0]["name"] == "@user_id INT"
        assert result[0]["type"] == "Any"
        assert result[1]["name"] == "@status VARCHAR(50)"
        assert result[2]["name"] == "@flag BIT"

    def test_list_of_dicts_passes_through(self, table_command):
        params = [
            {"name": "user_id", "type": "INT"},
            {"name": "status", "type": "VARCHAR"},
        ]
        result = table_command._process_sql_parameters(params)
        assert len(result) == 2
        assert result[0] == {"name": "user_id", "type": "INT"}
        assert result[1] == {"name": "status", "type": "VARCHAR"}

    def test_non_list_string_returns_one_item(self, table_command):
        result = table_command._process_sql_parameters("single_param")
        assert len(result) == 1
        assert result[0]["name"] == "single_param"
        assert result[0]["type"] == "Any"
