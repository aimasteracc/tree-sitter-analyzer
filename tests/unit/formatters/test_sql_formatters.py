#!/usr/bin/env python3
"""
Comprehensive tests for SQL formatters

Tests the SQL-specific formatters with various SQL elements and edge cases.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.formatters.sql_formatters import (
    SQLCompactFormatter,
    SQLCSVFormatter,
    SQLFullFormatter,
)
from tree_sitter_analyzer.models import (
    SQLColumn,
    SQLConstraint,
    SQLElement,
    SQLElementType,
    SQLFunction,
    SQLIndex,
    SQLParameter,
    SQLProcedure,
    SQLTable,
    SQLTrigger,
    SQLView,
)


class TestSQLFormatterBase:
    """Test base functionality of SQL formatters"""

    def test_empty_elements_list(self):
        """Test formatting with empty elements list"""
        formatter = SQLFullFormatter()
        result = formatter.format_elements([], "test.sql")

        assert "# test.sql" in result
        assert "No SQL elements found." in result

    def test_group_elements_by_type(self):
        """Test grouping elements by SQL type"""
        formatter = SQLFullFormatter()

        # Create test elements
        table = SQLTable(
            name="users",
            start_line=1,
            end_line=10,
            raw_text="CREATE TABLE users...",
            sql_element_type=SQLElementType.TABLE,
        )

        view = SQLView(
            name="active_users",
            start_line=15,
            end_line=20,
            raw_text="CREATE VIEW active_users...",
            sql_element_type=SQLElementType.VIEW,
        )

        elements = [table, view]
        grouped = formatter.group_elements_by_type(elements)

        assert SQLElementType.TABLE in grouped
        assert SQLElementType.VIEW in grouped
        assert len(grouped[SQLElementType.TABLE]) == 1
        assert len(grouped[SQLElementType.VIEW]) == 1
        assert grouped[SQLElementType.TABLE][0].name == "users"
        assert grouped[SQLElementType.VIEW][0].name == "active_users"


class TestSQLFullFormatter:
    """Test SQL full formatter with detailed metadata"""

    @pytest.fixture
    def sample_elements(self) -> list[SQLElement]:
        """Create sample SQL elements for testing"""
        # Create table with columns and constraints
        table_columns = [
            SQLColumn(name="id", data_type="INT", nullable=False, is_primary_key=True),
            SQLColumn(name="username", data_type="VARCHAR(100)", nullable=False),
            SQLColumn(name="email", data_type="VARCHAR(255)", nullable=False),
            SQLColumn(
                name="user_id",
                data_type="INT",
                nullable=False,
                is_foreign_key=True,
                foreign_key_reference="users(id)",
            ),
        ]

        table_constraints = [
            SQLConstraint(
                name="pk_users", constraint_type="PRIMARY_KEY", columns=["id"]
            ),
            SQLConstraint(
                name="uk_username", constraint_type="UNIQUE", columns=["username"]
            ),
        ]

        table = SQLTable(
            name="users",
            start_line=5,
            end_line=13,
            raw_text="CREATE TABLE users...",
            sql_element_type=SQLElementType.TABLE,
            columns=table_columns,
            constraints=table_constraints,
            dependencies=[],
        )

        # Create view
        view = SQLView(
            name="active_users",
            start_line=37,
            end_line=44,
            raw_text="CREATE VIEW active_users...",
            sql_element_type=SQLElementType.VIEW,
            source_tables=["users"],
            dependencies=["users"],
        )

        # Create procedure with parameters
        proc_parameters = [
            SQLParameter(name="user_id_param", data_type="INT", direction="IN")
        ]

        procedure = SQLProcedure(
            name="get_user_orders",
            start_line=58,
            end_line=68,
            raw_text="CREATE PROCEDURE get_user_orders...",
            sql_element_type=SQLElementType.PROCEDURE,
            parameters=proc_parameters,
            dependencies=["orders"],
        )

        # Create function with return type
        func_parameters = [
            SQLParameter(name="order_id_param", data_type="INT", direction="IN")
        ]

        function = SQLFunction(
            name="calculate_order_total",
            start_line=89,
            end_line=101,
            raw_text="CREATE FUNCTION calculate_order_total...",
            sql_element_type=SQLElementType.FUNCTION,
            parameters=func_parameters,
            return_type="DECIMAL(10, 2)",
            dependencies=["order_items"],
        )

        # Create trigger
        trigger = SQLTrigger(
            name="update_order_total",
            start_line=119,
            end_line=130,
            raw_text="CREATE TRIGGER update_order_total...",
            sql_element_type=SQLElementType.TRIGGER,
            trigger_timing="AFTER",
            trigger_event="INSERT",
            table_name="order_items",
            dependencies=["orders", "order_items"],
        )

        # Create index
        index = SQLIndex(
            name="idx_users_email",
            start_line=151,
            end_line=151,
            raw_text="CREATE INDEX idx_users_email...",
            sql_element_type=SQLElementType.INDEX,
            table_name="users",
            indexed_columns=["email"],
            is_unique=False,
            dependencies=["users"],
        )

        return [table, view, procedure, function, trigger, index]

    def test_full_format_output_structure(self, sample_elements):
        """Test full format output structure"""
        formatter = SQLFullFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        # Check header
        assert "# sample_database.sql" in result

        # Check overview table
        assert "## Database Schema Overview" in result
        assert (
            "| Element | Type | Lines | Columns/Parameters | Dependencies |" in result
        )

        # Check section headers
        assert "## Tables" in result
        assert "## Views" in result
        assert "## Procedures" in result
        assert "## Functions" in result
        assert "## Triggers" in result
        assert "## Indexes" in result

    def test_overview_table_content(self, sample_elements):
        """Test overview table content"""
        formatter = SQLFullFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        # Check table entries - update to match actual output format
        assert "| users | table | 5-13 | 4 columns | - |" in result
        assert "| active_users | view | 37-44 | from users | users |" in result
        assert (
            "| get_user_orders | procedure | 58-68 | (user_id_param) | orders |"
            in result
        )
        assert (
            "| calculate_order_total | function | 89-101 | (order_id_param) | order_items |"
            in result
        )
        assert (
            "| update_order_total | trigger | 119-130 | - | orders, order_items |"
            in result
        )
        assert "| idx_users_email | index | 151-151 | users(email) | users |" in result

    def test_table_details_formatting(self, sample_elements):
        """Test table details formatting"""
        formatter = SQLFullFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        # Check table section - update to match actual output format
        assert "### users (5-13)" in result
        assert "**Columns**: id, username, email, user_id" in result
        assert "**Primary Key**: id" in result
        assert "**Foreign Keys**: user_id → users(id)" in result
        # Constraints order is not guaranteed due to set() usage, so check both are present
        assert "**Constraints**:" in result
        assert "UNIQUE" in result
        assert "PRIMARY_KEY" in result

    def test_view_details_formatting(self, sample_elements):
        """Test view details formatting"""
        formatter = SQLFullFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        # Check view section
        assert "### active_users (37-44)" in result
        assert "**Source Tables**: users" in result

    def test_procedure_details_formatting(self, sample_elements):
        """Test procedure details formatting"""
        formatter = SQLFullFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        # Check procedure section
        assert "### get_user_orders (58-68)" in result
        assert "**Parameters**: user_id_param INT" in result
        assert "**Dependencies**: orders" in result

    def test_function_details_formatting(self, sample_elements):
        """Test function details formatting"""
        formatter = SQLFullFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        # Check function section
        assert "### calculate_order_total (89-101)" in result
        assert "**Parameters**: order_id_param INT" in result
        assert "**Returns**: DECIMAL(10, 2)" in result
        assert "**Dependencies**: order_items" in result

    def test_trigger_details_formatting(self, sample_elements):
        """Test trigger details formatting"""
        formatter = SQLFullFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        # Check trigger section
        assert "### update_order_total (119-130)" in result
        assert "**Event**: AFTER INSERT" in result
        assert "**Target Table**: order_items" in result
        assert "**Dependencies**: orders, order_items" in result

    def test_index_details_formatting(self, sample_elements):
        """Test index details formatting"""
        formatter = SQLFullFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        # Check index section
        assert "### idx_users_email (151-151)" in result
        assert "**Table**: users" in result
        assert "**Columns**: email" in result
        assert "**Type**: Standard index" in result


class TestSQLCompactFormatter:
    """Test SQL compact formatter"""

    @pytest.fixture
    def sample_elements(self) -> list[SQLElement]:
        """Create sample SQL elements for testing"""
        table = SQLTable(
            name="users",
            start_line=5,
            end_line=13,
            raw_text="CREATE TABLE users...",
            sql_element_type=SQLElementType.TABLE,
            columns=[
                SQLColumn(name="id", data_type="INT", is_primary_key=True),
                SQLColumn(name="username", data_type="VARCHAR(100)"),
            ],
        )

        view = SQLView(
            name="active_users",
            start_line=37,
            end_line=44,
            raw_text="CREATE VIEW active_users...",
            sql_element_type=SQLElementType.VIEW,
            source_tables=["users"],
        )

        procedure = SQLProcedure(
            name="get_user_orders",
            start_line=58,
            end_line=68,
            raw_text="CREATE PROCEDURE get_user_orders...",
            sql_element_type=SQLElementType.PROCEDURE,
            parameters=[SQLParameter(name="user_id_param", data_type="INT")],
        )

        function = SQLFunction(
            name="calculate_total",
            start_line=89,
            end_line=101,
            raw_text="CREATE FUNCTION calculate_total...",
            sql_element_type=SQLElementType.FUNCTION,
            parameters=[SQLParameter(name="order_id", data_type="INT")],
            return_type="DECIMAL(10, 2)",
        )

        trigger = SQLTrigger(
            name="update_order_total",
            start_line=119,
            end_line=130,
            raw_text="CREATE TRIGGER update_order_total...",
            sql_element_type=SQLElementType.TRIGGER,
            trigger_timing="AFTER",
            trigger_event="INSERT",
            table_name="order_items",
        )

        index = SQLIndex(
            name="idx_users_email",
            start_line=151,
            end_line=151,
            raw_text="CREATE INDEX idx_users_email...",
            sql_element_type=SQLElementType.INDEX,
            table_name="users",
            indexed_columns=["email"],
            is_unique=True,
        )

        return [table, view, procedure, function, trigger, index]

    def test_compact_format_structure(self, sample_elements):
        """Test compact format structure"""
        formatter = SQLCompactFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        # Check header
        assert "# sample_database.sql" in result

        # Check table header
        assert "| Element | Type | Lines | Details |" in result
        assert "|---------|------|-------|---------|" in result

    def test_compact_format_content(self, sample_elements):
        """Test compact format content"""
        formatter = SQLCompactFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        # Check element entries - update to match actual output format (-> not →)
        assert "| users | table | 5-13 | 2 cols, PK: id |" in result
        assert "| active_users | view | 37-44 | from users |" in result
        assert "| get_user_orders | procedure | 58-68 | 1 params |" in result
        assert (
            "| calculate_total | function | 89-101 | 1 params, -> DECIMAL(10, 2) |"
            in result
        )
        assert (
            "| update_order_total | trigger | 119-130 | AFTER INSERT, on order_items |"
            in result
        )
        assert (
            "| idx_users_email | index | 151-151 | on users, (email), UNIQUE |"
            in result
        )


class TestSQLCSVFormatter:
    """Test SQL CSV formatter"""

    @pytest.fixture
    def sample_elements(self) -> list[SQLElement]:
        """Create sample SQL elements for testing"""
        table = SQLTable(
            name="users",
            start_line=5,
            end_line=13,
            raw_text="CREATE TABLE users...",
            sql_element_type=SQLElementType.TABLE,
            columns=[
                SQLColumn(name="id", data_type="INT"),
                SQLColumn(name="username", data_type="VARCHAR(100)"),
            ],
            dependencies=[],
        )

        view = SQLView(
            name="active_users",
            start_line=37,
            end_line=44,
            raw_text="CREATE VIEW active_users...",
            sql_element_type=SQLElementType.VIEW,
            dependencies=["users"],
        )

        procedure = SQLProcedure(
            name="get_user_orders",
            start_line=58,
            end_line=68,
            raw_text="CREATE PROCEDURE get_user_orders...",
            sql_element_type=SQLElementType.PROCEDURE,
            parameters=[SQLParameter(name="user_id_param", data_type="INT")],
            dependencies=["orders", "users"],
        )

        index = SQLIndex(
            name="idx_users_email",
            start_line=151,
            end_line=151,
            raw_text="CREATE INDEX idx_users_email...",
            sql_element_type=SQLElementType.INDEX,
            indexed_columns=["email", "username"],
            dependencies=["users"],
        )

        return [table, view, procedure, index]

    def test_csv_format_structure(self, sample_elements):
        """Test CSV format structure"""
        formatter = SQLCSVFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        # Check CSV header
        assert "Element,Type,Lines,Columns_Parameters,Dependencies" in result

    def test_csv_format_content(self, sample_elements):
        """Test CSV format content"""
        formatter = SQLCSVFormatter()
        result = formatter.format_elements(sample_elements, "sample_database.sql")

        lines = result.strip().split("\n")

        # Check header
        assert lines[0] == "Element,Type,Lines,Columns_Parameters,Dependencies"

        # Check data rows
        assert "users,table,5-13,2 columns," in result
        assert "active_users,view,37-44,,users" in result
        assert "get_user_orders,procedure,58-68,1 parameters,orders;users" in result
        assert "idx_users_email,index,151-151,email;username,users" in result


class TestSQLFormatterEdgeCases:
    """Test SQL formatters with edge cases"""

    def test_empty_file_formatting(self):
        """Test formatting empty SQL file"""
        formatter = SQLFullFormatter()
        result = formatter.format_elements([], "empty.sql")

        assert "# empty.sql" in result
        assert "No SQL elements found." in result

    def test_single_element_formatting(self):
        """Test formatting with single element"""
        table = SQLTable(
            name="simple_table",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE simple_table...",
            sql_element_type=SQLElementType.TABLE,
        )

        formatter = SQLFullFormatter()
        result = formatter.format_elements([table], "simple.sql")

        assert "# simple.sql" in result
        assert "## Database Schema Overview" in result
        assert "## Tables" in result
        assert "### simple_table (1-5)" in result

    def test_elements_without_metadata(self):
        """Test formatting elements without detailed metadata"""
        # Create minimal elements
        table = SQLTable(
            name="minimal_table",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE minimal_table...",
            sql_element_type=SQLElementType.TABLE,
        )

        view = SQLView(
            name="minimal_view",
            start_line=10,
            end_line=15,
            raw_text="CREATE VIEW minimal_view...",
            sql_element_type=SQLElementType.VIEW,
        )

        elements = [table, view]

        # Test full formatter
        full_formatter = SQLFullFormatter()
        full_result = full_formatter.format_elements(elements, "minimal.sql")

        assert "minimal_table" in full_result
        assert "minimal_view" in full_result

        # Test compact formatter
        compact_formatter = SQLCompactFormatter()
        compact_result = compact_formatter.format_elements(elements, "minimal.sql")

        assert "minimal_table" in compact_result
        assert "minimal_view" in compact_result

        # Test CSV formatter
        csv_formatter = SQLCSVFormatter()
        csv_result = csv_formatter.format_elements(elements, "minimal.sql")

        assert "minimal_table" in csv_result
        assert "minimal_view" in csv_result

    def test_elements_sorting_by_line_number(self):
        """Test that elements are sorted by line number"""
        # Create elements in reverse order
        table2 = SQLTable(
            name="table_second",
            start_line=20,
            end_line=25,
            raw_text="CREATE TABLE table_second...",
            sql_element_type=SQLElementType.TABLE,
        )

        table1 = SQLTable(
            name="table_first",
            start_line=5,
            end_line=10,
            raw_text="CREATE TABLE table_first...",
            sql_element_type=SQLElementType.TABLE,
        )

        elements = [table2, table1]  # Reverse order

        formatter = SQLFullFormatter()
        result = formatter.format_elements(elements, "test.sql")

        # Check that table_first appears before table_second in output
        first_pos = result.find("table_first")
        second_pos = result.find("table_second")

        assert first_pos < second_pos

    def test_filename_extraction(self):
        """Test filename extraction from file path"""
        table = SQLTable(
            name="test_table",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE test_table...",
            sql_element_type=SQLElementType.TABLE,
        )

        formatter = SQLFullFormatter()

        # Test with full path
        result1 = formatter.format_elements([table], "/path/to/database.sql")
        assert "# database.sql" in result1

        # Test with relative path
        result2 = formatter.format_elements([table], "schemas/main.sql")
        assert "# main.sql" in result2

        # Test with no path
        result3 = formatter.format_elements([table], "")
        assert "# unknown.sql" in result3


class TestSQLFormatterIntegration:
    """Integration tests for SQL formatters"""

    def test_real_sql_file_formatting(self):
        """Test formatting with real SQL file if available"""
        sample_sql_file = Path("examples/sample_database.sql")

        if not sample_sql_file.exists():
            pytest.skip(f"Sample SQL file not found: {sample_sql_file}")

        # This test would require actual SQL parsing integration
        # For now, we'll just verify the file exists
        assert sample_sql_file.exists()
        assert sample_sql_file.suffix == ".sql"

    def test_formatter_consistency(self):
        """Test that all formatters handle the same elements consistently"""
        table = SQLTable(
            name="consistency_test",
            start_line=1,
            end_line=10,
            raw_text="CREATE TABLE consistency_test...",
            sql_element_type=SQLElementType.TABLE,
            columns=[SQLColumn(name="id", data_type="INT")],
            dependencies=[],
        )

        elements = [table]

        # Test all formatters
        full_formatter = SQLFullFormatter()
        compact_formatter = SQLCompactFormatter()
        csv_formatter = SQLCSVFormatter()

        full_result = full_formatter.format_elements(elements, "test.sql")
        compact_result = compact_formatter.format_elements(elements, "test.sql")
        csv_result = csv_formatter.format_elements(elements, "test.sql")

        # All should contain the table name
        assert "consistency_test" in full_result
        assert "consistency_test" in compact_result
        assert "consistency_test" in csv_result

        # All should contain the element type
        assert "table" in full_result.lower()
        assert "table" in compact_result.lower()
        assert "table" in csv_result.lower()


if __name__ == "__main__":
    pytest.main([__file__])
