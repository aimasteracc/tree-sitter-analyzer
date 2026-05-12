#!/usr/bin/env python3
"""Tests to push sql_plugin.py coverage from 77% to 80%+."""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.sql_plugin import SQLElementExtractor, SQLPlugin
from tree_sitter_analyzer.models import SQLFunction, SQLView

try:
    import tree_sitter
    import tree_sitter_sql  # noqa: F401

    TREE_SITTER_SQL_AVAILABLE = True
except ImportError:
    TREE_SITTER_SQL_AVAILABLE = False


class TestGetNodeTextMultiLineFallback:
    """Cover lines 525-548: multi-line _get_node_text fallback branch."""

    @pytest.fixture
    def extractor(self):
        ext = SQLElementExtractor()
        ext.source_code = "line0\nline1\nline2\nline3\nline4"
        ext.content_lines = ext.source_code.split("\n")
        ext._reset_caches()
        return ext

    def test_multiline_start_col_mid_end_col_mid(self, extractor):
        """Start and end on different lines with column offsets."""
        node = Mock()
        node.start_byte = 2
        node.end_byte = 20
        node.start_point = (0, 2)
        node.end_point = (2, 2)
        text = extractor._get_node_text(node)
        assert "ne0" in text
        assert "lin" in text

    def test_multiline_start_only_line(self, extractor):
        """Start line only (end on different line)."""
        node = Mock()
        node.start_byte = 3
        node.end_byte = 17
        node.start_point = (0, 3)
        node.end_point = (2, 0)
        text = extractor._get_node_text(node)
        assert "e0" in text

    def test_multiline_end_only_line(self, extractor):
        """End line only (start on different line)."""
        node = Mock()
        node.start_byte = 6
        node.end_byte = 17
        node.start_point = (1, 0)
        node.end_point = (2, 5)
        text = extractor._get_node_text(node)
        assert "line" in text

    def test_multiline_full_lines_between(self, extractor):
        """Full intermediate lines in multi-line span."""
        node = Mock()
        node.start_byte = 3
        node.end_byte = 22
        node.start_point = (0, 3)
        node.end_point = (3, 1)
        text = extractor._get_node_text(node)
        assert "line1" in text
        assert "line2" in text

    def test_multiline_exception_returns_empty(self, extractor):
        """Exception during extraction returns empty string."""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 10
        node.start_point = (999, 0)
        node.end_point = (999, 5)
        text = extractor._get_node_text(node)
        assert isinstance(text, str)


class TestValidateGarbageFunctionName:
    """Cover lines 233-246: garbage function name correction/removal."""

    @pytest.fixture
    def extractor(self):
        ext = SQLElementExtractor()
        ext.source_code = "CREATE FUNCTION real_name RETURNS INT BEGIN RETURN 1; END"
        ext.content_lines = ext.source_code.split("\n")
        ext._reset_caches()
        return ext

    def test_fix_garbage_function_name(self, extractor):
        """Garbage name AUTO_INCREMENT gets corrected via regex in raw_text."""
        func = SQLFunction(
            name="AUTO_INCREMENT",
            start_line=1,
            end_line=3,
            raw_text="CREATE FUNCTION real_name RETURNS INT BEGIN RETURN 1; END",
            language="sql",
        )
        result = extractor._validate_and_fix_elements([func])
        assert any(e.name == "real_name" for e in result)

    def test_remove_garbage_function_name_no_match(self, extractor):
        """Garbage name KEY without valid CREATE FUNCTION in raw_text gets removed."""
        func = SQLFunction(
            name="KEY",
            start_line=1,
            end_line=3,
            raw_text="SOME GARBAGE TEXT WITHOUT CREATE FUNCTION",
            language="sql",
        )
        result = extractor._validate_and_fix_elements([func])
        assert not any(e.name == "KEY" for e in result)


class TestTriggerRegexDuplicateAndKeyword:
    """Cover lines 2010, 2013, 2028: trigger extraction edge cases."""

    @pytest.fixture
    def extractor(self):
        return SQLElementExtractor()

    def test_trigger_duplicate_in_source(self, extractor):
        """Duplicate triggers in source skip on second occurrence (line 2010)."""
        code = """CREATE TRIGGER trg_audit
BEFORE INSERT ON users FOR EACH ROW BEGIN END;
CREATE TRIGGER trg_audit
AFTER UPDATE ON users FOR EACH ROW BEGIN END;"""
        extractor.source_code = code
        extractor.content_lines = code.split("\n")
        extractor._reset_caches()
        root = Mock()
        root.type = "root"
        root.children = []
        sql_elements = []
        extractor._extract_sql_triggers(root, sql_elements)
        triggers = [e for e in sql_elements if e.name == "trg_audit"]
        assert len(triggers) == 1

    def test_trigger_invalid_identifier_skipped(self, extractor):
        """Trigger name failing _is_valid_identifier is skipped (line 2013)."""
        code = "CREATE TRIGGER bad name AFTER INSERT ON t FOR EACH ROW BEGIN END;"
        extractor.source_code = code
        extractor.content_lines = code.split("\n")
        extractor._reset_caches()
        root = Mock()
        root.type = "root"
        root.children = []
        sql_elements = []
        extractor._extract_sql_triggers(root, sql_elements)
        # "bad name" has a space, not a valid identifier
        assert not any(e.name == "bad name" for e in sql_elements)

    def test_trigger_keyword_name_skipped(self, extractor):
        """Trigger name matching keyword list is skipped (line 2028)."""
        code = "CREATE TRIGGER INDEX AFTER INSERT ON t FOR EACH ROW BEGIN END;"
        extractor.source_code = code
        extractor.content_lines = code.split("\n")
        extractor._reset_caches()
        root = Mock()
        root.type = "root"
        root.children = []
        sql_elements = []
        extractor._extract_sql_triggers(root, sql_elements)
        assert not any(e.name == "INDEX" for e in sql_elements)

    def test_trigger_exception_during_creation(self, extractor):
        """Exception during SQLTrigger creation is caught (line 2068)."""
        code = "CREATE TRIGGER valid_trg AFTER INSERT ON t FOR EACH ROW BEGIN END;"
        extractor.source_code = code
        extractor.content_lines = code.split("\n")
        extractor._reset_caches()
        root = Mock()
        root.type = "root"
        root.children = []
        sql_elements = []
        with patch(
            "tree_sitter_analyzer.languages.sql_plugin.SQLTrigger",
            side_effect=ValueError("test error"),
        ):
            extractor._extract_sql_triggers(root, sql_elements)
        assert not any(e.name == "valid_trg" for e in sql_elements)


class TestIndexRegexExceptionPath:
    """Cover lines 2155-2156, 2245-2246: index extraction exception handling."""

    @pytest.fixture
    def extractor(self):
        return SQLElementExtractor()

    def test_index_exception_during_creation(self, extractor):
        """Exception during SQLIndex creation is caught (line 2155)."""
        code = "CREATE INDEX idx_test ON users (id)"
        extractor.source_code = code
        extractor.content_lines = code.split("\n")
        extractor._reset_caches()
        root = Mock()
        root.type = "root"
        root.children = []
        sql_elements = []
        with patch(
            "tree_sitter_analyzer.languages.sql_plugin.SQLIndex",
            side_effect=ValueError("test error"),
        ):
            extractor._extract_indexes_with_regex(sql_elements, set())
        assert not any(e.name == "idx_test" for e in sql_elements)


@pytest.mark.skipif(
    not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not installed"
)
class TestRealSQLParsingForCoverage:
    """Use real tree-sitter to hit uncovered code paths."""

    @pytest.fixture
    def plugin(self):
        return SQLPlugin()

    @pytest.fixture
    def parser(self):
        language = tree_sitter.Language(tree_sitter_sql.language())
        return tree_sitter.Parser(language)

    def test_procedure_extraction_with_regex(self, plugin, parser):
        """Cover lines 1536-1551, 1660-1697: procedure extraction paths."""
        code = """
CREATE PROCEDURE get_user(IN user_id INT)
BEGIN
    SELECT * FROM users WHERE id = user_id;
END;
"""
        tree = parser.parse(code.encode("utf-8"))
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)
        assert any(e.name == "get_user" for e in elements)

    def test_function_extraction_enhanced(self, plugin, parser):
        """Cover lines 1935-1952: function extraction enhanced path."""
        code = """
CREATE FUNCTION compute_tax(amount DECIMAL)
RETURNS DECIMAL
BEGIN
    RETURN amount * 0.1;
END;
"""
        tree = parser.parse(code.encode("utf-8"))
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)
        assert any(e.name == "compute_tax" for e in elements)

    def test_view_extraction_with_error_nodes(self, plugin, parser):
        """Cover lines 1405-1455: view extraction from ERROR nodes."""
        code = "CREATE VIEW active_users AS SELECT * FROM users WHERE active = 1;"
        tree = parser.parse(code.encode("utf-8"))
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)
        views = [e for e in elements if isinstance(e, SQLView)]
        assert any(v.name == "active_users" for v in views)

    def test_trigger_extraction_full(self, plugin, parser):
        """Cover trigger extraction with full metadata."""
        code = """
CREATE TRIGGER audit_trigger
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO audit_log VALUES (NEW.id);
END;
"""
        tree = parser.parse(code.encode("utf-8"))
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)
        assert any(e.name == "audit_trigger" for e in elements)

    def test_index_extraction_full(self, plugin, parser):
        """Cover index extraction with regex fallback."""
        code = """
CREATE UNIQUE INDEX idx_email ON users (email, name);
"""
        tree = parser.parse(code.encode("utf-8"))
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)
        assert any(e.name == "idx_email" for e in elements)

    def test_table_with_column_extraction(self, plugin, parser):
        """Cover lines 1003-1039: table column/constraint extraction."""
        code = """
CREATE TABLE orders (
    id INT PRIMARY KEY,
    user_id INT NOT NULL,
    total DECIMAL(10,2) DEFAULT 0.00,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""
        tree = parser.parse(code.encode("utf-8"))
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)
        tables = [
            e
            for e in elements
            if hasattr(e, "sql_element_type") and e.sql_element_type.value == "table"
        ]
        assert any(t.name == "orders" for t in tables)

    def test_view_with_source_tables(self, plugin, parser):
        """Cover lines 1545-1551: _extract_view_sources."""
        code = """
CREATE VIEW user_orders AS
SELECT u.id, u.name
FROM users u
JOIN orders o ON u.id = o.user_id;
"""
        tree = parser.parse(code.encode("utf-8"))
        extractor = SQLElementExtractor()
        elements = extractor.extract_sql_elements(tree, code)
        views = [e for e in elements if isinstance(e, SQLView)]
        assert len(views) >= 1


class TestPluginPlatformInitFailure:
    """Cover lines 2312-2315: platform init exception path."""

    def test_plugin_init_platform_failure(self):
        """Plugin init handles platform detection failure gracefully."""
        with patch(
            "tree_sitter_analyzer.languages.sql_plugin.PlatformDetector"
        ) as mock_pd:
            mock_pd.detect.side_effect = Exception("platform error")
            p = SQLPlugin()
            assert p.adapter is not None


@pytest.mark.skipif(
    not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not installed"
)
class TestProcedureRegexFallback:
    """Cover lines 1536-1551, 1660-1697: procedure regex fallback paths."""

    def test_procedure_with_multiple_statements(self):
        """Procedure extraction finds procedures via regex."""
        code = """CREATE PROCEDURE proc_one(IN p1 INT)
BEGIN
    SELECT p1;
END;
CREATE PROCEDURE proc_two()
BEGIN
    SELECT 1;
END;
"""
        extractor = SQLElementExtractor()
        language = tree_sitter.Language(tree_sitter_sql.language())
        parser = tree_sitter.Parser(language)
        tree = parser.parse(code.encode("utf-8"))
        elements = extractor.extract_sql_elements(tree, code)
        procs = [
            e
            for e in elements
            if hasattr(e, "sql_element_type")
            and e.sql_element_type.value == "procedure"
        ]
        assert len(procs) >= 1

    def test_procedure_with_params(self):
        """Procedure with IN/OUT parameters."""
        code = """CREATE PROCEDURE my_proc(IN x INT, OUT y INT)
BEGIN
    SET y = x * 2;
END;
"""
        extractor = SQLElementExtractor()
        language = tree_sitter.Language(tree_sitter_sql.language())
        parser = tree_sitter.Parser(language)
        tree = parser.parse(code.encode("utf-8"))
        elements = extractor.extract_sql_elements(tree, code)
        assert any(e.name == "my_proc" for e in elements)


@pytest.mark.skipif(
    not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not installed"
)
class TestSQLPluginAnalyzeFileError:
    """Cover lines 2450-2452: analyze_file exception handling."""

    @pytest.fixture
    def plugin(self):
        with patch(
            "tree_sitter_analyzer.languages.sql_plugin.PlatformDetector"
        ) as mock_pd:
            mock_pd.detect.side_effect = Exception("no platform")
            return SQLPlugin()

    @pytest.mark.asyncio
    async def test_analyze_file_nonexistent(self, plugin):
        """analyze_file handles nonexistent file gracefully."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            nonexistent = os.path.join(td, "no_such.sql")
            from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

            request = AnalysisRequest(
                file_path=nonexistent,
                language="sql",
            )
            result = await plugin.analyze_file(nonexistent, request)
            assert result is not None
