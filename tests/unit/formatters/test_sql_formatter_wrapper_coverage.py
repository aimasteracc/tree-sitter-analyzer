"""
Comprehensive tests for SQL Formatter Wrapper to achieve 90%+ coverage.
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

    def test_format_table_compact(self, formatter):
        """Test format_table with compact type."""
        data = {
            "file_path": "test.sql",
            "elements": [
                SQLTable(
                    name="orders",
                    start_line=1,
                    end_line=3,
                    raw_text="CREATE TABLE orders (id INT);",
                    language="sql",
                )
            ],
        }
        result = formatter.format_table(data, "compact")
        assert isinstance(result, str)

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


class TestFormatSummary:
    """Test format_summary method."""

    def test_format_summary(self, formatter):
        """Test format_summary uses compact formatter."""
        data = {
            "file_path": "test.sql",
            "elements": [
                SQLTable(
                    name="summary_table",
                    start_line=1,
                    end_line=5,
                    raw_text="CREATE TABLE summary_table (id INT);",
                    language="sql",
                )
            ],
        }
        result = formatter.format_summary(data)
        assert isinstance(result, str)


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


class TestExtractTableColumns:
    """Test _extract_table_columns method."""

    def test_extract_simple_columns(self, formatter):
        """Test extraction of simple columns."""
        raw_text = """CREATE TABLE users (
            id INT,
            name VARCHAR(100),
            email VARCHAR(255)
        );"""
        result = formatter._extract_table_columns(raw_text, "users")
        assert "columns" in result
        assert "constraints" in result

    def test_extract_columns_with_constraints(self, formatter):
        """Test extraction with constraints."""
        raw_text = """CREATE TABLE users (
            id INT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(255) UNIQUE,
            FOREIGN KEY (dept_id) REFERENCES departments(id)
        );"""
        result = formatter._extract_table_columns(raw_text, "users")
        assert "PRIMARY KEY" in result["constraints"]
        assert "NOT NULL" in result["constraints"]
        assert "UNIQUE" in result["constraints"]
        assert "FOREIGN KEY" in result["constraints"]

    def test_extract_columns_skip_keywords(self, formatter):
        """Test that keywords are skipped."""
        raw_text = """CREATE TABLE test (
            id INT,
            PRIMARY KEY (id),
            CONSTRAINT fk_test FOREIGN KEY (ref_id) REFERENCES other(id)
        );"""
        result = formatter._extract_table_columns(raw_text, "test")
        # Should not include PRIMARY, FOREIGN, KEY, CONSTRAINT as column names
        for col in result["columns"]:
            assert col.upper() not in ["PRIMARY", "FOREIGN", "KEY", "CONSTRAINT"]


class TestExtractViewInfo:
    """Test _extract_view_info method."""

    def test_extract_simple_view(self, formatter):
        """Test extraction of simple view info."""
        raw_text = "CREATE VIEW user_view AS SELECT * FROM users;"
        result = formatter._extract_view_info(raw_text, "user_view")
        assert "users" in result["source_tables"]

    def test_extract_view_with_join(self, formatter):
        """Test extraction of view with JOIN."""
        raw_text = """CREATE VIEW order_summary AS
            SELECT * FROM orders
            JOIN users ON orders.user_id = users.id
            JOIN products ON orders.product_id = products.id;"""
        result = formatter._extract_view_info(raw_text, "order_summary")
        assert "orders" in result["source_tables"]
        assert "users" in result["source_tables"]
        assert "products" in result["source_tables"]


class TestExtractProcedureInfo:
    """Test _extract_procedure_info method."""

    def test_extract_simple_procedure(self, formatter):
        """Test extraction of simple procedure info."""
        raw_text = """CREATE PROCEDURE update_user(IN user_id INT, OUT result VARCHAR(50))
        BEGIN
            UPDATE users SET updated_at = NOW() WHERE id = user_id;
        END;"""
        result = formatter._extract_procedure_info(raw_text, "update_user")
        assert "parameters" in result
        assert "dependencies" in result
        assert len(result["parameters"]) > 0

    def test_extract_procedure_with_dependencies(self, formatter):
        """Test extraction of procedure with table dependencies."""
        raw_text = """CREATE PROCEDURE process_order(IN order_id INT)
        BEGIN
            SELECT * FROM orders WHERE id = order_id;
            UPDATE inventory SET quantity = quantity - 1;
            INSERT INTO audit_log (action) VALUES ('processed');
        END;"""
        result = formatter._extract_procedure_info(raw_text, "process_order")
        assert "orders" in result["dependencies"]
        assert "inventory" in result["dependencies"]
        assert "audit_log" in result["dependencies"]


class TestExtractFunctionInfo:
    """Test _extract_function_info method."""

    def test_extract_simple_function(self, formatter):
        """Test extraction of simple function info."""
        raw_text = """CREATE FUNCTION calculate_tax(price DECIMAL(10,2))
        RETURNS DECIMAL(10,2)
        READS SQL DATA
        BEGIN
            RETURN price * 0.1;
        END;"""
        result = formatter._extract_function_info(raw_text, "calculate_tax")
        assert result["return_type"] == "DECIMAL(10,2)"
        assert "parameters" in result

    def test_extract_function_with_dependencies(self, formatter):
        """Test extraction of function with table dependencies."""
        raw_text = """CREATE FUNCTION get_user_count()
        RETURNS INT
        BEGIN
            DECLARE cnt INT;
            SELECT COUNT(*) INTO cnt FROM users;
            RETURN cnt;
        END;"""
        result = formatter._extract_function_info(raw_text, "get_user_count")
        assert "users" in result["dependencies"]


class TestExtractTriggerInfo:
    """Test _extract_trigger_info method."""

    def test_extract_before_update_trigger(self, formatter):
        """Test extraction of BEFORE UPDATE trigger."""
        raw_text = """CREATE TRIGGER audit_update
        BEFORE UPDATE ON users
        FOR EACH ROW
        BEGIN
            INSERT INTO audit_log (action) VALUES ('update');
        END;"""
        result = formatter._extract_trigger_info(raw_text, "audit_update")
        assert result["timing"] == "BEFORE"
        assert result["event"] == "UPDATE"
        assert result["table_name"] == "users"

    def test_extract_after_insert_trigger(self, formatter):
        """Test extraction of AFTER INSERT trigger."""
        raw_text = """CREATE TRIGGER log_insert
        AFTER INSERT ON orders
        FOR EACH ROW
        BEGIN
            UPDATE statistics SET order_count = order_count + 1;
        END;"""
        result = formatter._extract_trigger_info(raw_text, "log_insert")
        assert result["timing"] == "AFTER"
        assert result["event"] == "INSERT"
        assert result["table_name"] == "orders"

    def test_extract_trigger_with_dependencies(self, formatter):
        """Test extraction of trigger with additional dependencies."""
        raw_text = """CREATE TRIGGER complex_trigger
        AFTER DELETE ON products
        FOR EACH ROW
        BEGIN
            UPDATE inventory SET quantity = 0 WHERE product_id = OLD.id;
            INSERT INTO deleted_products SELECT * FROM products WHERE id = OLD.id;
        END;"""
        result = formatter._extract_trigger_info(raw_text, "complex_trigger")
        assert "products" in result["dependencies"]
        assert "inventory" in result["dependencies"]
        assert "deleted_products" in result["dependencies"]


class TestExtractIndexInfo:
    """Test _extract_index_info method."""

    def test_extract_simple_index(self, formatter):
        """Test extraction of simple index info."""
        raw_text = "CREATE INDEX idx_email ON users (email);"
        result = formatter._extract_index_info(raw_text, "idx_email")
        assert result["table_name"] == "users"
        assert "email" in result["columns"]
        assert result["is_unique"] is False

    def test_extract_unique_index(self, formatter):
        """Test extraction of unique index info."""
        raw_text = "CREATE UNIQUE INDEX idx_unique_email ON users (email);"
        result = formatter._extract_index_info(raw_text, "idx_unique_email")
        assert result["is_unique"] is True

    def test_extract_composite_index(self, formatter):
        """Test extraction of composite index info."""
        raw_text = (
            "CREATE INDEX idx_composite ON orders (user_id, product_id, created_at);"
        )
        result = formatter._extract_index_info(raw_text, "idx_composite")
        assert result["table_name"] == "orders"
        assert len(result["columns"]) == 3
        assert "user_id" in result["columns"]
        assert "product_id" in result["columns"]
        assert "created_at" in result["columns"]
