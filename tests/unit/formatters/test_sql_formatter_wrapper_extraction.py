"""
Tests for SQL Formatter Wrapper SQL element extraction methods.
"""

import pytest

from tree_sitter_analyzer.formatters.sql_formatter_wrapper import SQLFormatterWrapper


@pytest.fixture
def formatter():
    return SQLFormatterWrapper()


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
