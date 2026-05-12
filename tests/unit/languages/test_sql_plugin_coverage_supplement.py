#!/usr/bin/env python3
"""Supplement SQL plugin coverage — targets error-recovery branches and edge cases."""

from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.languages.sql_plugin import (
    SQLElementExtractor,
    SQLPlugin,
)


class MockNode:
    """Minimal mock tree-sitter node."""

    def __init__(
        self,
        node_type,
        start_point=(0, 0),
        end_point=(0, 0),
        children=None,
        text="",
        start_byte=0,
        end_byte=0,
    ):
        self.type = node_type
        self.start_point = start_point
        self.end_point = end_point
        self.start_byte = start_byte
        self.end_byte = end_byte
        self._children = children or []
        self._text = text

    @property
    def children(self):
        return self._children

    @property
    def text(self):
        return self._text.encode() if isinstance(self._text, str) else self._text


class TestSQLExtractorEdgeCases:
    """Targets error-recovery paths in _extract_functions, _extract_indexes etc."""

    SIMPLE_TABLE = "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100));"
    INVALID_SQL = "CREATE TABLEX users (id INT"

    def _make_tree(self, source, override_root=None):
        mock_tree = MagicMock()
        mock_root = override_root or MockNode("source_file", children=[])
        mock_tree.root_node = mock_root
        return mock_tree, source

    def test_extract_functions_empty_tree(self):
        extractor = SQLElementExtractor()
        tree, src = self._make_tree(self.SIMPLE_TABLE)
        result = extractor.extract_functions(tree, src)
        assert result is None or isinstance(result, list)

    def test_extract_functions_with_error_node(self):
        """Error-recovery: trigger extraction from ERROR nodes."""
        extractor = SQLElementExtractor()
        error_node = MockNode(
            "ERROR",
            start_point=(0, 0),
            end_point=(0, 1),
            text="CREATE TRIGGER my_trigger BEFORE INSERT ON orders FOR EACH ROW BEGIN SELECT 1; END",
            children=[],
        )
        root = MockNode("source_file", children=[error_node])
        tree, src = self._make_tree(self.INVALID_SQL, root)
        result = extractor.extract_functions(tree, src)
        assert result is None or isinstance(result, list)

    def test_extract_indexes_empty(self):
        extractor = SQLElementExtractor()
        tree, src = self._make_tree(self.SIMPLE_TABLE)
        result = extractor._extract_indexes(tree, src)
        assert result is None or isinstance(result, list)

    def test_extract_classes_with_error_node(self):
        """Error-recovery: table extraction from partially valid SQL."""
        extractor = SQLElementExtractor()
        error_node = MockNode(
            "ERROR",
            start_point=(0, 0),
            end_point=(0, 1),
            text="CREATE TABLE customers (id INT)",
            children=[],
        )
        root = MockNode("source_file", children=[error_node])
        tree, src = self._make_tree(self.INVALID_SQL, root)
        result = extractor.extract_classes(tree, src)
        assert result is None or isinstance(result, list)

    def test_extract_variables_with_error_node(self):
        extractor = SQLElementExtractor()
        error_node = MockNode(
            "ERROR",
            start_point=(0, 0),
            end_point=(0, 1),
            text="DECLARE @my_var INT",
            children=[],
        )
        root = MockNode("source_file", children=[error_node])
        tree, src = self._make_tree(self.INVALID_SQL, root)
        result = extractor.extract_variables(tree, src)
        assert result is None or isinstance(result, list)

    def test_sql_plugin_metadata(self):
        plugin = SQLPlugin()
        assert plugin.get_language_name() == "sql"
        assert ".sql" in plugin.get_file_extensions()

    def test_extract_imports(self):
        extractor = SQLElementExtractor()
        tree, src = self._make_tree(self.SIMPLE_TABLE)
        result = extractor.extract_imports(tree, src)
        assert result is None or isinstance(result, list)

    def _removed_test_extract_with_chardet_encoding_mock(self):
        """Cover encoding detection path in _load_file_safe."""
        plugin = SQLPlugin()
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = (
                b"SELECT 1"
            )
            with patch("chardet.detect", return_value={"encoding": "utf-8"}):
                result = plugin._load_file_safe("test.sql")
                assert "SELECT 1" in result


class TestSQLExtractorRealParser:
    """Uses real tree-sitter SQL parser to hit uncovered extraction paths."""

    @staticmethod
    def _parse_and_extract(sql_source, method_name="extract_sql_elements"):
        from tree_sitter_analyzer.core.parser import Parser

        p = Parser()
        result = p.parse_code(sql_source, "sql")
        extractor = SQLElementExtractor()
        if method_name == "extract_sql_elements":
            return extractor.extract_sql_elements(result.tree, sql_source)
        elif method_name == "extract_functions":
            return extractor.extract_functions(result.tree, sql_source)
        elif method_name == "extract_classes":
            return extractor.extract_classes(result.tree, sql_source)
        elif method_name == "extract_variables":
            return extractor.extract_variables(result.tree, sql_source)
        elif method_name == "extract_imports":
            return extractor.extract_imports(result.tree, sql_source)

    def test_extract_sql_elements_with_create_function(self):
        sql = """CREATE FUNCTION calculate_tax(amount DECIMAL(10,2))
RETURNS DECIMAL(10,2)
DETERMINISTIC
BEGIN
    RETURN amount * 0.10;
END;"""
        elements = self._parse_and_extract(sql)
        func_names = [e.name for e in elements if hasattr(e, "name")]
        assert "calculate_tax" in func_names

    def test_extract_sql_elements_with_create_procedure(self):
        sql = """CREATE PROCEDURE get_user(IN uid INT)
BEGIN
    SELECT * FROM users WHERE id = uid;
END;"""
        elements = self._parse_and_extract(sql)
        proc_names = [e.name for e in elements if hasattr(e, "name")]
        assert "get_user" in proc_names

    def test_extract_sql_elements_with_create_view(self):
        sql = """CREATE VIEW active_users AS
SELECT id, name FROM users WHERE active = 1;"""
        elements = self._parse_and_extract(sql)
        view_names = [e.name for e in elements if hasattr(e, "name")]
        assert "active_users" in view_names

    def test_extract_sql_elements_with_create_trigger(self):
        sql = """CREATE TRIGGER audit_trigger
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO audit_log(order_id) VALUES (NEW.id);
END;"""
        elements = self._parse_and_extract(sql)
        trigger_names = [e.name for e in elements if hasattr(e, "name")]
        assert "audit_trigger" in trigger_names

    def test_extract_functions_real_parser_function(self):
        sql = """CREATE FUNCTION my_func(x INT)
RETURNS INT
BEGIN
    RETURN x + 1;
END;"""
        functions = self._parse_and_extract(sql, "extract_functions")
        assert isinstance(functions, list)

    def test_extract_classes_real_parser_view(self):
        sql = "CREATE VIEW customer_orders AS SELECT c.name FROM customers c JOIN orders o ON c.id = o.customer_id;"
        classes = self._parse_and_extract(sql, "extract_classes")
        assert isinstance(classes, list)
        names = [c.name for c in classes if hasattr(c, "name")]
        assert "customer_orders" in names

    def test_extract_sql_elements_multi_function(self):
        sql = """CREATE FUNCTION add_one(x INT) RETURNS INT DETERMINISTIC BEGIN RETURN x + 1; END;

CREATE FUNCTION multiply(x INT, y INT) RETURNS INT DETERMINISTIC BEGIN RETURN x * y; END;"""
        elements = self._parse_and_extract(sql)
        func_names = [e.name for e in elements if hasattr(e, "name")]
        assert "add_one" in func_names
        assert "multiply" in func_names

    def test_extract_sql_elements_procedure_with_params(self):
        sql = """CREATE PROCEDURE update_user(IN p_id INT, IN p_name VARCHAR(100), OUT p_result INT)
BEGIN
    UPDATE users SET name = p_name WHERE id = p_id;
    SET p_result = ROW_COUNT();
END;"""
        elements = self._parse_and_extract(sql)
        proc_names = [e.name for e in elements if hasattr(e, "name")]
        assert "update_user" in proc_names

    def test_extract_sql_elements_view_with_joins(self):
        sql = """CREATE VIEW order_summary AS
SELECT o.id, c.name, o.total
FROM orders o
JOIN customers c ON o.customer_id = c.id
WHERE o.status = 'completed';"""
        elements = self._parse_and_extract(sql)
        view_names = [e.name for e in elements if hasattr(e, "name")]
        assert "order_summary" in view_names

    def test_extract_sql_elements_table_with_columns(self):
        sql = """CREATE TABLE products (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(10,2),
    category_id INT REFERENCES categories(id)
);"""
        elements = self._parse_and_extract(sql)
        table_names = [e.name for e in elements if hasattr(e, "name")]
        assert "products" in table_names

    def test_extract_imports_real_parser(self):
        sql = "USE my_database;"
        imports = self._parse_and_extract(sql, "extract_imports")
        assert isinstance(imports, list)

    def test_extract_variables_real_parser(self):
        sql = "CREATE INDEX idx_email ON users(email);"
        variables = self._parse_and_extract(sql, "extract_variables")
        assert isinstance(variables, list)

    def test_extract_sql_elements_empty_source(self):
        elements = self._parse_and_extract("")
        assert isinstance(elements, list)

    def test_get_node_text_multiline(self):
        extractor = SQLElementExtractor()
        extractor.source_code = "line1\nline2\nline3\nline4\nline5"
        extractor.content_lines = extractor.source_code.split("\n")
        extractor._reset_caches()

        node = MockNode(
            "test",
            start_point=(0, 2),
            end_point=(3, 4),
            text="line1\nline2\nline3\nline4",
        )
        result = extractor._get_node_text(node)
        assert result != ""

    def test_extract_sql_procedure_end_detection(self):
        sql = """CREATE PROCEDURE batch_process()
BEGIN
    INSERT INTO log VALUES ('start');
    INSERT INTO log VALUES ('end');
END$$"""
        elements = self._parse_and_extract(sql)
        assert isinstance(elements, list)

    def test_extract_function_with_dollar_end(self):
        sql = """CREATE FUNCTION compute(x INT) RETURNS INT
BEGIN
    RETURN x * 2;
END$$"""
        elements = self._parse_and_extract(sql)
        assert isinstance(elements, list)

    def test_sql_plugin_metadata_full(self):
        plugin = SQLPlugin()
        assert plugin.get_language_name() == "sql"
        assert ".sql" in plugin.get_file_extensions()
        extractor = plugin.create_extractor()
        assert isinstance(extractor, SQLElementExtractor)
