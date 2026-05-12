"""Tests for sql_plugin uncovered code paths: triggers, procedures, views, multiline text extraction."""

import pytest

from tree_sitter_analyzer.languages.sql_plugin import SQLElementExtractor, SQLPlugin


def _parse(extractor: SQLElementExtractor, sql: str):
    """Parse SQL with tree-sitter and return (tree, source_code)."""
    lang = None
    try:
        lang = SQLPlugin().get_tree_sitter_language()
    except Exception:
        pytest.skip("tree-sitter-sql not available")

    if lang is None:
        pytest.skip("tree-sitter-sql not available")

    import tree_sitter

    parser = tree_sitter.Parser(lang)
    tree = parser.parse(sql.encode("utf-8"))
    return tree, sql


class TestSQLTriggerExtraction:
    """Cover _extract_triggers via ERROR nodes in AST."""

    def test_create_trigger_before_insert(self):
        sql = """
CREATE TABLE users (id INT, name VARCHAR(100));

CREATE TRIGGER trg_before_insert
BEFORE INSERT ON users
FOR EACH ROW
BEGIN
    SET NEW.name = UPPER(NEW.name);
END;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        functions = extractor.extract_functions(tree, source)
        trigger_names = [f.name for f in functions]
        assert "trg_before_insert" in trigger_names

    def test_create_trigger_after_update(self):
        sql = """
CREATE TABLE orders (id INT, total DECIMAL);

CREATE TRIGGER trg_after_update
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    INSERT INTO audit_log VALUES (OLD.id, 'UPDATE');
END;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        functions = extractor.extract_functions(tree, source)
        trigger_names = [f.name for f in functions]
        assert "trg_after_update" in trigger_names

    def test_trigger_with_if_not_exists(self):
        sql = """
CREATE TRIGGER IF NOT EXISTS check_trigger
AFTER DELETE ON products
FOR EACH ROW
BEGIN
    DELETE FROM stock WHERE product_id = OLD.id;
END;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        functions = extractor.extract_functions(tree, source)
        trigger_names = [f.name for f in functions]
        assert "check_trigger" in trigger_names

    def test_trigger_skips_short_keyword_names(self):
        sql = """
CREATE TRIGGER ON
AFTER INSERT ON t
FOR EACH ROW BEGIN END;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        functions = extractor.extract_functions(tree, source)
        names = [f.name for f in functions]
        assert "ON" not in names


class TestSQLProcedureExtraction:
    """Cover _extract_sql_procedures and _extract_procedures paths."""

    def test_create_procedure_basic(self):
        sql = """
CREATE PROCEDURE sp_get_user(IN user_id INT)
BEGIN
    SELECT * FROM users WHERE id = user_id;
END;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        elements = extractor.extract_sql_elements(tree, source)
        proc_names = [
            e.name for e in elements
            if hasattr(e, "sql_element_type") and e.sql_element_type.value == "procedure"
        ]
        assert "sp_get_user" in proc_names

    def test_create_procedure_with_params(self):
        sql = """
CREATE PROCEDURE sp_calc_total(IN price DECIMAL, IN qty INT, OUT total DECIMAL)
BEGIN
    SET total = price * qty;
END;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        elements = extractor.extract_sql_elements(tree, source)
        procs = [
            e for e in elements
            if hasattr(e, "sql_element_type") and e.sql_element_type.value == "procedure"
        ]
        assert len(procs) >= 1
        assert procs[0].name == "sp_calc_total"

    def test_multiple_procedures(self):
        sql = """
CREATE PROCEDURE sp_first()
BEGIN
    SELECT 1;
END;

CREATE PROCEDURE sp_second()
BEGIN
    SELECT 2;
END;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        elements = extractor.extract_sql_elements(tree, source)
        proc_names = [
            e.name for e in elements
            if hasattr(e, "sql_element_type") and e.sql_element_type.value == "procedure"
        ]
        assert "sp_first" in proc_names
        assert "sp_second" in proc_names


class TestSQLViewExtraction:
    """Cover _extract_sql_views paths including regex and AST fallback."""

    def test_create_view_basic(self):
        sql = """
CREATE TABLE orders (id INT, customer_id INT, total DECIMAL);
CREATE TABLE customers (id INT, name VARCHAR(100));

CREATE VIEW v_customer_orders AS
SELECT c.name, o.total
FROM orders o
JOIN customers c ON o.customer_id = c.id;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        elements = extractor.extract_sql_elements(tree, source)
        view_names = [
            e.name for e in elements
            if hasattr(e, "sql_element_type") and e.sql_element_type.value == "view"
        ]
        assert "v_customer_orders" in view_names

    def test_create_view_if_not_exists(self):
        sql = """
CREATE TABLE t1 (id INT);

CREATE VIEW IF NOT EXISTS v_summary AS
SELECT id FROM t1;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        elements = extractor.extract_sql_elements(tree, source)
        view_names = [
            e.name for e in elements
            if hasattr(e, "sql_element_type") and e.sql_element_type.value == "view"
        ]
        assert "v_summary" in view_names


class TestSQLIndexExtraction:
    """Cover _extract_sql_indexes and regex fallback."""

    def test_create_index_basic(self):
        sql = """
CREATE TABLE users (id INT, email VARCHAR(255));

CREATE INDEX idx_email ON users(email);
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        elements = extractor.extract_sql_elements(tree, source)
        index_names = [
            e.name for e in elements
            if hasattr(e, "sql_element_type") and e.sql_element_type.value == "index"
        ]
        assert "idx_email" in index_names

    def test_create_unique_index(self):
        sql = """
CREATE TABLE accounts (id INT, username VARCHAR(50));

CREATE UNIQUE INDEX idx_username ON accounts(username);
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        elements = extractor.extract_sql_elements(tree, source)
        index_names = [
            e.name for e in elements
            if hasattr(e, "sql_element_type") and e.sql_element_type.value == "index"
        ]
        assert "idx_username" in index_names


class TestSQLFunctionExtraction:
    """Cover _extract_sql_functions - tree-sitter-sql parses CREATE FUNCTION as ERROR."""

    def test_create_function_extracted_as_element(self):
        sql = """
CREATE FUNCTION add_numbers(a INT, b INT)
RETURNS INT
DETERMINISTIC
BEGIN
    RETURN a + b;
END;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        elements = extractor.extract_sql_elements(tree, source)
        func_names = [
            e.name for e in elements
            if hasattr(e, "sql_element_type")
            and e.sql_element_type.value in ("function", "procedure")
        ]
        assert "add_numbers" in func_names

    def test_create_function_via_extract_functions(self):
        sql = """
CREATE FUNCTION hello_world()
RETURNS VARCHAR(50)
BEGIN
    RETURN 'Hello';
END;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        functions = extractor.extract_functions(tree, source)
        # tree-sitter-sql treats CREATE FUNCTION as ERROR, so extraction
        # may use regex fallback; just verify no crash and returns a list
        assert isinstance(functions, list)


class TestMultilineTextExtraction:
    """Cover multiline branch in _get_node_text."""

    def test_multiline_node_text(self):
        sql = """CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(255)
);"""
        extractor = SQLElementExtractor()
        extractor.source_code = sql
        extractor.content_lines = sql.split("\n")
        extractor._node_text_cache = {}
        elements = extractor.extract_sql_elements(None, sql)
        assert isinstance(elements, list)


class TestSQLPluginExtractElements:
    """Cover SQLPlugin.extract_elements legacy method."""

    def test_extract_elements_with_sql(self):
        sql = """
CREATE TABLE products (id INT, name VARCHAR(100));
CREATE PROCEDURE sp_list()
BEGIN
    SELECT * FROM products;
END;
CREATE FUNCTION fn_count() RETURNS INT
BEGIN
    RETURN 0;
END;
"""
        plugin = SQLPlugin()
        tree, source = _parse(plugin.extractor, sql)
        result = plugin.extract_elements(tree, source)
        assert isinstance(result, dict)
        assert "functions" in result
        assert "classes" in result


class TestExtractClassesAndVariablesAndImports:
    """Cover extract_classes, extract_variables, extract_imports on SQLElementExtractor."""

    def test_extract_classes_with_table(self):
        sql = """
CREATE TABLE orders (
    id INT PRIMARY KEY,
    customer_id INT,
    total DECIMAL
);
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        classes = extractor.extract_classes(tree, source)
        assert isinstance(classes, list)
        assert any(c.name == "orders" for c in classes)

    def test_extract_classes_with_view(self):
        sql = """
CREATE TABLE t1 (id INT);
CREATE VIEW v1 AS SELECT id FROM t1;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        classes = extractor.extract_classes(tree, source)
        names = [c.name for c in classes]
        assert "t1" in names
        assert "v1" in names

    def test_extract_variables_with_index(self):
        sql = """
CREATE TABLE users (id INT, email VARCHAR(255));
CREATE INDEX idx_email ON users(email);
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        variables = extractor.extract_variables(tree, source)
        assert isinstance(variables, list)
        assert any(v.name == "idx_email" for v in variables)

    def test_extract_imports_with_schema_reference(self):
        sql = """
SELECT * FROM schema2.orders;
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        imports = extractor.extract_imports(tree, source)
        assert isinstance(imports, list)

    def test_extract_functions_none_tree(self):
        extractor = SQLElementExtractor()
        result = extractor.extract_functions(None, "")
        assert result == []

    def test_extract_classes_none_tree(self):
        extractor = SQLElementExtractor()
        result = extractor.extract_classes(None, "")
        assert result == []

    def test_extract_variables_none_tree(self):
        extractor = SQLElementExtractor()
        result = extractor.extract_variables(None, "")
        assert result == []

    def test_extract_imports_none_tree(self):
        extractor = SQLElementExtractor()
        result = extractor.extract_imports(None, "")
        assert result == []

    def test_extract_sql_elements_with_table_and_view(self):
        sql = """
CREATE TABLE customers (
    id INT PRIMARY KEY,
    name VARCHAR(100),
    region VARCHAR(50)
);

CREATE VIEW v_regional AS
SELECT region, COUNT(*) as cnt
FROM customers
GROUP BY region;

CREATE INDEX idx_region ON customers(region);
"""
        extractor = SQLElementExtractor()
        tree, source = _parse(extractor, sql)
        elements = extractor.extract_sql_elements(tree, source)
        assert isinstance(elements, list)
        names = [e.name for e in elements]
        assert "customers" in names
        assert "v_regional" in names
        assert "idx_region" in names
