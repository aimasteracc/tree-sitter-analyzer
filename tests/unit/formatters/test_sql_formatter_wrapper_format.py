"""
Tests for SQL Formatter Wrapper formatting methods.
"""

import pytest

from tree_sitter_analyzer.formatters.sql_formatter_wrapper import SQLFormatterWrapper
from tree_sitter_analyzer.models import (
    AnalysisResult,
    SQLElement,
    SQLElementType,
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


class TestSQLFormatterWrapperInit:
    """Test initialization of SQLFormatterWrapper."""

    def test_init_creates_formatters(self, formatter):
        """Test that init creates all required formatters."""
        assert "full" in formatter._formatters
        assert "compact" in formatter._formatters
        assert "csv" in formatter._formatters


class TestFormatTable:
    """Test format_table method."""

    def test_format_table_full(self, formatter):
        """Test format_table with full type."""
        data = {
            "file_path": "test.sql",
            "elements": [
                SQLTable(
                    name="users",
                    start_line=1,
                    end_line=5,
                    raw_text="CREATE TABLE users (id INT);",
                    language="sql",
                )
            ],
        }
        result = formatter.format_table(data, "full")
        assert "users" in result

    def test_format_table_csv(self, formatter):
        """Test format_table with csv type."""
        data = {
            "file_path": "test.sql",
            "elements": [
                SQLTable(
                    name="products",
                    start_line=1,
                    end_line=3,
                    raw_text="CREATE TABLE products (id INT);",
                    language="sql",
                )
            ],
        }
        result = formatter.format_table(data, "csv")
        assert isinstance(result, str)

    def test_format_table_unsupported_type(self, formatter):
        """Test format_table with unsupported type raises ValueError."""
        data = {"file_path": "test.sql", "elements": []}
        with pytest.raises(ValueError) as exc_info:
            formatter.format_table(data, "invalid_type")
        assert "Unsupported table type" in str(exc_info.value)

    def test_format_table_default_file_path(self, formatter):
        """Test format_table with missing file_path uses default."""
        data = {"elements": []}
        result = formatter.format_table(data, "full")
        assert isinstance(result, str)


class TestFormatAnalysisResult:
    """Test format_analysis_result method."""

    def test_format_analysis_result_basic(self, formatter):
        """Test basic format_analysis_result."""
        element = SQLElement(
            name="test_table",
            sql_element_type=SQLElementType.TABLE,
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE test_table (id INT);",
        )
        result = AnalysisResult(file_path="test.sql", elements=[element])
        output = formatter.format_analysis_result(result, "full")
        assert "test_table" in output

    def test_format_analysis_result_invalid_type_fallback(self, formatter):
        """Test format_analysis_result falls back to full for invalid type."""
        element = SQLElement(
            name="test_table",
            sql_element_type=SQLElementType.TABLE,
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE test_table (id INT);",
        )
        result = AnalysisResult(file_path="test.sql", elements=[element])
        output = formatter.format_analysis_result(result, "invalid_type")
        assert isinstance(output, str)

    def test_format_analysis_result_with_view(self, formatter):
        """Test format_analysis_result with view element."""
        element = SQLView(
            name="user_view",
            start_line=1,
            end_line=3,
            raw_text="CREATE VIEW user_view AS SELECT * FROM users;",
            language="sql",
        )
        result = AnalysisResult(file_path="test.sql", elements=[element])
        output = formatter.format_analysis_result(result, "full")
        assert "user_view" in output

    def test_format_analysis_result_with_procedure(self, formatter):
        """Test format_analysis_result with procedure element."""
        element = SQLProcedure(
            name="update_user",
            start_line=1,
            end_line=10,
            raw_text="CREATE PROCEDURE update_user() BEGIN END;",
            language="sql",
        )
        result = AnalysisResult(file_path="test.sql", elements=[element])
        output = formatter.format_analysis_result(result, "full")
        assert "update_user" in output

    def test_format_analysis_result_with_function(self, formatter):
        """Test format_analysis_result with function element."""
        element = SQLFunction(
            name="calc_total",
            start_line=1,
            end_line=8,
            raw_text="CREATE FUNCTION calc_total() RETURNS INT BEGIN RETURN 0; END;",
            language="sql",
        )
        result = AnalysisResult(file_path="test.sql", elements=[element])
        output = formatter.format_analysis_result(result, "full")
        assert "calc_total" in output

    def test_format_analysis_result_with_trigger(self, formatter):
        """Test format_analysis_result with trigger element."""
        element = SQLTrigger(
            name="audit_trigger",
            start_line=1,
            end_line=6,
            raw_text="CREATE TRIGGER audit_trigger BEFORE UPDATE ON users FOR EACH ROW BEGIN END;",
            language="sql",
        )
        result = AnalysisResult(file_path="test.sql", elements=[element])
        output = formatter.format_analysis_result(result, "full")
        assert "audit_trigger" in output

    def test_format_analysis_result_with_index(self, formatter):
        """Test format_analysis_result with index element."""
        element = SQLIndex(
            name="idx_email",
            start_line=1,
            end_line=1,
            raw_text="CREATE INDEX idx_email ON users (email);",
            language="sql",
        )
        result = AnalysisResult(file_path="test.sql", elements=[element])
        output = formatter.format_analysis_result(result, "full")
        assert "idx_email" in output


class TestFormatElements:
    """Test format_elements method."""

    def test_format_elements_with_sql_elements(self, formatter):
        """Test format_elements with SQL elements."""
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
        ]
        result = formatter.format_elements(elements, "full")
        assert "users" in result
        assert "user_view" in result

    def test_format_elements_with_dict_elements(self, formatter):
        """Test format_elements with dictionary elements."""
        elements = [
            {
                "name": "dict_table",
                "type": "table",
                "start_line": 1,
                "end_line": 5,
                "raw_text": "CREATE TABLE dict_table (id INT);",
                "language": "sql",
            }
        ]
        result = formatter.format_elements(elements, "full")
        assert "dict_table" in result

    def test_format_elements_invalid_type_fallback(self, formatter):
        """Test format_elements falls back to full for invalid type."""
        elements = [
            SQLTable(
                name="test",
                start_line=1,
                end_line=5,
                raw_text="CREATE TABLE test (id INT);",
                language="sql",
            )
        ]
        result = formatter.format_elements(elements, "invalid_type")
        assert isinstance(result, str)

    def test_format_elements_compact(self, formatter):
        """Test format_elements with compact format."""
        elements = [
            SQLTable(
                name="compact_table",
                start_line=1,
                end_line=5,
                raw_text="CREATE TABLE compact_table (id INT);",
                language="sql",
            )
        ]
        result = formatter.format_elements(elements, "compact")
        assert isinstance(result, str)

    def test_format_elements_csv(self, formatter):
        """Test format_elements with csv format."""
        elements = [
            SQLTable(
                name="csv_table",
                start_line=1,
                end_line=5,
                raw_text="CREATE TABLE csv_table (id INT);",
                language="sql",
            )
        ]
        result = formatter.format_elements(elements, "csv")
        assert isinstance(result, str)


class TestSupportsLanguage:
    """Test supports_language method."""

    def test_supports_sql(self, formatter):
        """Test that SQL is supported."""
        assert formatter.supports_language("sql") is True
        assert formatter.supports_language("SQL") is True
        assert formatter.supports_language("Sql") is True

    def test_does_not_support_other_languages(self, formatter):
        """Test that other languages are not supported."""
        assert formatter.supports_language("python") is False
        assert formatter.supports_language("java") is False
        assert formatter.supports_language("javascript") is False


class TestFormatStructure:
    """Test format_structure method."""

    def test_format_structure(self, formatter):
        """Test format_structure uses full formatter."""
        data = {
            "file_path": "test.sql",
            "elements": [
                SQLTable(
                    name="structure_table",
                    start_line=1,
                    end_line=5,
                    raw_text="CREATE TABLE structure_table (id INT);",
                    language="sql",
                )
            ],
        }
        result = formatter.format_structure(data)
        assert isinstance(result, str)


class TestFormatAdvanced:
    """Test format_advanced method."""

    def test_format_advanced_json(self, formatter):
        """Test format_advanced with json output."""
        data = {"file_path": "test.sql", "elements": [], "test_key": "test_value"}
        result = formatter.format_advanced(data, "json")
        assert "test_key" in result
        assert "test_value" in result

    def test_format_advanced_table(self, formatter):
        """Test format_advanced with table output."""
        data = {
            "file_path": "test.sql",
            "elements": [
                SQLTable(
                    name="advanced_table",
                    start_line=1,
                    end_line=5,
                    raw_text="CREATE TABLE advanced_table (id INT);",
                    language="sql",
                )
            ],
        }
        result = formatter.format_advanced(data, "table")
        assert isinstance(result, str)
