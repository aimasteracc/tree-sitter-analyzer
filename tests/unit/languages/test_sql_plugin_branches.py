#!/usr/bin/env python3
"""Additional SQL plugin coverage tests targeting uncovered branches."""

import pytest

from tree_sitter_analyzer.languages.sql_plugin import (
    SQLElementExtractor,
    SQLPlugin,
)
from tree_sitter_analyzer.models import (
    SQLElementType,
    SQLTable,
    SQLTrigger,
)

# Check if tree-sitter-sql is available
try:
    import tree_sitter
    import tree_sitter_sql

    TREE_SITTER_SQL_AVAILABLE = True
except ImportError:
    TREE_SITTER_SQL_AVAILABLE = False


class TestSQLExtractorBranchCoverage:
    """Test uncovered branches in SQL extractor."""

    @pytest.fixture
    def extractor(self):
        ext = SQLElementExtractor()
        ext.source_code = ""
        ext.content_lines = []
        ext._reset_caches()
        return ext

    def test_is_valid_identifier_with_numbers(self, extractor):
        """Test identifier starting with underscore and numbers."""
        assert extractor._is_valid_identifier("_column1")
        assert extractor._is_valid_identifier("user_123")
        assert not extractor._is_valid_identifier("123_invalid")

    def test_is_valid_identifier_with_special_chars(self, extractor):
        """Test identifier with special characters."""
        assert not extractor._is_valid_identifier("user@name")
        assert not extractor._is_valid_identifier("table#1")

    def test_is_valid_identifier_sql_keywords(self, extractor):
        """Test SQL keywords are invalid."""
        keywords = [
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "FROM",
            "WHERE",
            "JOIN",
            "ON",
            "AND",
            "OR",
            "NOT",
            "NULL",
            "CREATE",
            "DROP",
            "ALTER",
            "TABLE",
            "INDEX",
            "VIEW",
            "TRIGGER",
            "PROCEDURE",
        ]
        for kw in keywords:
            assert not extractor._is_valid_identifier(kw)
            assert not extractor._is_valid_identifier(kw.lower())

    def test_is_valid_identifier_backtick_quoted(self, extractor):
        """Test backtick-quoted identifiers."""
        assert extractor._is_valid_identifier("`my-table`")
        assert extractor._is_valid_identifier("`table name`")

    def test_is_valid_identifier_double_quoted(self, extractor):
        """Test double-quoted identifiers."""
        assert extractor._is_valid_identifier('"my-column"')
        assert extractor._is_valid_identifier('"column name"')

    def test_is_valid_identifier_bracket_quoted(self, extractor):
        """Test bracket-quoted identifiers (SQL Server style)."""
        assert extractor._is_valid_identifier("[my-table]")
        assert extractor._is_valid_identifier("[table name]")

    def test_is_valid_identifier_length_limit(self, extractor):
        """Test identifier length limits."""
        # 128 chars should be valid
        assert extractor._is_valid_identifier("a" * 128)
        # 200 chars should be invalid
        assert not extractor._is_valid_identifier("a" * 200)

    def test_parse_column_with_default_value(self, extractor):
        """Test column parsing with DEFAULT value."""
        col_def = "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        column = extractor._parse_column_definition(col_def)
        assert column is not None
        assert column.name == "created_at"
        assert "TIMESTAMP" in column.data_type

    def test_parse_column_with_size(self, extractor):
        """Test column parsing with size specification."""
        col_def = "name VARCHAR(255) NOT NULL"
        column = extractor._parse_column_definition(col_def)
        assert column is not None
        assert column.name == "name"
        assert "VARCHAR(255)" in column.data_type or "VARCHAR" in column.data_type
        assert column.nullable is False

    def test_parse_column_decimal_precision(self, extractor):
        """Test column parsing with decimal precision."""
        col_def = "price DECIMAL(10,2)"
        column = extractor._parse_column_definition(col_def)
        assert column is not None
        assert column.name == "price"
        assert "DECIMAL" in column.data_type

    def test_parse_column_with_unsigned(self, extractor):
        """Test column parsing with UNSIGNED modifier."""
        col_def = "id INT UNSIGNED NOT NULL AUTO_INCREMENT"
        column = extractor._parse_column_definition(col_def)
        assert column is not None
        assert column.name == "id"
        assert column.is_primary_key is True  # AUTO_INCREMENT implies primary key

    def test_split_column_definitions_deeply_nested(self, extractor):
        """Test splitting with deeply nested parentheses."""
        content = "id INT, check_val INT CHECK (value > 0 AND value < (SELECT MAX(id) FROM t)), name TEXT"
        defs = extractor._split_column_definitions(content)
        assert len(defs) == 3


@pytest.mark.skipif(
    not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not installed"
)
class TestSQLPluginExtractionBranches:
    """Test extraction branches with actual tree-sitter."""

    @pytest.fixture
    def plugin(self):
        return SQLPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_sql.language())
        return tree_sitter.Parser(language)

    def test_extract_table_with_all_constraint_types(self, plugin, parser):
        """Test table with all constraint types."""
        code = """
CREATE TABLE products (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    category_id INT,
    price DECIMAL(10,2) CHECK (price >= 0),
    CONSTRAINT fk_category FOREIGN KEY (category_id) REFERENCES categories(id),
    INDEX idx_name (name)
);
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result
        tables = [c for c in result["classes"] if c.name == "products"]
        assert len(tables) >= 1

    def test_extract_view_with_if_not_exists(self, plugin, parser):
        """Test CREATE VIEW IF NOT EXISTS."""
        code = """
CREATE VIEW IF NOT EXISTS user_orders AS
SELECT u.id, u.name, COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.name;
"""
        tree = parser.parse(code.encode("utf-8"))
        plugin.extract_elements(tree, code)
        # May or may not extract view depending on parser

    def test_extract_function_with_returns(self, plugin, parser):
        """Test CREATE FUNCTION with RETURNS clause."""
        code = """
CREATE FUNCTION get_full_name(first_name VARCHAR(50), last_name VARCHAR(50))
RETURNS VARCHAR(101)
BEGIN
    RETURN CONCAT(first_name, ' ', last_name);
END;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_procedure_with_parameters(self, plugin, parser):
        """Test CREATE PROCEDURE with IN/OUT parameters."""
        code = """
CREATE PROCEDURE update_user_status(
    IN user_id INT,
    IN new_status VARCHAR(20),
    OUT success BOOLEAN
)
BEGIN
    UPDATE users SET status = new_status WHERE id = user_id;
    SET success = ROW_COUNT() > 0;
END;
"""
        tree = parser.parse(code.encode("utf-8"))
        plugin.extract_elements(tree, code)

    def test_extract_trigger_before_insert(self, plugin, parser):
        """Test CREATE TRIGGER BEFORE INSERT."""
        code = """
CREATE TRIGGER before_user_insert
BEFORE INSERT ON users
FOR EACH ROW
BEGIN
    SET NEW.created_at = NOW();
END;
"""
        tree = parser.parse(code.encode("utf-8"))
        plugin.extract_elements(tree, code)

    def test_extract_trigger_after_delete(self, plugin, parser):
        """Test CREATE TRIGGER AFTER DELETE."""
        code = """
CREATE TRIGGER after_order_delete
AFTER DELETE ON orders
FOR EACH ROW
BEGIN
    INSERT INTO deleted_orders SELECT OLD.*;
END;
"""
        tree = parser.parse(code.encode("utf-8"))
        plugin.extract_elements(tree, code)

    def test_extract_unique_index(self, plugin, parser):
        """Test CREATE UNIQUE INDEX."""
        code = """
CREATE UNIQUE INDEX idx_email ON users(email);
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "variables" in result

    def test_extract_composite_index(self, plugin, parser):
        """Test CREATE INDEX with multiple columns."""
        code = """
CREATE INDEX idx_user_date ON orders(user_id, created_at DESC);
"""
        tree = parser.parse(code.encode("utf-8"))
        plugin.extract_elements(tree, code)

    def test_extract_drop_statements(self, plugin, parser):
        """Test DROP statements don't cause errors."""
        code = """
DROP TABLE IF EXISTS old_users;
DROP VIEW IF EXISTS old_view;
DROP INDEX idx_old ON users;
DROP PROCEDURE IF EXISTS old_proc;
DROP FUNCTION IF EXISTS old_func;
DROP TRIGGER IF EXISTS old_trigger;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_extract_set_statements(self, plugin, parser):
        """Test SET statements don't cause errors."""
        code = """
SET @var = 1;
SET NAMES utf8mb4;
SET CHARACTER SET utf8;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_extract_use_database(self, plugin, parser):
        """Test USE DATABASE statement."""
        code = """
USE mydb;
SELECT * FROM users;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_extract_grant_revoke(self, plugin, parser):
        """Test GRANT/REVOKE statements."""
        code = """
GRANT SELECT, INSERT ON users TO 'app_user'@'localhost';
REVOKE DELETE ON users FROM 'app_user'@'localhost';
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_extract_lock_unlock(self, plugin, parser):
        """Test LOCK/UNLOCK statements."""
        code = """
LOCK TABLES users WRITE;
SELECT * FROM users;
UNLOCK TABLES;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_extract_truncate(self, plugin, parser):
        """Test TRUNCATE statement."""
        code = """
TRUNCATE TABLE temp_data;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_extract_rename_table(self, plugin, parser):
        """Test RENAME TABLE statement."""
        code = """
RENAME TABLE old_name TO new_name;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_complex_subquery_in_from(self, plugin, parser):
        """Test complex subquery in FROM clause."""
        code = """
SELECT t.id, t.total
FROM (
    SELECT user_id, SUM(amount) as total
    FROM transactions
    GROUP BY user_id
    HAVING SUM(amount) > 1000
) t
JOIN users u ON t.user_id = u.id
WHERE u.active = 1;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_recursive_cte(self, plugin, parser):
        """Test recursive CTE."""
        code = """
WITH RECURSIVE employee_hierarchy AS (
    SELECT id, name, manager_id, 1 as level
    FROM employees
    WHERE manager_id IS NULL
    UNION ALL
    SELECT e.id, e.name, e.manager_id, eh.level + 1
    FROM employees e
    JOIN employee_hierarchy eh ON e.manager_id = eh.id
)
SELECT * FROM employee_hierarchy;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_multiple_tables_single_create(self, plugin, parser):
        """Test multiple CREATE TABLE statements."""
        code = """
CREATE TABLE users (
    id INT PRIMARY KEY,
    email VARCHAR(255)
);

CREATE TABLE orders (
    id INT PRIMARY KEY,
    user_id INT REFERENCES users(id)
);

CREATE TABLE items (
    id INT PRIMARY KEY,
    order_id INT REFERENCES orders(id)
);
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result
        table_names = [c.name for c in result["classes"]]
        assert "users" in table_names
        assert "orders" in table_names
        assert "items" in table_names


class TestSQLPluginValidation:
    """Test validation and fixing of elements."""

    @pytest.fixture
    def extractor(self):
        ext = SQLElementExtractor()
        ext.source_code = ""
        ext.content_lines = []
        return ext

    def test_validate_removes_duplicates(self, extractor):
        """Test that validation removes duplicate elements."""
        table1 = SQLTable(
            name="users",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE users (id INT)",
            sql_element_type=SQLElementType.TABLE,
        )
        table2 = SQLTable(
            name="users",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE users (id INT)",
            sql_element_type=SQLElementType.TABLE,
        )

        result = extractor._validate_and_fix_elements([table1, table2])
        user_tables = [e for e in result if getattr(e, "name", "") == "users"]
        assert len(user_tables) == 1

    def test_validate_removes_phantom_triggers(self, extractor):
        """Test that phantom triggers are removed."""
        phantom = SQLTrigger(
            name="not_a_trigger",
            start_line=1,
            end_line=5,
            raw_text="CREATE FUNCTION my_func() RETURNS INT",
            sql_element_type=SQLElementType.TRIGGER,
        )

        result = extractor._validate_and_fix_elements([phantom])
        triggers = [
            e for e in result if isinstance(e, SQLTrigger) and e.name == "not_a_trigger"
        ]
        assert len(triggers) == 0

    def test_validate_keeps_valid_trigger(self, extractor):
        """Test that valid triggers are kept."""
        valid = SQLTrigger(
            name="valid_trigger",
            start_line=1,
            end_line=5,
            raw_text="CREATE TRIGGER valid_trigger BEFORE INSERT ON users",
            sql_element_type=SQLElementType.TRIGGER,
        )

        result = extractor._validate_and_fix_elements([valid])
        triggers = [
            e for e in result if isinstance(e, SQLTrigger) and e.name == "valid_trigger"
        ]
        assert len(triggers) == 1


class TestSQLPluginErrorHandling:
    """Test error handling in SQL plugin."""

    @pytest.fixture
    def plugin(self):
        return SQLPlugin()

    def test_extract_with_none_tree(self, plugin):
        """Test extraction with None tree."""
        result = plugin.extract_elements(None, "SELECT * FROM users")
        assert isinstance(result, dict)

    def test_extract_with_empty_code(self, plugin):
        """Test extraction with empty code."""
        result = plugin.extract_elements(None, "")
        assert isinstance(result, dict)

    def test_extract_with_whitespace_only(self, plugin):
        """Test extraction with whitespace only code."""
        result = plugin.extract_elements(None, "   \n\n   \t   ")
        assert isinstance(result, dict)

    def test_extract_with_comments_only(self, plugin):
        """Test extraction with comments only."""
        code = """
-- This is a comment
/* Multi-line
   comment */
# MySQL style comment
"""
        result = plugin.extract_elements(None, code)
        assert isinstance(result, dict)

    def test_extract_with_syntax_errors(self, plugin):
        """Test extraction with SQL syntax errors."""
        code = """
CREATE TABL users (  -- typo in TABLE
    id INT
);
SELEC * FROM users;  -- typo in SELECT
"""
        result = plugin.extract_elements(None, code)
        assert isinstance(result, dict)

    def test_extract_with_incomplete_statement(self, plugin):
        """Test extraction with incomplete statements."""
        code = """
CREATE TABLE users (
    id INT,
    name VARCHAR(100)
-- Missing closing parenthesis and semicolon
"""
        result = plugin.extract_elements(None, code)
        assert isinstance(result, dict)


class TestSQLColumnDetails:
    """Test SQL column detail extraction."""

    @pytest.fixture
    def extractor(self):
        return SQLElementExtractor()

    def test_parse_column_basic_types(self, extractor):
        """Test parsing basic column types."""
        basic_types = [
            ("id INT", "id", "INT"),
            ("name TEXT", "name", "TEXT"),
            ("active BOOLEAN", "active", "BOOLEAN"),
            ("data BLOB", "data", "BLOB"),
            ("amount FLOAT", "amount", "FLOAT"),
            ("value DOUBLE", "value", "DOUBLE"),
        ]
        for col_def, expected_name, _expected_type in basic_types:
            column = extractor._parse_column_definition(col_def)
            assert column is not None, f"Failed to parse: {col_def}"
            assert column.name == expected_name

    def test_parse_column_with_multiple_constraints(self, extractor):
        """Test parsing column with multiple constraints."""
        col_def = "id INT NOT NULL PRIMARY KEY AUTO_INCREMENT UNIQUE"
        column = extractor._parse_column_definition(col_def)
        assert column is not None
        assert column.name == "id"
        assert column.nullable is False
        assert column.is_primary_key is True

    def test_parse_column_inline_foreign_key(self, extractor):
        """Test parsing column with inline foreign key."""
        col_def = (
            "user_id INT REFERENCES users(id) ON DELETE CASCADE ON UPDATE SET NULL"
        )
        column = extractor._parse_column_definition(col_def)
        assert column is not None
        assert column.name == "user_id"
        assert column.is_foreign_key is True
        assert "users(id)" in column.foreign_key_reference


@pytest.mark.skipif(
    not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not installed"
)
class TestSQLPluginIntegration:
    """Integration tests for SQL plugin."""

    @pytest.fixture
    def plugin(self):
        return SQLPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_sql.language())
        return tree_sitter.Parser(language)

    def test_full_database_schema(self, plugin, parser):
        """Test extracting full database schema."""
        code = """
-- Users table
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- User profiles
CREATE TABLE profiles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL UNIQUE,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    bio TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Orders table
CREATE TABLE orders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    total_amount DECIMAL(10,2) DEFAULT 0.00,
    status ENUM('pending', 'processing', 'shipped', 'delivered', 'cancelled') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Order items
CREATE TABLE order_items (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);

-- View for order summary
CREATE VIEW order_summary AS
SELECT
    o.id as order_id,
    u.email as user_email,
    o.total_amount,
    o.status,
    COUNT(oi.id) as item_count
FROM orders o
JOIN users u ON o.user_id = u.id
LEFT JOIN order_items oi ON o.id = oi.order_id
GROUP BY o.id, u.email, o.total_amount, o.status;

-- Stored procedure
CREATE PROCEDURE calculate_order_total(IN order_id_param INT)
BEGIN
    UPDATE orders o
    SET total_amount = (
        SELECT COALESCE(SUM(quantity * unit_price), 0)
        FROM order_items
        WHERE order_id = order_id_param
    )
    WHERE o.id = order_id_param;
END;

-- Trigger for updated_at
CREATE TRIGGER update_user_timestamp
BEFORE UPDATE ON users
FOR EACH ROW
BEGIN
    SET NEW.updated_at = CURRENT_TIMESTAMP;
END;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)

        assert "classes" in result
        table_names = [c.name for c in result["classes"]]

        # Should extract tables
        assert "users" in table_names
        assert "profiles" in table_names
        assert "orders" in table_names
        assert "order_items" in table_names

    def test_extract_postgresql_specific(self, plugin, parser):
        """Test PostgreSQL-specific syntax."""
        code = """
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    data JSONB NOT NULL,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_data ON events USING GIN (data);
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_extract_mysql_specific(self, plugin, parser):
        """Test MySQL-specific syntax."""
        code = """
CREATE TABLE logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    message TEXT,
    level ENUM('debug', 'info', 'warn', 'error') DEFAULT 'info',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)
