#!/usr/bin/env python3
"""
Comprehensive tests for SQL Plugin.

Tests cover:
- Table extraction with columns and constraints
- View extraction with queries
- Procedure extraction
- Function extraction
- Trigger extraction
- Index extraction
- Schema references
- Platform compatibility
- Edge cases and error handling
- SQL element models and metadata
- Formatter integration
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.sql_plugin import SQLElementExtractor, SQLPlugin
from tree_sitter_analyzer.models import (
    CodeElement,
    SQLColumn,
    SQLConstraint,
    SQLElementType,
    SQLFunction,
    SQLIndex,
    SQLParameter,
    SQLProcedure,
    SQLTable,
    SQLTrigger,
)

# Check if tree-sitter-sql is available
try:
    import tree_sitter_sql  # noqa: F401

    TREE_SITTER_SQL_AVAILABLE = True
except ImportError:
    TREE_SITTER_SQL_AVAILABLE = False


def extract_elements_from_sql(plugin: SQLPlugin, sql_code: str) -> dict:
    """Helper to extract elements using tree-sitter parser."""
    if not TREE_SITTER_SQL_AVAILABLE:
        pytest.skip("tree-sitter-sql not installed")

    import tree_sitter

    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_sql.language()))
    tree = parser.parse(sql_code.encode("utf-8"))
    return plugin.extract_elements(tree, sql_code)


class TestSQLElementExtractorUnit:
    """Unit tests for SQLElementExtractor that don't need tree-sitter-sql."""

    @pytest.fixture
    def extractor(self) -> SQLElementExtractor:
        """Create an extractor instance."""
        return SQLElementExtractor()

    def test_extractor_initialization(self, extractor: SQLElementExtractor) -> None:
        """Test SQLElementExtractor initialization."""
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert extractor.diagnostic_mode is False
        assert extractor.platform_info is None
        assert extractor.adapter is None

    def test_extractor_diagnostic_mode(self) -> None:
        """Test extractor initialization with diagnostic mode."""
        extractor = SQLElementExtractor(diagnostic_mode=True)
        assert extractor.diagnostic_mode is True

    def test_reset_caches(self, extractor: SQLElementExtractor) -> None:
        """Test cache reset functionality."""
        extractor._node_text_cache[123] = "cached_text"
        extractor._processed_nodes.add(456)

        extractor._reset_caches()

        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0

    def test_set_adapter(self, extractor: SQLElementExtractor) -> None:
        """Test setting compatibility adapter."""
        from unittest.mock import Mock

        mock_adapter = Mock()
        extractor.set_adapter(mock_adapter)

        assert extractor.adapter is mock_adapter

    # ==================== Identifier Validation Tests ====================

    def test_is_valid_identifier_simple(self, extractor: SQLElementExtractor) -> None:
        """Test valid identifier validation."""
        assert extractor._is_valid_identifier("users")
        assert extractor._is_valid_identifier("my_table")
        assert extractor._is_valid_identifier("Table123")
        assert extractor._is_valid_identifier("_private")

    def test_is_valid_identifier_invalid(self, extractor: SQLElementExtractor) -> None:
        """Test invalid identifier detection."""
        assert not extractor._is_valid_identifier("")
        assert not extractor._is_valid_identifier("SELECT ")
        assert not extractor._is_valid_identifier("CREATE TABLE")
        assert not extractor._is_valid_identifier("multi\nline")
        assert not extractor._is_valid_identifier("has(paren")
        assert not extractor._is_valid_identifier("a" * 200)  # Too long

    def test_is_valid_identifier_sql_keywords(
        self, extractor: SQLElementExtractor
    ) -> None:
        """Test that SQL keywords are rejected."""
        keywords = [
            "SELECT",
            "FROM",
            "WHERE",
            "INSERT",
            "UPDATE",
            "DELETE",
            "CREATE",
            "TABLE",
            "VIEW",
            "NULL",
            "PRIMARY",
            "KEY",
            "NOT",
            "FOREIGN",
            "REFERENCES",
        ]
        for kw in keywords:
            assert not extractor._is_valid_identifier(kw), (
                f"Keyword {kw} should be invalid"
            )

    def test_is_valid_identifier_quoted(self, extractor: SQLElementExtractor) -> None:
        """Test quoted identifiers."""
        assert extractor._is_valid_identifier("`my-table`")
        assert extractor._is_valid_identifier('"my-table"')
        assert extractor._is_valid_identifier("[my-table]")

    # ==================== Node Text Extraction Tests ====================

    def test_get_node_text_caching(self, extractor: SQLElementExtractor) -> None:
        """Test that node text is cached."""
        extractor.source_code = "CREATE TABLE test (id INT);"
        extractor.content_lines = extractor.source_code.split("\n")
        extractor._reset_caches()

        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 27
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 27)

        text1 = extractor._get_node_text(mock_node)
        text2 = extractor._get_node_text(mock_node)

        assert text1 == text2
        # Cache uses (start_byte, end_byte) tuple as key
        assert (mock_node.start_byte, mock_node.end_byte) in extractor._node_text_cache

    def test_get_node_text_multiline(self, extractor: SQLElementExtractor) -> None:
        """Test multiline node text extraction."""
        extractor.source_code = "line1\nline2\nline3"
        extractor.content_lines = extractor.source_code.split("\n")
        extractor._reset_caches()

        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 17
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 5)

        text = extractor._get_node_text(mock_node)
        assert isinstance(text, str)

    def test_get_node_text_empty_fallback(self, extractor: SQLElementExtractor) -> None:
        """Test node text extraction fallback."""
        extractor.source_code = ""
        extractor.content_lines = []
        extractor._reset_caches()

        mock_node = Mock()
        mock_node.start_byte = 100
        mock_node.end_byte = 200
        mock_node.start_point = (100, 0)
        mock_node.end_point = (100, 50)

        text = extractor._get_node_text(mock_node)
        assert text == ""

    # ==================== Traverse Nodes Tests ====================

    def test_traverse_nodes_simple(self, extractor: SQLElementExtractor) -> None:
        """Test traversal of simple tree."""
        root = Mock()
        child1 = Mock()
        child2 = Mock()
        child1.children = []
        child2.children = []
        root.children = [child1, child2]

        nodes = list(extractor._traverse_nodes(root))

        assert root in nodes
        assert child1 in nodes
        assert child2 in nodes
        assert len(nodes) == 3

    def test_traverse_nodes_nested(self, extractor: SQLElementExtractor) -> None:
        """Test traversal of nested tree."""
        root = Mock()
        child = Mock()
        grandchild = Mock()
        grandchild.children = []
        child.children = [grandchild]
        root.children = [child]

        nodes = list(extractor._traverse_nodes(root))

        assert len(nodes) == 3
        assert root in nodes
        assert child in nodes
        assert grandchild in nodes

    # ==================== Validate and Fix Elements Tests ====================

    def test_validate_removes_phantom_triggers(
        self, extractor: SQLElementExtractor
    ) -> None:
        """Test removal of phantom trigger elements."""
        phantom = SQLTrigger(
            name="fake_trigger",
            start_line=1,
            end_line=5,
            raw_text="CREATE FUNCTION something ...",  # Wrong content
            sql_element_type=SQLElementType.TRIGGER,
        )

        elements = [phantom]
        validated = extractor._validate_and_fix_elements(elements)

        assert all(e.name != "fake_trigger" for e in validated)

    def test_validate_keeps_valid_trigger(self, extractor: SQLElementExtractor) -> None:
        """Test that valid triggers are kept."""
        valid_trigger = SQLTrigger(
            name="my_trigger",
            start_line=1,
            end_line=5,
            raw_text="CREATE TRIGGER my_trigger BEFORE INSERT ON users ...",
            sql_element_type=SQLElementType.TRIGGER,
        )

        elements = [valid_trigger]
        validated = extractor._validate_and_fix_elements(elements)

        assert any(e.name == "my_trigger" for e in validated)

    def test_validate_keeps_valid_table(self, extractor: SQLElementExtractor) -> None:
        """Test that valid tables are kept."""
        table = SQLTable(
            name="users",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE users (id INT);",
            sql_element_type=SQLElementType.TABLE,
        )

        elements = [table]
        validated = extractor._validate_and_fix_elements(elements)

        assert any(e.name == "users" for e in validated)


class TestSQLPluginUnit:
    """Unit tests for SQLPlugin that don't need tree-sitter-sql."""

    @pytest.fixture
    def plugin(self) -> SQLPlugin:
        """Create a SQLPlugin instance."""
        return SQLPlugin()

    def test_plugin_attributes(self, plugin: SQLPlugin) -> None:
        """Test plugin attributes."""
        assert plugin.language == "sql"
        assert ".sql" in plugin.supported_extensions
        assert hasattr(plugin, "extractor")
        assert isinstance(plugin.extractor, SQLElementExtractor)

    def test_extract_elements_with_none_tree(self, plugin: SQLPlugin) -> None:
        """Test extract_elements with None tree."""
        result = plugin.extract_elements(None, "")
        assert isinstance(result, dict)
        assert "functions" in result
        assert "classes" in result

    def test_extract_elements_with_mock_tree(self, plugin: SQLPlugin) -> None:
        """Test extract_elements with mock tree."""
        tree = Mock()
        root_node = Mock()
        root_node.children = []
        tree.root_node = root_node

        result = plugin.extract_elements(tree, "CREATE TABLE test (id INT);")
        assert isinstance(result, dict)


@pytest.mark.skipif(
    not TREE_SITTER_SQL_AVAILABLE,
    reason="tree-sitter-sql not installed",
)
class TestSQLElementExtractorIntegration:
    """Integration tests for SQLElementExtractor with actual tree-sitter-sql."""

    @pytest.fixture
    def plugin(self) -> SQLPlugin:
        """Create a plugin instance."""
        return SQLPlugin()

    # ==================== Table Extraction Tests ====================

    def test_extract_simple_table(self, plugin: SQLPlugin) -> None:
        """Test extraction of a simple CREATE TABLE statement."""
        sql_code = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE
);
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert result is not None
        classes = result.get("classes", [])
        assert any(c.name == "users" for c in classes)

    def test_extract_table_with_foreign_key(self, plugin: SQLPlugin) -> None:
        """Test extraction of table with foreign key constraint."""
        sql_code = """
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    total DECIMAL(10, 2),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert result is not None
        classes = result.get("classes", [])
        assert any(c.name == "orders" for c in classes)

    def test_extract_multiple_tables(self, plugin: SQLPlugin) -> None:
        """Test extraction of multiple tables."""
        sql_code = """
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name VARCHAR(200)
);

CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100)
);
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert result is not None
        classes = result.get("classes", [])
        table_names = [c.name for c in classes]
        assert "products" in table_names
        assert "categories" in table_names

    # ==================== View Extraction Tests ====================

    def test_extract_simple_view(self, plugin: SQLPlugin) -> None:
        """Test extraction of a simple CREATE VIEW statement."""
        sql_code = """
CREATE VIEW active_users AS
SELECT id, name, email
FROM users
WHERE status = 'active';
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert result is not None
        classes = result.get("classes", [])
        assert any(c.name == "active_users" for c in classes)

    def test_extract_view_with_joins(self, plugin: SQLPlugin) -> None:
        """Test extraction of view with JOIN operations."""
        sql_code = """
CREATE VIEW order_summary AS
SELECT o.id, u.name as customer, o.total
FROM orders o
JOIN users u ON o.user_id = u.id;
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert result is not None
        classes = result.get("classes", [])
        assert any(c.name == "order_summary" for c in classes)

    # ==================== Procedure Extraction Tests ====================

    def test_extract_simple_procedure(self, plugin: SQLPlugin) -> None:
        """Test extraction of a simple stored procedure."""
        sql_code = """
CREATE PROCEDURE get_user_by_id(IN user_id INT)
BEGIN
    SELECT * FROM users WHERE id = user_id;
END;
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert result is not None
        functions = result.get("functions", [])
        assert any("get_user_by_id" in f.name for f in functions)

    def test_extract_multiple_procedures(self, plugin: SQLPlugin) -> None:
        """Test extraction of multiple procedures."""
        sql_code = """
CREATE PROCEDURE proc_one()
BEGIN
    SELECT 1;
END;

CREATE PROCEDURE proc_two()
BEGIN
    SELECT 2;
END;
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert result is not None
        functions = result.get("functions", [])
        proc_names = [f.name for f in functions]
        assert any("proc_one" in name for name in proc_names)
        assert any("proc_two" in name for name in proc_names)

    # ==================== Function Extraction Tests ====================

    def test_extract_simple_function(self, plugin: SQLPlugin) -> None:
        """Test extraction of a SQL function."""
        sql_code = """
CREATE FUNCTION get_full_name(first_name VARCHAR(50), last_name VARCHAR(50))
RETURNS VARCHAR(101)
BEGIN
    RETURN CONCAT(first_name, ' ', last_name);
END;
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert result is not None
        functions = result.get("functions", [])
        assert any("get_full_name" in f.name for f in functions)

    # ==================== Trigger Extraction Tests ====================

    def test_extract_before_insert_trigger(self, plugin: SQLPlugin) -> None:
        """Test extraction of BEFORE INSERT trigger."""
        sql_code = """
CREATE TRIGGER before_user_insert
BEFORE INSERT ON users
FOR EACH ROW
BEGIN
    SET NEW.created_at = NOW();
END;
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert result is not None
        functions = result.get("functions", [])
        assert any("before_user_insert" in f.name for f in functions)

    # ==================== Index Extraction Tests ====================

    def test_extract_simple_index(self, plugin: SQLPlugin) -> None:
        """Test extraction of a simple index."""
        sql_code = """
CREATE INDEX idx_users_email ON users (email);
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert result is not None
        variables = result.get("variables", [])
        assert any("idx_users_email" in v.name for v in variables)

    def test_extract_unique_index(self, plugin: SQLPlugin) -> None:
        """Test extraction of a unique index."""
        sql_code = """
CREATE UNIQUE INDEX idx_users_email_unique ON users (email);
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert result is not None
        variables = result.get("variables", [])
        assert any("idx_users_email_unique" in v.name for v in variables)

    # ==================== SQL Elements Tests ====================

    def test_extract_sql_elements(self, plugin: SQLPlugin) -> None:
        """Test the enhanced extract_sql_elements method."""
        sql_code = """
CREATE TABLE employees (
    id INT PRIMARY KEY,
    name VARCHAR(100)
);

CREATE VIEW employee_list AS
SELECT * FROM employees;
"""
        import tree_sitter

        parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_sql.language()))
        tree = parser.parse(sql_code.encode("utf-8"))

        sql_elements = plugin.extractor.extract_sql_elements(tree, sql_code)

        assert isinstance(sql_elements, list)
        for elem in sql_elements:
            assert isinstance(elem, CodeElement)

    # ==================== Edge Cases ====================

    def test_empty_source_code(self, plugin: SQLPlugin) -> None:
        """Test extraction from empty source code."""
        result = extract_elements_from_sql(plugin, "")

        assert isinstance(result, dict)
        assert len(result.get("classes", [])) == 0
        assert len(result.get("functions", [])) == 0

    def test_comments_only(self, plugin: SQLPlugin) -> None:
        """Test extraction from comments-only code."""
        sql_code = """
-- This is a comment
/* Multi-line
   comment */
"""
        result = extract_elements_from_sql(plugin, sql_code)
        assert isinstance(result, dict)

    def test_malformed_sql(self, plugin: SQLPlugin) -> None:
        """Test extraction from malformed SQL."""
        sql_code = """
CREATE TABLE incomplete (
    id INT
"""
        result = extract_elements_from_sql(plugin, sql_code)
        assert isinstance(result, dict)

    def test_mixed_statements(self, plugin: SQLPlugin) -> None:
        """Test extraction from mixed SQL statements."""
        sql_code = """
CREATE TABLE logs (
    id INT PRIMARY KEY,
    message TEXT
);

INSERT INTO logs (message) VALUES ('test');

SELECT * FROM logs;

        CREATE VIEW recent_logs AS
SELECT * FROM logs ORDER BY id DESC LIMIT 10;
"""
        result = extract_elements_from_sql(plugin, sql_code)
        assert isinstance(result, dict)

    def test_complex_database_schema(self, plugin: SQLPlugin) -> None:
        """Test extraction from complex database schema."""
        sql_code = """
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE posts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE VIEW published_posts AS
SELECT p.id, p.title, p.content, u.username as author
FROM posts p
JOIN users u ON p.user_id = u.id;

CREATE PROCEDURE create_user(
    IN p_username VARCHAR(50),
    IN p_email VARCHAR(100),
    IN p_password_hash VARCHAR(255)
)
BEGIN
    INSERT INTO users (username, email, password_hash)
    VALUES (p_username, p_email, p_password_hash);
END;

        CREATE INDEX idx_users_email ON users (email);
"""
        result = extract_elements_from_sql(plugin, sql_code)

        assert isinstance(result, dict)
        table_names = [c.name for c in result.get("classes", [])]
        assert "users" in table_names


@pytest.mark.skipif(
    not TREE_SITTER_SQL_AVAILABLE,
    reason="tree-sitter-sql not installed",
)
class TestSQLPluginAsync:
    """Async tests for SQLPlugin."""

    @pytest.fixture
    def plugin(self) -> SQLPlugin:
        """Create a SQLPlugin instance."""
        return SQLPlugin()

    @pytest.mark.asyncio
    async def test_analyze_file_simple(self, plugin: SQLPlugin) -> None:
        """Test analyze_file with simple SQL."""
        sql_content = """
CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write(sql_content)
            temp_path = f.name

        try:
            from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

            request = AnalysisRequest(file_path=temp_path)
            result = await plugin.analyze_file(temp_path, request)

            assert result is not None and hasattr(result, "language")
            assert result.language == "sql"
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_analyze_file_with_procedures(self, plugin: SQLPlugin) -> None:
        """Test analyze_file with procedures."""
        sql_content = """
CREATE PROCEDURE test_proc()
BEGIN
    SELECT 1;
END;
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write(sql_content)
            temp_path = f.name

        try:
            from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

            request = AnalysisRequest(file_path=temp_path)
            result = await plugin.analyze_file(temp_path, request)

            assert result is not None and hasattr(result, "language")
            assert result.language == "sql"
        finally:
            os.unlink(temp_path)


class TestSQLElementModels:
    """Test SQL-specific element models and metadata."""

    def test_sql_element_types_available(self) -> None:
        """Test that SQL-specific element types are available."""
        for attr in ("TABLE", "VIEW", "PROCEDURE", "FUNCTION", "TRIGGER", "INDEX"):
            assert attr in SQLElementType.__members__

    def test_sql_table_with_columns_and_constraints(self) -> None:
        """Test SQLTable with columns and constraints."""
        table = SQLTable(
            name="users",
            start_line=1,
            end_line=10,
            raw_text="CREATE TABLE users...",
            sql_element_type=SQLElementType.TABLE,
            columns=[
                SQLColumn(name="id", data_type="INT", is_primary_key=True),
                SQLColumn(name="email", data_type="VARCHAR(255)", nullable=False),
            ],
            constraints=[
                SQLConstraint(
                    name="pk_users", constraint_type="PRIMARY_KEY", columns=["id"]
                ),
            ],
        )
        assert len(table.columns) == 2
        assert table.get_primary_key_columns() == ["id"]
        assert table.get_foreign_key_columns() == []

    def test_sql_function_and_procedure_models(self) -> None:
        """Test SQLFunction and SQLProcedure models."""
        func = SQLFunction(
            name="calc_total",
            start_line=1,
            end_line=5,
            raw_text="CREATE FUNCTION calc_total...",
            sql_element_type=SQLElementType.FUNCTION,
            return_type="DECIMAL(10, 2)",
        )
        assert func.return_type == "DECIMAL(10, 2)"

        proc = SQLProcedure(
            name="get_orders",
            start_line=10,
            end_line=20,
            raw_text="CREATE PROCEDURE get_orders...",
            sql_element_type=SQLElementType.PROCEDURE,
            parameters=[SQLParameter(name="uid", data_type="INT", direction="IN")],
        )
        assert proc.parameters[0].direction == "IN"

    def test_sql_trigger_and_index_models(self) -> None:
        """Test SQLTrigger and SQLIndex models."""
        trigger = SQLTrigger(
            name="upd_ts",
            start_line=1,
            end_line=5,
            raw_text="CREATE TRIGGER upd_ts AFTER UPDATE ON users",
            sql_element_type=SQLElementType.TRIGGER,
            trigger_timing="AFTER",
            trigger_event="UPDATE",
            table_name="users",
        )
        assert trigger.trigger_timing == "AFTER"
        assert trigger.table_name == "users"

        index = SQLIndex(
            name="idx_email",
            start_line=10,
            end_line=10,
            raw_text="CREATE INDEX idx_email ON users(email)",
            sql_element_type=SQLElementType.INDEX,
            table_name="users",
            indexed_columns=["email"],
            is_unique=True,
        )
        assert index.is_unique


class TestSQLPluginTreeSitterLanguage:
    """Test tree-sitter language loading and plugin init."""

    def test_get_tree_sitter_language_missing(self) -> None:
        """Test get_tree_sitter_language when tree-sitter-sql is not available."""
        plugin = SQLPlugin()
        plugin._cached_language = None
        with patch.dict("sys.modules", {"tree_sitter_sql": None}):
            try:
                plugin.get_tree_sitter_language()
                pytest.fail("Should have raised RuntimeError")
            except RuntimeError as e:
                assert "tree-sitter-sql is required" in str(e)
            except ImportError:
                pass

    def test_diagnostic_mode_init(self) -> None:
        """Test plugin diagnostic mode initialization."""
        assert SQLPlugin(diagnostic_mode=True).diagnostic_mode is True
        assert SQLPlugin(diagnostic_mode=False).diagnostic_mode is False
