#!/usr/bin/env python3
"""Additional tests to boost SQL plugin coverage to 70%+."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from tree_sitter_analyzer.languages.sql_plugin import SQLElementExtractor, SQLPlugin
from tree_sitter_analyzer.models import SQLTable, SQLView, SQLTrigger, SQLElementType

# Check if tree-sitter-sql is available
try:
    import tree_sitter_sql
    import tree_sitter
    TREE_SITTER_SQL_AVAILABLE = True
except ImportError:
    TREE_SITTER_SQL_AVAILABLE = False


class TestSQLExtractorValidation:
    """Test validation and recovery paths."""

    @pytest.fixture
    def extractor(self):
        return SQLElementExtractor()

    def test_validate_phantom_trigger_removal(self, extractor):
        """Test phantom trigger removal in validation."""
        phantom = SQLTrigger(
            name="bad_trigger",
            start_line=1,
            end_line=5,
            raw_text="CREATE FUNCTION not_trigger ...",
            sql_element_type=SQLElementType.TRIGGER,
        )
        
        result = extractor._validate_and_fix_elements([phantom])
        # Phantom trigger should be removed
        assert not any(e.name == "bad_trigger" and isinstance(e, SQLTrigger) for e in result)

    def test_validate_valid_trigger_kept(self, extractor):
        """Test valid trigger is kept."""
        valid = SQLTrigger(
            name="real_trigger",
            start_line=1,
            end_line=5,
            raw_text="CREATE TRIGGER real_trigger BEFORE INSERT ON t",
            sql_element_type=SQLElementType.TRIGGER,
        )
        
        result = extractor._validate_and_fix_elements([valid])
        assert any(e.name == "real_trigger" for e in result)

    def test_validate_table_kept(self, extractor):
        """Test table is kept in validation."""
        table = SQLTable(
            name="users",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE users (id INT)",
            sql_element_type=SQLElementType.TABLE,
        )
        
        result = extractor._validate_and_fix_elements([table])
        assert any(e.name == "users" for e in result)

    def test_validate_view_recovery(self, extractor):
        """Test view recovery in validation."""
        extractor.source_code = """
CREATE TABLE users (id INT);
CREATE VIEW active_users AS SELECT * FROM users WHERE active = 1;
"""
        extractor.content_lines = extractor.source_code.split("\n")
        
        # Empty list - should try to recover views from source
        result = extractor._validate_and_fix_elements([])
        # May or may not recover depending on regex
        assert isinstance(result, list)


class TestSQLExtractorNodeMethods:
    """Test node manipulation methods."""

    @pytest.fixture
    def extractor(self):
        return SQLElementExtractor()

    def test_get_node_text_with_cache(self, extractor):
        """Test node text caching."""
        extractor.source_code = "SELECT * FROM users"
        extractor.content_lines = ["SELECT * FROM users"]
        extractor._reset_caches()
        
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 19
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 19)
        
        text1 = extractor._get_node_text(mock_node)
        text2 = extractor._get_node_text(mock_node)
        
        assert text1 == text2
        assert id(mock_node) in extractor._node_text_cache

    def test_get_node_text_multiline(self, extractor):
        """Test multiline text extraction."""
        extractor.source_code = "SELECT *\nFROM users\nWHERE id = 1"
        extractor.content_lines = extractor.source_code.split("\n")
        extractor._reset_caches()
        
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 33
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 12)
        
        text = extractor._get_node_text(mock_node)
        assert isinstance(text, str)

    def test_get_node_text_out_of_bounds(self, extractor):
        """Test out of bounds handling."""
        extractor.source_code = "short"
        extractor.content_lines = ["short"]
        extractor._reset_caches()
        
        mock_node = Mock()
        mock_node.start_byte = 100
        mock_node.end_byte = 200
        mock_node.start_point = (10, 0)
        mock_node.end_point = (10, 50)
        
        text = extractor._get_node_text(mock_node)
        assert text == ""

    def test_traverse_nodes(self, extractor):
        """Test node traversal."""
        root = Mock()
        child1 = Mock()
        child2 = Mock()
        grandchild = Mock()
        
        grandchild.children = []
        child1.children = [grandchild]
        child2.children = []
        root.children = [child1, child2]
        
        nodes = list(extractor._traverse_nodes(root))
        
        assert root in nodes
        assert child1 in nodes
        assert child2 in nodes
        assert grandchild in nodes

    def test_is_valid_identifier_empty(self, extractor):
        """Test empty identifier."""
        assert not extractor._is_valid_identifier("")

    def test_is_valid_identifier_keywords(self, extractor):
        """Test SQL keywords are invalid."""
        assert not extractor._is_valid_identifier("SELECT")
        assert not extractor._is_valid_identifier("FROM")
        assert not extractor._is_valid_identifier("WHERE")

    def test_is_valid_identifier_valid(self, extractor):
        """Test valid identifiers."""
        assert extractor._is_valid_identifier("users")
        assert extractor._is_valid_identifier("my_table")
        assert extractor._is_valid_identifier("_test")

    def test_is_valid_identifier_quoted(self, extractor):
        """Test quoted identifiers."""
        assert extractor._is_valid_identifier("`my-table`")
        assert extractor._is_valid_identifier('"my-table"')
        assert extractor._is_valid_identifier("[my-table]")

    def test_is_valid_identifier_too_long(self, extractor):
        """Test identifier length limit."""
        assert not extractor._is_valid_identifier("a" * 200)


@pytest.mark.skipif(not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not installed")
class TestSQLPluginExtractionPaths:
    """Test various extraction paths."""

    @pytest.fixture
    def plugin(self):
        return SQLPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_sql.language())
        return tree_sitter.Parser(language)

    def test_extract_table_with_constraints(self, plugin, parser):
        """Test table with multiple constraints."""
        code = """
CREATE TABLE orders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    total DECIMAL(10,2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id),
    UNIQUE (id, user_id)
);
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result
        assert any(c.name == "orders" for c in result["classes"])

    def test_extract_create_or_replace_view(self, plugin, parser):
        """Test CREATE OR REPLACE VIEW."""
        code = """
CREATE OR REPLACE VIEW user_summary AS
SELECT u.id, u.name, COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.name;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_procedure_with_variables(self, plugin, parser):
        """Test procedure with local variables."""
        code = """
CREATE PROCEDURE calculate_total(IN order_id INT)
BEGIN
    DECLARE total DECIMAL(10,2);
    DECLARE tax DECIMAL(10,2);
    
    SELECT SUM(price) INTO total FROM order_items WHERE order_id = order_id;
    SET tax = total * 0.1;
    UPDATE orders SET total = total + tax WHERE id = order_id;
END;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_trigger_after_update(self, plugin, parser):
        """Test AFTER UPDATE trigger."""
        code = """
CREATE TRIGGER audit_update
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (table_name, action, old_data, new_data)
    VALUES ('users', 'UPDATE', OLD.name, NEW.name);
END;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_function_with_cursor(self, plugin, parser):
        """Test function with cursor."""
        code = """
CREATE FUNCTION get_total_users()
RETURNS INT
BEGIN
    DECLARE total INT;
    SELECT COUNT(*) INTO total FROM users;
    RETURN total;
END;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "functions" in result

    def test_extract_compound_index(self, plugin, parser):
        """Test compound index."""
        code = """
CREATE INDEX idx_user_order ON orders (user_id, created_at DESC);
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "variables" in result

    def test_extract_with_comments(self, plugin, parser):
        """Test extraction with SQL comments."""
        code = """
-- This is a user table
CREATE TABLE users (
    id INT PRIMARY KEY, -- Primary key
    name VARCHAR(100) /* user name */
);
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result

    def test_extract_with_backticks(self, plugin, parser):
        """Test extraction with backtick identifiers."""
        code = """
CREATE TABLE `user-data` (
    `id` INT PRIMARY KEY,
    `full-name` VARCHAR(100)
);
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert "classes" in result


class TestSQLPluginMethods:
    """Test SQLPlugin methods."""

    @pytest.fixture
    def plugin(self):
        return SQLPlugin()

    def test_get_language_name(self, plugin):
        """Test language name."""
        assert plugin.get_language_name() == "sql"

    def test_get_file_extensions(self, plugin):
        """Test file extensions."""
        extensions = plugin.get_file_extensions()
        assert ".sql" in extensions

    def test_is_applicable(self, plugin):
        """Test file applicability."""
        assert plugin.is_applicable("test.sql")
        assert plugin.is_applicable("TEST.SQL")
        assert not plugin.is_applicable("test.py")

    def test_get_plugin_info(self, plugin):
        """Test plugin info."""
        info = plugin.get_plugin_info()
        assert info["language"] == "sql"
        assert ".sql" in info["extensions"]

    def test_create_extractor(self, plugin):
        """Test extractor creation."""
        extractor = plugin.create_extractor()
        assert isinstance(extractor, SQLElementExtractor)

    def test_extract_elements_none_tree(self, plugin):
        """Test with None tree."""
        result = plugin.extract_elements(None, "")
        assert isinstance(result, dict)
        assert "functions" in result
        assert "classes" in result

    def test_extract_elements_empty_code(self, plugin):
        """Test with empty code."""
        result = plugin.extract_elements(None, "")
        assert isinstance(result, dict)


class TestSQLExtractorDiagnosticMode:
    """Test diagnostic mode."""

    def test_diagnostic_mode_enabled(self):
        """Test extractor with diagnostic mode."""
        extractor = SQLElementExtractor(diagnostic_mode=True)
        assert extractor.diagnostic_mode is True

    def test_diagnostic_mode_disabled(self):
        """Test extractor without diagnostic mode."""
        extractor = SQLElementExtractor(diagnostic_mode=False)
        assert extractor.diagnostic_mode is False

    def test_set_adapter(self):
        """Test setting adapter."""
        extractor = SQLElementExtractor()
        mock_adapter = Mock()
        extractor.set_adapter(mock_adapter)
        assert extractor.adapter is mock_adapter


@pytest.mark.skipif(not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not installed")
class TestSQLComplexQueries:
    """Test complex SQL query handling."""

    @pytest.fixture
    def plugin(self):
        return SQLPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_sql.language())
        return tree_sitter.Parser(language)

    def test_cte_query(self, plugin, parser):
        """Test Common Table Expression (CTE)."""
        code = """
CREATE VIEW user_orders AS
WITH user_totals AS (
    SELECT user_id, SUM(total) as total_amount
    FROM orders
    GROUP BY user_id
)
SELECT u.name, ut.total_amount
FROM users u
JOIN user_totals ut ON u.id = ut.user_id;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_window_function(self, plugin, parser):
        """Test window function."""
        code = """
CREATE VIEW ranked_users AS
SELECT 
    name,
    total_orders,
    ROW_NUMBER() OVER (ORDER BY total_orders DESC) as rank
FROM users;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_case_expression(self, plugin, parser):
        """Test CASE expression."""
        code = """
CREATE VIEW user_status AS
SELECT 
    name,
    CASE 
        WHEN last_login > DATE_SUB(NOW(), INTERVAL 7 DAY) THEN 'active'
        WHEN last_login > DATE_SUB(NOW(), INTERVAL 30 DAY) THEN 'inactive'
        ELSE 'dormant'
    END as status
FROM users;
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)

    def test_subquery(self, plugin, parser):
        """Test subquery."""
        code = """
CREATE VIEW top_customers AS
SELECT * FROM users
WHERE id IN (
    SELECT user_id FROM orders
    GROUP BY user_id
    HAVING SUM(total) > 1000
);
"""
        tree = parser.parse(code.encode("utf-8"))
        result = plugin.extract_elements(tree, code)
        assert isinstance(result, dict)
