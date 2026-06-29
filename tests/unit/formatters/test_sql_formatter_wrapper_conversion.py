"""
Tests for SQL Formatter Wrapper element conversion methods.
"""

import pytest

from tree_sitter_analyzer.formatters.sql_formatter_wrapper import SQLFormatterWrapper
from tree_sitter_analyzer.models import (
    AnalysisResult,
    SQLFunction,
    SQLIndex,
    SQLProcedure,
    SQLTable,
    SQLTrigger,
    SQLView,
)


@pytest.fixture
def formatter():
    return SQLFormatterWrapper()


class TestConvertAnalysisResultToSQLElements:
    """Test _convert_analysis_result_to_sql_elements method."""

    def test_convert_sql_element_passthrough(self, formatter):
        """Test that existing SQL elements pass through unchanged."""
        element = SQLTable(
            name="existing_table",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE existing_table (id INT);",
            language="sql",
        )
        result = AnalysisResult(file_path="test.sql", elements=[element])
        sql_elements = formatter._convert_analysis_result_to_sql_elements(result)
        assert len(sql_elements) == 1
        assert sql_elements[0].name == "existing_table"

    def test_convert_multiple_sql_elements(self, formatter):
        """Test conversion of multiple SQL elements."""
        elements = [
            SQLTable(
                name="users",
                start_line=1,
                end_line=5,
                raw_text="CREATE TABLE users (id INT);",
                language="sql",
            ),
            SQLView(
                name="user_view",
                start_line=6,
                end_line=8,
                raw_text="CREATE VIEW user_view AS SELECT * FROM users;",
                language="sql",
            ),
            SQLProcedure(
                name="update_user",
                start_line=9,
                end_line=15,
                raw_text="CREATE PROCEDURE update_user() BEGIN END;",
                language="sql",
            ),
            SQLFunction(
                name="calc_total",
                start_line=16,
                end_line=22,
                raw_text="CREATE FUNCTION calc_total() RETURNS INT BEGIN RETURN 0; END;",
                language="sql",
            ),
            SQLTrigger(
                name="audit_trigger",
                start_line=23,
                end_line=28,
                raw_text="CREATE TRIGGER audit_trigger BEFORE UPDATE ON users FOR EACH ROW BEGIN END;",
                language="sql",
            ),
            SQLIndex(
                name="idx_email",
                start_line=29,
                end_line=29,
                raw_text="CREATE INDEX idx_email ON users (email);",
                language="sql",
            ),
        ]
        result = AnalysisResult(file_path="test.sql", elements=elements)
        sql_elements = formatter._convert_analysis_result_to_sql_elements(result)
        assert len(sql_elements) == 6


class TestConvertToSQLElements:
    """Test _convert_to_sql_elements method."""

    def test_convert_empty_data(self, formatter):
        """Test conversion with empty data."""
        data = {"elements": [], "methods": []}
        result = formatter._convert_to_sql_elements(data)
        assert result == []

    def test_convert_sql_element_passthrough(self, formatter):
        """Test that SQL elements pass through unchanged."""
        element = SQLTable(
            name="test_table",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE test_table (id INT);",
            language="sql",
        )
        data = {"elements": [element], "methods": []}
        result = formatter._convert_to_sql_elements(data)
        assert len(result) == 1
        assert result[0].name == "test_table"

    def test_convert_dict_element(self, formatter):
        """Test conversion of dictionary element."""
        data = {
            "elements": [
                {
                    "name": "dict_table",
                    "type": "table",
                    "start_line": 1,
                    "end_line": 5,
                    "raw_text": "CREATE TABLE dict_table (id INT);",
                    "language": "sql",
                }
            ],
            "methods": [],
        }
        result = formatter._convert_to_sql_elements(data)
        assert len(result) == 1
        assert result[0].name == "dict_table"

    def test_convert_methods_included(self, formatter):
        """Test that methods are also converted."""
        data = {
            "elements": [],
            "methods": [
                SQLProcedure(
                    name="test_proc",
                    start_line=1,
                    end_line=10,
                    raw_text="CREATE PROCEDURE test_proc() BEGIN END;",
                    language="sql",
                )
            ],
        }
        result = formatter._convert_to_sql_elements(data)
        assert len(result) == 1


class TestElementToDict:
    """Test _element_to_dict method."""

    def test_element_to_dict_with_attributes(self, formatter):
        """Test conversion of element with all attributes."""
        element = SQLTable(
            name="test_table",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE test_table (id INT);",
            language="sql",
        )
        result = formatter._element_to_dict(element)
        assert result["name"] == "test_table"
        assert result["start_line"] == 1
        assert result["end_line"] == 5
        assert result["raw_text"] == "CREATE TABLE test_table (id INT);"
        assert result["language"] == "sql"


class TestCreateSQLElementFromDict:
    """Test _create_sql_element_from_dict method."""

    def test_create_table_element(self, formatter):
        """Test creation of table element."""
        data = {
            "name": "users",
            "type": "table",
            "start_line": 1,
            "end_line": 10,
            "raw_text": "CREATE TABLE users (id INT);",
            "language": "sql",
        }
        result = formatter._create_sql_element_from_dict(data)
        assert result is not None
        assert result.name == "users"

    def test_create_view_element(self, formatter):
        """Test creation of view element."""
        data = {
            "name": "user_view",
            "type": "view",
            "start_line": 1,
            "end_line": 5,
            "raw_text": "CREATE VIEW user_view AS SELECT * FROM users;",
            "language": "sql",
        }
        result = formatter._create_sql_element_from_dict(data)
        assert result is not None
        assert result.name == "user_view"

    def test_create_procedure_element(self, formatter):
        """Test creation of procedure element."""
        data = {
            "name": "update_user",
            "type": "procedure",
            "start_line": 1,
            "end_line": 15,
            "raw_text": "CREATE PROCEDURE update_user() BEGIN END;",
            "language": "sql",
        }
        result = formatter._create_sql_element_from_dict(data)
        assert result is not None
        assert result.name == "update_user"

    def test_create_function_element(self, formatter):
        """Test creation of function element."""
        data = {
            "name": "calc_total",
            "type": "function",
            "start_line": 1,
            "end_line": 10,
            "raw_text": "CREATE FUNCTION calc_total() RETURNS INT BEGIN RETURN 0; END;",
            "language": "sql",
        }
        result = formatter._create_sql_element_from_dict(data)
        assert result is not None
        assert result.name == "calc_total"

    def test_create_trigger_element(self, formatter):
        """Test creation of trigger element."""
        data = {
            "name": "audit_trigger",
            "type": "trigger",
            "start_line": 1,
            "end_line": 8,
            "raw_text": "CREATE TRIGGER audit_trigger BEFORE UPDATE ON users FOR EACH ROW BEGIN END;",
            "language": "sql",
        }
        result = formatter._create_sql_element_from_dict(data)
        assert result is not None
        assert result.name == "audit_trigger"

    def test_create_index_element(self, formatter):
        """Test creation of index element."""
        data = {
            "name": "idx_email",
            "type": "index",
            "start_line": 1,
            "end_line": 1,
            "raw_text": "CREATE INDEX idx_email ON users (email);",
            "language": "sql",
        }
        result = formatter._create_sql_element_from_dict(data)
        assert result is not None
        assert result.name == "idx_email"

    def test_create_unknown_type_fallback(self, formatter):
        """Test creation with unknown type falls back to SQLTable."""
        data = {
            "name": "unknown_element",
            "type": "unknown_type",
            "start_line": 1,
            "end_line": 5,
            "raw_text": "SOME SQL;",
            "language": "sql",
        }
        result = formatter._create_sql_element_from_dict(data)
        assert result is not None
        assert result.name == "unknown_element"

    def test_create_with_create_prefix_types(self, formatter):
        """Test creation with create_ prefix types."""
        for type_name in [
            "create_table",
            "create_view",
            "create_procedure",
            "create_function",
            "create_trigger",
            "create_index",
        ]:
            data = {
                "name": f"test_{type_name}",
                "type": type_name,
                "start_line": 1,
                "end_line": 5,
                "raw_text": f"CREATE {type_name.replace('create_', '').upper()} test;",
                "language": "sql",
            }
            result = formatter._create_sql_element_from_dict(data)
            assert result is not None
            assert result.name == f"test_{type_name}"
            # create_table → element_type "table", create_view → "view", etc.
            expected_element_type = type_name.replace("create_", "")
            assert result.element_type == expected_element_type
