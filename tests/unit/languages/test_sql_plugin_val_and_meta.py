"""Tests for SQL plugin validate_and_fix, metadata extraction, and edge cases."""

import pytest

from tree_sitter_analyzer.languages.sql_plugin import (
    SQLElementExtractor,
    SQLPlugin,
)
from tree_sitter_analyzer.models import (
    SQLFunction,
    SQLTable,
    SQLTrigger,
    Variable,
)

try:
    import tree_sitter
    import tree_sitter_sql

    TREE_SITTER_SQL_AVAILABLE = True
except ImportError:
    TREE_SITTER_SQL_AVAILABLE = False


def _parse(sql: str):
    """Parse SQL and return (tree, source_code)."""
    if not TREE_SITTER_SQL_AVAILABLE:
        pytest.skip("tree-sitter-sql not available")
    lang = tree_sitter.Language(tree_sitter_sql.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(sql.encode("utf-8"))
    return tree, sql


class TestValidateAndFixPhantomFunction:
    """Test _validate_and_fix_elements removes phantom functions."""

    def test_phantom_function_removed(self):
        ext = SQLElementExtractor()
        ext.source_code = "CREATE TABLE t (id INT);"
        ext.content_lines = ext.source_code.split("\n")

        phantom = SQLFunction(
            name="phantom_func",
            start_line=1,
            end_line=1,
            raw_text="CREATE TABLE t (id INT);",
            language="sql",
        )
        result = ext._validate_and_fix_elements([phantom])
        assert len(result) == 0

    def test_valid_function_kept(self):
        ext = SQLElementExtractor()
        ext.source_code = "CREATE FUNCTION my_func() RETURNS INT BEGIN RETURN 1; END;"
        ext.content_lines = ext.source_code.split("\n")

        func = SQLFunction(
            name="my_func",
            start_line=1,
            end_line=1,
            raw_text="CREATE FUNCTION my_func() RETURNS INT BEGIN RETURN 1; END;",
            language="sql",
        )
        result = ext._validate_and_fix_elements([func])
        assert len(result) == 1
        assert result[0].name == "my_func"


class TestValidateAndFixNameCorrection:
    """Test name correction for triggers and functions."""

    def test_trigger_name_fixed(self):
        ext = SQLElementExtractor()
        sql = "CREATE TRIGGER trg_before_insert BEFORE INSERT ON users FOR EACH ROW BEGIN END;"
        ext.source_code = sql
        ext.content_lines = sql.split("\n")

        trigger = SQLTrigger(
            name="wrong_name",
            start_line=1,
            end_line=1,
            raw_text=sql,
            language="sql",
        )
        result = ext._validate_and_fix_elements([trigger])
        assert len(result) == 1
        assert result[0].name == "trg_before_insert"

    def test_garbage_function_name_auto_increment_removed(self):
        ext = SQLElementExtractor()
        sql = "CREATE TABLE t (id INT AUTO_INCREMENT, PRIMARY KEY (id));"
        ext.source_code = sql
        ext.content_lines = sql.split("\n")

        func = SQLFunction(
            name="AUTO_INCREMENT",
            start_line=1,
            end_line=1,
            raw_text=sql,
            language="sql",
        )
        result = ext._validate_and_fix_elements([func])
        assert len(result) == 0

    def test_function_name_corrected(self):
        ext = SQLElementExtractor()
        sql = "CREATE FUNCTION calc_total(x INT) RETURNS INT BEGIN RETURN x; END;"
        ext.source_code = sql
        ext.content_lines = sql.split("\n")

        func = SQLFunction(
            name="wrong_func",
            start_line=1,
            end_line=1,
            raw_text=sql,
            language="sql",
        )
        result = ext._validate_and_fix_elements([func])
        assert len(result) == 1
        assert result[0].name == "calc_total"


class TestGetNodeTextMultilineFallback:
    """Test _get_node_text multiline fallback path."""

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not available"
    )
    def test_multiline_node_text(self):
        sql = "CREATE TABLE users (\n  id INT PRIMARY KEY,\n  name VARCHAR(100)\n);"
        tree, source = _parse(sql)
        ext = SQLElementExtractor()
        ext.source_code = source
        ext.content_lines = source.split("\n")

        root = tree.root_node
        text = ext._get_node_text(root)
        assert "CREATE TABLE" in text


class TestExtractSQLTriggersNoEndFallback:
    """Test trigger extraction when END; is not found."""

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not available"
    )
    def test_trigger_without_end_semicolon(self):
        sql = "CREATE TRIGGER my_trg BEFORE INSERT ON users FOR EACH ROW SET x = 1"
        tree, source = _parse(sql)
        ext = SQLElementExtractor()
        ext.source_code = source
        ext.content_lines = source.split("\n")

        sql_elements = []
        ext._extract_sql_triggers(tree.root_node, sql_elements)
        assert any(e.name == "my_trg" for e in sql_elements)


class TestExtractFunctionMetadata:
    """Test _extract_function_metadata with real tree nodes."""

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not available"
    )
    def test_metadata_with_real_node(self):
        sql = "CREATE FUNCTION add_one(x INT) RETURNS INT BEGIN RETURN x + 1; END;"
        tree, source = _parse(sql)
        ext = SQLElementExtractor()
        ext.source_code = source
        ext.content_lines = source.split("\n")

        params = []
        deps = []
        func_node = tree.root_node
        ext._extract_function_metadata(func_node, params, None, deps)
        assert len(params) > 0


class TestProcedureParameterDirection:
    """Test procedure parameter direction detection."""

    def test_out_parameter(self):
        ext = SQLElementExtractor()
        params = []
        proc_text = "PROCEDURE my_proc(OUT result INT) BEGIN SET result = 1; END;"
        ext._extract_procedure_parameters(proc_text, params)
        assert len(params) > 0
        assert params[0].direction == "OUT"

    def test_default_in_parameter(self):
        ext = SQLElementExtractor()
        params = []
        proc_text = "PROCEDURE my_proc(p_id INT) BEGIN SET x = p_id; END;"
        ext._extract_procedure_parameters(proc_text, params)
        assert len(params) > 0
        assert params[0].direction == "IN"
        assert params[0].name == "p_id"
        assert params[0].data_type == "INT"


class TestSQLPluginDiagnosticMode:
    """Test SQLPlugin initialization with diagnostic mode."""

    def test_diagnostic_mode_init(self):
        plugin = SQLPlugin(diagnostic_mode=True)
        assert plugin.diagnostic_mode is True

    def test_normal_mode_init(self):
        plugin = SQLPlugin(diagnostic_mode=False)
        assert plugin.diagnostic_mode is False


class TestSQLPluginExtractElementsMapping:
    """Test extract_elements maps SQL-specific types to legacy buckets."""

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not available"
    )
    def test_table_maps_to_classes(self):
        sql = "CREATE TABLE users (id INT);"
        tree, source = _parse(sql)
        plugin = SQLPlugin()

        from unittest.mock import patch

        table_elem = SQLTable(
            name="users",
            start_line=1,
            end_line=3,
            raw_text="CREATE TABLE users (id INT);",
            language="sql",
        )

        with patch.object(
            plugin.extractor, "extract_sql_elements", return_value=[table_elem]
        ):
            result = plugin.extract_elements(tree, source)

        assert len(result["classes"]) >= 1

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not available"
    )
    def test_index_maps_to_variables(self):
        sql = "CREATE INDEX idx_name ON users(name);"
        tree, source = _parse(sql)
        plugin = SQLPlugin()

        from unittest.mock import patch

        index_elem = Variable(
            name="idx_name",
            start_line=1,
            end_line=1,
            raw_text="CREATE INDEX idx_name ON users(name);",
            language="sql",
        )

        with patch.object(
            plugin.extractor, "extract_sql_elements", return_value=[index_elem]
        ):
            result = plugin.extract_elements(tree, source)

        assert len(result["variables"]) >= 1


class TestViewRecoveryFromSource:
    """Test view recovery in _validate_and_fix_elements."""

    def test_recover_missing_view(self):
        ext = SQLElementExtractor()
        sql = "CREATE VIEW my_view AS SELECT * FROM users;"
        ext.source_code = sql
        ext.content_lines = sql.split("\n")

        result = ext._validate_and_fix_elements([])
        assert any(e.name == "my_view" for e in result)


class TestExtractProceduresWithTreeSitter:
    """Test enhanced procedure extraction with tree-sitter."""

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not available"
    )
    def test_procedure_with_parameters_extracted(self):
        sql = (
            "CREATE PROCEDURE my_proc(IN p_id INT, OUT p_name VARCHAR(100))\n"
            "BEGIN\n"
            "SELECT name INTO p_name FROM users WHERE id = p_id;\n"
            "END;"
        )
        tree, source = _parse(sql)
        ext = SQLElementExtractor()
        ext.source_code = source
        ext.content_lines = source.split("\n")

        sql_elements = []
        ext._extract_sql_procedures(tree.root_node, sql_elements)
        assert len(sql_elements) >= 1
        proc = sql_elements[0]
        assert proc.name == "my_proc"
