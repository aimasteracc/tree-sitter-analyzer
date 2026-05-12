"""Tests for uncovered branches in sql_plugin.py."""

import pytest

from tree_sitter_analyzer.languages.sql_plugin import SQLElementExtractor, SQLPlugin
from tree_sitter_analyzer.models import SQLFunction, SQLProcedure, SQLView

try:
    import tree_sitter
    import tree_sitter_sql  # noqa: F401

    HAS_TS = True
except ImportError:
    HAS_TS = False

pytestmark = pytest.mark.skipif(not HAS_TS, reason="tree-sitter-sql not installed")


@pytest.fixture
def plugin():
    return SQLPlugin()


@pytest.fixture
def parser():
    language = tree_sitter.Language(tree_sitter_sql.language())
    return tree_sitter.Parser(language)


def _parse(parser, code):
    return parser.parse(code.encode("utf-8"))


class TestProcedureWithParameters:
    """Cover _extract_sql_procedures with IN/OUT/INOUT parameters."""

    def test_procedure_with_in_out_params(self, plugin, parser):
        code = """\
CREATE PROCEDURE transfer_funds(IN from_id INT, IN to_id INT, OUT status VARCHAR(20))
BEGIN
    UPDATE accounts SET balance = balance - 100 WHERE id = from_id;
    SET status = 'OK';
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        procs = [e for e in elements if isinstance(e, SQLProcedure)]
        assert len(procs) >= 1
        p = procs[0]
        assert p.name == "transfer_funds"
        assert any(param.name == "from_id" for param in p.parameters)
        assert any(param.name == "to_id" for param in p.parameters)

    def test_procedure_with_inout_param(self, plugin, parser):
        code = """\
CREATE PROCEDURE swap_values(INOUT val_x INT, INOUT val_y INT)
BEGIN
    SET @tmp = val_x;
    SET val_x = val_y;
    SET val_y = @tmp;
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        procs = [e for e in elements if isinstance(e, SQLProcedure)]
        assert len(procs) >= 1
        p = procs[0]
        assert p.name == "swap_values"
        assert len(p.parameters) >= 1

    def test_procedure_no_params(self, plugin, parser):
        code = """\
CREATE PROCEDURE cleanup_old()
BEGIN
    DELETE FROM logs WHERE created_at < '2024-01-01';
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        procs = [e for e in elements if isinstance(e, SQLProcedure)]
        assert len(procs) >= 1
        assert procs[0].name == "cleanup_old"


class TestFunctionWithReturnType:
    """Cover _extract_sql_functions_enhanced with RETURNS clause."""

    def test_function_with_returns(self, plugin, parser):
        code = """\
CREATE FUNCTION get_age(dob DATE) RETURNS INT
BEGIN
    RETURN TIMESTAMPDIFF(YEAR, dob, CURDATE());
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        funcs = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(funcs) >= 1
        f = funcs[0]
        assert f.name == "get_age"
        assert f.return_type is not None

    def test_function_with_nested_begin_end(self, plugin, parser):
        code = """\
CREATE FUNCTION compute(x INT) RETURNS INT
BEGIN
    IF x > 0 THEN
        BEGIN
            RETURN x * 2;
        END;
    END IF;
    RETURN 0;
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        funcs = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(funcs) >= 1
        assert funcs[0].name == "compute"

    def test_function_with_params(self, plugin, parser):
        code = """\
CREATE FUNCTION format_name(IN first_name VARCHAR(100), IN last_name VARCHAR(100)) RETURNS VARCHAR(201)
BEGIN
    RETURN CONCAT(first_name, ' ', last_name);
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        funcs = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(funcs) >= 1
        f = funcs[0]
        assert f.name == "format_name"
        assert len(f.parameters) >= 1


class TestViewWithSourceTables:
    """Cover _extract_view_sources and ERROR node view extraction."""

    def test_view_with_join(self, plugin, parser):
        code = """\
CREATE VIEW order_summary AS
SELECT o.id, c.name
FROM orders o
JOIN customers c ON o.customer_id = c.id;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        views = [e for e in elements if isinstance(e, SQLView)]
        assert len(views) >= 1
        v = views[0]
        assert v.name == "order_summary"

    def test_multiple_views(self, plugin, parser):
        code = """\
CREATE VIEW active_users AS
SELECT id, name FROM users WHERE status = 'active';

CREATE VIEW user_orders AS
SELECT u.id, u.name, COUNT(o.id) AS order_count
FROM users u
JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.name;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        views = [e for e in elements if isinstance(e, SQLView)]
        assert len(views) >= 1


class TestElementClassification:
    """Cover extract_elements classification branches."""

    def test_classify_functions(self, plugin, parser):
        code = """\
CREATE FUNCTION hello() RETURNS VARCHAR(50)
BEGIN
    RETURN 'Hello World';
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        extractor.extract_sql_elements(tree, code)

        plugin2 = SQLPlugin()
        result = plugin2.extract_elements(tree, code)
        assert "functions" in result
        assert "classes" in result
        assert "variables" in result
        assert "imports" in result

    def test_classify_tables_and_views(self, plugin, parser):
        code = """\
CREATE TABLE products (
    id INT PRIMARY KEY,
    name VARCHAR(100)
);

CREATE VIEW product_list AS
SELECT id, name FROM products;
"""
        tree = _parse(parser, code)
        plugin2 = SQLPlugin()
        result = plugin2.extract_elements(tree, code)
        assert len(result["classes"]) >= 1


class TestErrorNodeViewExtraction:
    """Cover _extract_sql_views ERROR node path (lines 1405-1455)."""

    def test_error_node_with_view(self, plugin, parser):
        """Unclosed BEGIN block produces ERROR node containing CREATE VIEW."""
        code = "BEGIN SELECT 1; CREATE VIEW error_block_view AS SELECT * FROM users;"
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        views = [e for e in elements if isinstance(e, SQLView)]
        assert len(views) >= 1
        assert any(v.name == "error_block_view" for v in views)

    def test_error_node_view_with_if_not_exists(self, plugin, parser):
        """ERROR node containing CREATE VIEW IF NOT EXISTS."""
        code = "BEGIN SELECT 1; CREATE VIEW IF NOT EXISTS safe_view AS SELECT a, b FROM mytable;"
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        views = [e for e in elements if isinstance(e, SQLView)]
        assert any(v.name == "safe_view" for v in views)


class TestFunctionRegexFallback:
    """Cover _extract_sql_functions regex fallback (lines 1013-1023)."""

    def test_function_with_keyword_name(self, plugin, parser):
        """Function named 'count' triggers AST rejection + regex fallback."""
        code = "CREATE FUNCTION count(IN x INT) RETURNS INT RETURN x + 1;"
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        # Both AST and regex reject 'count' as invalid, so no function extracted
        # But both code paths are exercised
        funcs = [e for e in elements if isinstance(e, SQLFunction)]
        # 'count' is rejected by _is_valid_identifier, so no function
        assert len(funcs) == 0

    def test_function_with_column_name(self, plugin, parser):
        """Function named 'price' triggers AST rejection + regex fallback."""
        code = "CREATE FUNCTION price(IN x INT) RETURNS INT RETURN x * 2;"
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        # price is in common_column_names, should be rejected
        funcs = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(funcs) == 0


class TestProcedureRegexFallback:
    """Cover _extract_sql_procedures regex-based extraction paths."""

    def test_multi_procedure_extraction(self, plugin, parser):
        """Multiple procedures in one file tests iteration loop."""
        code = """\
CREATE PROCEDURE first_proc()
BEGIN
    SELECT 'first';
END;

CREATE PROCEDURE second_proc(IN param INT)
BEGIN
    SELECT param;
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        procs = [e for e in elements if isinstance(e, SQLProcedure)]
        assert len(procs) >= 1

    def test_procedure_with_dependencies(self, plugin, parser):
        """Procedure that references tables tests dependency extraction."""
        code = """\
CREATE PROCEDURE update_status(IN user_id INT, IN new_status VARCHAR(20))
BEGIN
    UPDATE users SET status = new_status WHERE id = user_id;
    INSERT INTO audit_log (user_id, action) VALUES (user_id, 'status_change');
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        procs = [e for e in elements if isinstance(e, SQLProcedure)]
        assert len(procs) >= 1


class TestEnhancedFunctionExtraction:
    """Cover _extract_sql_functions_enhanced text-based fallback paths."""

    def test_function_body_text_extraction(self, plugin, parser):
        """Function body parsed via text-based approach (not AST children)."""
        code = """\
CREATE FUNCTION calc_bonus(salary DECIMAL(10,2)) RETURNS DECIMAL(10,2)
BEGIN
    DECLARE bonus DECIMAL(10,2);
    SET bonus = salary * 0.1;
    RETURN bonus;
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        funcs = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(funcs) >= 1

    def test_function_with_return_type_metadata(self, plugin, parser):
        """Function with complex return type to test metadata extraction."""
        code = """\
CREATE FUNCTION get_full_name(first_id INT) RETURNS VARCHAR(255)
BEGIN
    DECLARE full_name VARCHAR(255);
    SELECT CONCAT(first_name, ' ', last_name) INTO full_name
    FROM users WHERE id = first_id;
    RETURN full_name;
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        funcs = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(funcs) >= 1
        f = funcs[0]
        assert f.return_type is not None

    def test_function_deterministic(self, plugin, parser):
        """DETERMINISTIC function to test metadata extraction."""
        code = """\
CREATE FUNCTION square(x INT) RETURNS INT DETERMINISTIC
BEGIN
    RETURN x * x;
END;
"""
        tree = _parse(parser, code)
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)

        funcs = [e for e in elements if isinstance(e, SQLFunction)]
        assert len(funcs) >= 1
