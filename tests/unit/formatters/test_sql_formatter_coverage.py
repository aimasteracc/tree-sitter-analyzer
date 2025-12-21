import pytest

from tree_sitter_analyzer.formatters.sql_formatters import (
    SQLFormatterBase,
    SQLFullFormatter,
)
from tree_sitter_analyzer.models import (
    AnalysisResult,
    SQLColumn,
    SQLFunction,
    SQLIndex,
    SQLParameter,
    SQLTable,
    SQLView,
)


class TestSQLFormatterCoverage:
    def test_format_empty_file(self):
        formatter = SQLFullFormatter()
        result = formatter.format_elements([], "test.sql")
        assert "# test.sql" in result
        assert "No SQL elements found" in result

    def test_format_analysis_result_empty(self):
        formatter = SQLFullFormatter()
        result = formatter.format_analysis_result(None)
        assert "No SQL elements found" in result

        empty_result = AnalysisResult(
            file_path="empty.sql",
            language="sql",
            line_count=0,
            elements=[],
            node_count=0,
            query_results={},
            source_code="",
            success=True,
            error_message=None,
        )
        result = formatter.format_analysis_result(empty_result)
        assert "# empty.sql" in result
        assert "No SQL elements found" in result

    def test_format_analysis_result_no_sql_elements(self):
        formatter = SQLFullFormatter()

        # Create a dummy element that is not an SQLElement
        class DummyElement:
            name = "dummy"

        result_with_dummy = AnalysisResult(
            file_path="dummy.sql",
            language="sql",
            line_count=0,
            elements=[DummyElement()],
            node_count=0,
            query_results={},
            source_code="",
            success=True,
            error_message=None,
        )
        result = formatter.format_analysis_result(result_with_dummy)
        assert "No SQL elements found" in result

    def test_format_overview_table_complex_elements(self):
        formatter = SQLFullFormatter()

        # Create elements with various properties to cover branches in _format_overview_table
        table = SQLTable(
            name="users",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE...",
            language="sql",
            columns=[SQLColumn(name="id", data_type="INT")],
            constraints=[],
        )

        view = SQLView(
            name="active_users",
            start_line=10,
            end_line=15,
            raw_text="CREATE VIEW...",
            language="sql",
            source_tables=["users"],
            dependencies=["users"],
        )

        func = SQLFunction(
            name="calculate_total",
            start_line=20,
            end_line=25,
            raw_text="CREATE FUNCTION...",
            language="sql",
            parameters=[
                SQLParameter(name="order_id", data_type="INT"),
                SQLParameter(name="SELECT", data_type="KEYWORD"),
            ],  # Test keyword filtering
        )

        index = SQLIndex(
            name="idx_users_email",
            start_line=30,
            end_line=30,
            raw_text="CREATE INDEX...",
            language="sql",
            table_name="users",
            indexed_columns=["email"],
            is_unique=True,
        )

        elements = [table, view, func, index]
        result = formatter.format_elements(elements, "complex.sql")

        assert "| users | table | 1-5 | 1 columns | - |" in result
        assert "| active_users | view | 10-15 | from users | users |" in result
        assert (
            "| calculate_total | function | 20-25 | (order_id) | - |" in result
        )  # SELECT should be filtered
        assert "| idx_users_email | index | 30-30 | users(email) | - |" in result

    def test_base_formatter_not_implemented(self):
        formatter = SQLFormatterBase()
        with pytest.raises(NotImplementedError):
            formatter._format_grouped_elements({}, "test.sql")
