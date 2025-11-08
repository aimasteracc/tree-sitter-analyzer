#!/usr/bin/env python3
"""
Comprehensive SQL Formatters Tests

Tests for SQL-specific formatters including full, compact, and CSV formats.
Validates SQL-specific terminology, metadata extraction, and format consistency.
"""

import pytest

from tree_sitter_analyzer.formatters.sql_formatters import (
    SQLCompactFormatter,
    SQLCSVFormatter,
    SQLFullFormatter,
)
from tree_sitter_analyzer.models import (
    SQLColumn,
    SQLConstraint,
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

    def test_group_elements_by_type(self):
        """Test element grouping by SQL type"""
        formatter = SQLFullFormatter()

        # Create test elements
        table = SQLTable(
            name="users",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE users...",
            language="sql",
            columns=[],
            constraints=[],
        )

        view = SQLView(
            name="active_users",
            start_line=7,
            end_line=9,
            raw_text="CREATE VIEW active_users...",
            language="sql",
            source_tables=["users"],
            dependencies=["users"],
        )

        elements = [table, view]
        grouped = formatter.group_elements_by_type(elements)

        assert SQLElementType.TABLE in grouped
        assert SQLElementType.VIEW in grouped
        assert len(grouped[SQLElementType.TABLE]) == 1
        assert len(grouped[SQLElementType.VIEW]) == 1
        assert grouped[SQLElementType.TABLE][0].name == "users"
        assert grouped[SQLElementType.VIEW][0].name == "active_users"

    def test_format_empty_file(self):
        """Test formatting of empty SQL file"""
        formatter = SQLFullFormatter()
        result = formatter._format_empty_file("test.sql")

        assert "test.sql" in result
        assert "No SQL elements found" in result


class TestSQLFullFormatter:
    """Test SQL full format output"""

    def create_sample_table(self) -> SQLTable:
        """Create a sample table for testing"""
        columns = [
            SQLColumn(
                name="id",
                data_type="INTEGER",
                nullable=False,
                is_primary_key=True,
            ),
            SQLColumn(
                name="name",
                data_type="VARCHAR(100)",
                nullable=False,
                is_primary_key=False,
            ),
            SQLColumn(
                name="email",
                data_type="VARCHAR(255)",
                nullable=True,
                is_primary_key=False,
            ),
        ]

        constraints = [
            SQLConstraint(
                name="pk_users",
                constraint_type="PRIMARY KEY",
                columns=["id"],
            ),
            SQLConstraint(
                name="uk_users_email",
                constraint_type="UNIQUE",
                columns=["email"],
            ),
        ]

        return SQLTable(
            name="users",
            start_line=1,
            end_line=8,
            raw_text="CREATE TABLE users (...)",
            language="sql",
            columns=columns,
            constraints=constraints,
        )

    def create_sample_view(self) -> SQLView:
        """Create a sample view for testing"""
        return SQLView(
            name="active_users",
            start_line=10,
            end_line=12,
            raw_text="CREATE VIEW active_users AS SELECT * FROM users WHERE active = 1",
            language="sql",
            source_tables=["users"],
            dependencies=["users"],
        )

    def create_sample_procedure(self) -> SQLProcedure:
        """Create a sample procedure for testing"""
        parameters = [
            SQLParameter(
                name="user_id",
                data_type="INT",
                direction="IN",
            ),
            SQLParameter(
                name="result_count",
                data_type="INT",
                direction="OUT",
            ),
        ]

        return SQLProcedure(
            name="get_user_info",
            start_line=14,
            end_line=20,
            raw_text="CREATE PROCEDURE get_user_info (...)",
            language="sql",
            parameters=parameters,
            dependencies=["users"],
        )

    def create_sample_function(self) -> SQLFunction:
        """Create a sample function for testing"""
        parameters = [
            SQLParameter(
                name="birth_date",
                data_type="DATE",
                direction="IN",
            ),
        ]

        return SQLFunction(
            name="calculate_age",
            start_line=22,
            end_line=26,
            raw_text="CREATE FUNCTION calculate_age (...)",
            language="sql",
            parameters=parameters,
            return_type="INT",
            dependencies=[],
        )

    def create_sample_trigger(self) -> SQLTrigger:
        """Create a sample trigger for testing"""
        return SQLTrigger(
            name="user_audit",
            start_line=28,
            end_line=34,
            raw_text="CREATE TRIGGER user_audit ...",
            language="sql",
            table_name="users",
            trigger_timing="AFTER",
            trigger_event="INSERT",
            dependencies=["users", "audit_log"],
        )

    def create_sample_index(self) -> SQLIndex:
        """Create a sample index for testing"""
        return SQLIndex(
            name="idx_user_email",
            start_line=36,
            end_line=36,
            raw_text="CREATE INDEX idx_user_email ON users(email)",
            language="sql",
            table_name="users",
            indexed_columns=["email"],
            is_unique=False,
            dependencies=["users"],
        )

    def test_full_format_overview_table(self):
        """Test overview table generation"""
        formatter = SQLFullFormatter()
        table = self.create_sample_table()
        view = self.create_sample_view()

        elements = [table, view]
        grouped = formatter.group_elements_by_type(elements)
        overview = formatter._format_overview_table(grouped)

        # Check header
        assert "Database Schema Overview" in overview[0]
        assert (
            "| Element | Type | Lines | Columns/Parameters | Dependencies |"
            in overview[1]
        )

        # Check table row
        table_row = next((line for line in overview if "users" in line), None)
        assert table_row is not None
        assert "table" in table_row.lower()
        assert "1-8" in table_row
        assert "3 columns" in table_row

        # Check view row
        view_row = next((line for line in overview if "active_users" in line), None)
        assert view_row is not None
        assert "view" in view_row.lower()
        assert "10-12" in view_row
        assert "users" in view_row

    def test_full_format_table_details(self):
        """Test table detail formatting"""
        formatter = SQLFullFormatter()
        table = self.create_sample_table()

        details = formatter._format_table_details(table)

        # Check columns
        columns_line = next((line for line in details if "Columns" in line), None)
        assert columns_line is not None
        assert "id, name, email" in columns_line

        # Check primary key
        pk_line = next((line for line in details if "Primary Key" in line), None)
        assert pk_line is not None
        assert "id" in pk_line

        # Check constraints
        constraints_line = next(
            (line for line in details if "Constraints" in line), None
        )
        assert constraints_line is not None

    def test_full_format_procedure_details(self):
        """Test procedure detail formatting"""
        formatter = SQLFullFormatter()
        procedure = self.create_sample_procedure()

        details = formatter._format_procedure_details(procedure)

        # Check parameters
        params_line = next((line for line in details if "Parameters" in line), None)
        assert params_line is not None
        assert "user_id INT" in params_line
        assert "OUT result_count INT" in params_line

        # Check dependencies
        deps_line = next((line for line in details if "Dependencies" in line), None)
        assert deps_line is not None
        assert "users" in deps_line

    def test_full_format_function_details(self):
        """Test function detail formatting"""
        formatter = SQLFullFormatter()
        function = self.create_sample_function()

        details = formatter._format_function_details(function)

        # Check parameters
        params_line = next((line for line in details if "Parameters" in line), None)
        assert params_line is not None
        assert "birth_date DATE" in params_line

        # Check return type
        returns_line = next((line for line in details if "Returns" in line), None)
        assert returns_line is not None
        assert "INT" in returns_line

    def test_full_format_trigger_details(self):
        """Test trigger detail formatting"""
        formatter = SQLFullFormatter()
        trigger = self.create_sample_trigger()

        details = formatter._format_trigger_details(trigger)

        # Check event
        event_line = next((line for line in details if "Event" in line), None)
        assert event_line is not None
        assert "AFTER INSERT" in event_line

        # Check target table
        table_line = next((line for line in details if "Target Table" in line), None)
        assert table_line is not None
        assert "users" in table_line

    def test_full_format_index_details(self):
        """Test index detail formatting"""
        formatter = SQLFullFormatter()
        index = self.create_sample_index()

        details = formatter._format_index_details(index)

        # Check table
        table_line = next((line for line in details if "Table" in line), None)
        assert table_line is not None
        assert "users" in table_line

        # Check columns
        columns_line = next((line for line in details if "Columns" in line), None)
        assert columns_line is not None
        assert "email" in columns_line

        # Check type
        type_line = next((line for line in details if "Type" in line), None)
        assert type_line is not None
        assert "Standard index" in type_line

    def test_full_format_complete_output(self):
        """Test complete full format output"""
        formatter = SQLFullFormatter()

        elements = [
            self.create_sample_table(),
            self.create_sample_view(),
            self.create_sample_procedure(),
            self.create_sample_function(),
            self.create_sample_trigger(),
            self.create_sample_index(),
        ]

        result = formatter.format_elements(elements, "sample_database.sql")

        # Check file header
        assert "sample_database.sql" in result

        # Check overview section
        assert "Database Schema Overview" in result

        # Check detailed sections
        assert "## Tables" in result
        assert "## Views" in result
        assert "## Procedures" in result
        assert "## Functions" in result
        assert "## Triggers" in result
        assert "## Indexes" in result

        # Check element names appear
        assert "users" in result
        assert "active_users" in result
        assert "get_user_info" in result
        assert "calculate_age" in result
        assert "user_audit" in result
        assert "idx_user_email" in result


class TestSQLCompactFormatter:
    """Test SQL compact format output"""

    def test_compact_format_table_details(self):
        """Test compact table detail formatting"""
        formatter = SQLCompactFormatter()

        columns = [
            SQLColumn(
                name="id", data_type="INTEGER", nullable=False, is_primary_key=True
            ),
            SQLColumn(
                name="name",
                data_type="VARCHAR(100)",
                nullable=False,
                is_primary_key=False,
            ),
        ]

        table = SQLTable(
            name="users",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE users...",
            language="sql",
            columns=columns,
            constraints=[],
        )

        details = formatter._format_compact_details(table)
        assert "2 cols" in details
        assert "PK: id" in details

    def test_compact_format_view_details(self):
        """Test compact view detail formatting"""
        formatter = SQLCompactFormatter()

        view = SQLView(
            name="active_users",
            start_line=7,
            end_line=9,
            raw_text="CREATE VIEW active_users...",
            language="sql",
            source_tables=["users", "profiles"],
            dependencies=["users", "profiles"],
        )

        details = formatter._format_compact_details(view)
        assert "from users, profiles" in details

    def test_compact_format_procedure_details(self):
        """Test compact procedure detail formatting"""
        formatter = SQLCompactFormatter()

        parameters = [
            SQLParameter(name="user_id", data_type="INT", direction="IN"),
            SQLParameter(name="result", data_type="VARCHAR", direction="OUT"),
        ]

        procedure = SQLProcedure(
            name="get_user",
            start_line=11,
            end_line=15,
            raw_text="CREATE PROCEDURE get_user...",
            language="sql",
            parameters=parameters,
            dependencies=[],
        )

        details = formatter._format_compact_details(procedure)
        assert "2 params" in details

    def test_compact_format_function_details(self):
        """Test compact function detail formatting"""
        formatter = SQLCompactFormatter()

        parameters = [
            SQLParameter(name="birth_date", data_type="DATE", direction="IN"),
        ]

        function = SQLFunction(
            name="calculate_age",
            start_line=17,
            end_line=21,
            raw_text="CREATE FUNCTION calculate_age...",
            language="sql",
            parameters=parameters,
            return_type="INT",
            dependencies=[],
        )

        details = formatter._format_compact_details(function)
        assert "1 params" in details
        assert "→ INT" in details

    def test_compact_format_trigger_details(self):
        """Test compact trigger detail formatting"""
        formatter = SQLCompactFormatter()

        trigger = SQLTrigger(
            name="user_audit",
            start_line=23,
            end_line=29,
            raw_text="CREATE TRIGGER user_audit...",
            language="sql",
            table_name="users",
            trigger_timing="AFTER",
            trigger_event="INSERT",
            dependencies=["users"],
        )

        details = formatter._format_compact_details(trigger)
        assert "AFTER INSERT" in details
        assert "on users" in details

    def test_compact_format_index_details(self):
        """Test compact index detail formatting"""
        formatter = SQLCompactFormatter()

        index = SQLIndex(
            name="idx_user_email",
            start_line=31,
            end_line=31,
            raw_text="CREATE UNIQUE INDEX idx_user_email...",
            language="sql",
            table_name="users",
            indexed_columns=["email", "name"],
            is_unique=True,
            dependencies=["users"],
        )

        details = formatter._format_compact_details(index)
        assert "on users" in details
        assert "(email, name)" in details
        assert "UNIQUE" in details

    def test_compact_format_complete_output(self):
        """Test complete compact format output"""
        formatter = SQLCompactFormatter()

        table = SQLTable(
            name="users",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE users...",
            language="sql",
            columns=[
                SQLColumn(
                    name="id", data_type="INTEGER", nullable=False, is_primary_key=True
                ),
            ],
            constraints=[],
        )

        view = SQLView(
            name="active_users",
            start_line=7,
            end_line=9,
            raw_text="CREATE VIEW active_users...",
            language="sql",
            source_tables=["users"],
            dependencies=["users"],
        )

        elements = [table, view]
        result = formatter.format_elements(elements, "test.sql")

        # Check header
        assert "test.sql" in result
        assert "| Element | Type | Lines | Details |" in result

        # Check table row
        assert "| users | table | 1-5 | 1 cols, PK: id |" in result

        # Check view row
        assert "| active_users | view | 7-9 | from users |" in result


class TestSQLCSVFormatter:
    """Test SQL CSV format output"""

    def test_csv_format_header(self):
        """Test CSV header format"""
        formatter = SQLCSVFormatter()

        table = SQLTable(
            name="users",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE users...",
            language="sql",
            columns=[],
            constraints=[],
        )

        result = formatter.format_elements([table], "test.sql")
        lines = result.strip().split("\n")

        # Check header
        assert lines[0] == "Element,Type,Lines,Columns_Parameters,Dependencies"

    def test_csv_format_table_row(self):
        """Test CSV table row format"""
        formatter = SQLCSVFormatter()

        columns = [
            SQLColumn(
                name="id", data_type="INTEGER", nullable=False, is_primary_key=True
            ),
            SQLColumn(
                name="name",
                data_type="VARCHAR(100)",
                nullable=False,
                is_primary_key=False,
            ),
        ]

        table = SQLTable(
            name="users",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE users...",
            language="sql",
            columns=columns,
            constraints=[],
        )

        result = formatter.format_elements([table], "test.sql")
        lines = result.strip().split("\n")

        # Check data row
        assert lines[1] == "users,table,1-5,2 columns,"

    def test_csv_format_with_dependencies(self):
        """Test CSV format with dependencies"""
        formatter = SQLCSVFormatter()

        view = SQLView(
            name="active_users",
            start_line=7,
            end_line=9,
            raw_text="CREATE VIEW active_users...",
            language="sql",
            source_tables=["users", "profiles"],
            dependencies=["users", "profiles"],
        )

        result = formatter.format_elements([view], "test.sql")
        lines = result.strip().split("\n")

        # Check data row with dependencies
        assert lines[1] == "active_users,view,7-9,,users;profiles"

    def test_csv_format_index_with_columns(self):
        """Test CSV format for index with columns"""
        formatter = SQLCSVFormatter()

        index = SQLIndex(
            name="idx_user_email",
            start_line=11,
            end_line=11,
            raw_text="CREATE INDEX idx_user_email...",
            language="sql",
            table_name="users",
            indexed_columns=["email", "name"],
            is_unique=False,
            dependencies=["users"],
        )

        result = formatter.format_elements([index], "test.sql")
        lines = result.strip().split("\n")

        # Check data row with indexed columns
        assert lines[1] == "idx_user_email,index,11-11,email;name,users"


class TestSQLFormatterEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_elements_list(self):
        """Test formatting with empty elements list"""
        formatters = [SQLFullFormatter(), SQLCompactFormatter(), SQLCSVFormatter()]

        for formatter in formatters:
            result = formatter.format_elements([], "empty.sql")
            if isinstance(formatter, SQLCSVFormatter):
                # CSV formatter should still have header even with empty elements
                # but doesn't include filename for empty files
                assert "Element,Type,Lines,Columns_Parameters,Dependencies" in result
                lines = result.strip().split("\n")
                assert len(lines) >= 1
            else:
                assert "empty.sql" in result
                assert "No SQL elements found" in result

    def test_elements_without_metadata(self):
        """Test formatting elements with minimal metadata"""
        formatter = SQLFullFormatter()

        # Table without columns or constraints
        table = SQLTable(
            name="simple_table",
            start_line=1,
            end_line=3,
            raw_text="CREATE TABLE simple_table (id INT);",
            language="sql",
            columns=[],
            constraints=[],
        )

        result = formatter.format_elements([table], "simple.sql")
        assert "simple_table" in result
        assert "Tables" in result

    def test_elements_with_none_values(self):
        """Test formatting elements with None values"""
        formatter = SQLCompactFormatter()

        # Function without parameters or return type
        function = SQLFunction(
            name="simple_function",
            start_line=5,
            end_line=7,
            raw_text="CREATE FUNCTION simple_function() ...",
            language="sql",
            parameters=[],
            return_type=None,
            dependencies=[],
        )

        result = formatter.format_elements([function], "simple.sql")
        assert "simple_function" in result
        assert "function" in result.lower()

    def test_sorting_by_line_number(self):
        """Test that elements are sorted by line number"""
        formatter = SQLCompactFormatter()

        # Create elements in reverse line order
        elements = [
            SQLTable(
                name="table_z",
                start_line=20,
                end_line=25,
                raw_text="CREATE TABLE table_z...",
                language="sql",
                columns=[],
                constraints=[],
            ),
            SQLTable(
                name="table_a",
                start_line=1,
                end_line=5,
                raw_text="CREATE TABLE table_a...",
                language="sql",
                columns=[],
                constraints=[],
            ),
            SQLTable(
                name="table_m",
                start_line=10,
                end_line=15,
                raw_text="CREATE TABLE table_m...",
                language="sql",
                columns=[],
                constraints=[],
            ),
        ]

        result = formatter.format_elements(elements, "test.sql")
        lines = result.strip().split("\n")

        # Find data rows (skip header)
        data_lines = [line for line in lines if line.startswith("| table_")]

        # Check order
        assert "table_a" in data_lines[0]
        assert "table_m" in data_lines[1]
        assert "table_z" in data_lines[2]


class TestSQLFormatterIntegration:
    """Integration tests with sample database file"""

    @pytest.fixture
    def sample_sql_file(self, tmp_path):
        """Create a sample SQL file for testing"""
        sql_content = """
-- Sample database schema
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIEW active_users AS
SELECT * FROM users WHERE active = 1;

CREATE PROCEDURE get_user_by_id(IN user_id INT)
BEGIN
    SELECT * FROM users WHERE id = user_id;
END;

CREATE FUNCTION calculate_age(birth_date DATE)
RETURNS INT
BEGIN
    RETURN YEAR(CURDATE()) - YEAR(birth_date);
END;

CREATE TRIGGER user_audit
AFTER INSERT ON users
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (table_name, action, timestamp)
    VALUES ('users', 'INSERT', NOW());
END;

CREATE INDEX idx_user_email ON users(email);
"""
        sql_file = tmp_path / "sample.sql"
        sql_file.write_text(sql_content)
        return str(sql_file)

    def test_format_with_real_sql_file(self, sample_sql_file):
        """Test formatters with a real SQL file structure"""
        # This test would require actual SQL parsing integration
        # For now, we'll test the formatter structure

        formatters = [SQLFullFormatter(), SQLCompactFormatter(), SQLCSVFormatter()]

        for formatter in formatters:
            # Test with empty elements (simulating no parsed elements)
            result = formatter.format_elements([], sample_sql_file)

            # Verify formatter doesn't crash with empty input
            assert isinstance(result, str)
            assert len(result) > 0

            # For CSV formatter, check that header is present even with empty elements
            if isinstance(formatter, SQLCSVFormatter):
                assert "Element,Type,Lines,Columns_Parameters,Dependencies" in result
            else:
                assert "sample.sql" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
