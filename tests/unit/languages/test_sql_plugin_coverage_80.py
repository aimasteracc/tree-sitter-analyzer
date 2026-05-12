#!/usr/bin/env python3
"""Tests to push sql_plugin.py coverage from 77% to 80%+."""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.sql_plugin import SQLElementExtractor, SQLPlugin
from tree_sitter_analyzer.models import SQLFunction, SQLView

try:
    import tree_sitter_sql  # noqa: F401

    TREE_SITTER_SQL_AVAILABLE = True
except ImportError:
    TREE_SITTER_SQL_AVAILABLE = False


class TestGetNodeTextMultiLineFallback:
    """Cover the multi-line _get_node_text fallback (lines 525-548)."""

    @pytest.fixture
    def extractor(self):
        ext = SQLElementExtractor()
        ext.source_code = "line0\nline1\nline2\nline3\nline4"
        ext.content_lines = ext.source_code.split("\n")
        ext._reset_caches()
        return ext

    def test_multiline_spanning_three_lines(self, extractor):
        """Cover multiline branch: start and end on different lines."""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 30
        node.start_point = (0, 0)
        node.end_point = (2, 5)
        text = extractor._get_node_text(node)
        assert "line0" in text
        assert "line2" in text

    def test_multiline_middle_only(self, extractor):
        """Cover multiline: start on line 1, end on line 3."""
        node = Mock()
        node.start_byte = 6
        node.end_byte = 25
        node.start_point = (1, 0)
        node.end_point = (3, 0)
        text = extractor._get_node_text(node)
        assert "line1" in text

    def test_multiline_start_equals_end_line(self, extractor):
        """Cover the i == start_point[0] and i == end_point[0] same-line branch."""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 5
        node.start_point = (0, 0)
        node.end_point = (0, 5)
        text = extractor._get_node_text(node)
        assert text == "line0"

    def test_multiline_fallback_exception(self, extractor):
        """Cover exception handler at line 546-548."""
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


class TestViewExtractionErrorNodes:
    """Cover lines 1405-1455: view extraction from ERROR nodes."""

    @pytest.fixture
    def extractor(self):
        return SQLElementExtractor()

    def test_extract_views_from_error_node(self, extractor):
        """Views inside ERROR nodes are extracted via regex."""
        code = "CREATE VIEW my_view AS SELECT * FROM users JOIN orders ON users.id = orders.uid;"
        extractor.source_code = code
        extractor.content_lines = code.split("\n")
        extractor._reset_caches()

        error_node = Mock()
        error_node.type = "ERROR"
        error_node.start_point = (0, 0)
        error_node.end_point = (0, len(code))
        error_node.children = []

        root = Mock()
        root.children = [error_node]
        root.type = "root"

        sql_elements = []
        extractor._extract_sql_views(root, sql_elements)
        assert any(isinstance(e, SQLView) and e.name == "my_view" for e in sql_elements)


class TestProcedureExtractionEnhanced:
    """Cover lines 1536-1551, 1660-1697: enhanced procedure extraction."""

    @pytest.fixture
    def extractor(self):
        return SQLElementExtractor()

    def test_extract_procedure_with_end_dollar(self, extractor):
        """Procedure with END$$ delimiter."""
        code = """CREATE PROCEDURE calc_tax(IN amount DECIMAL)
BEGIN
    DECLARE tax DECIMAL;
    SET tax = amount * 0.1;
    SELECT tax;
END$$"""
        extractor.source_code = code
        extractor.content_lines = code.split("\n")
        extractor._reset_caches()

        root = Mock()
        root.type = "root"
        root.children = []
        sql_elements = []
        extractor._extract_sql_procedures(root, sql_elements)
        assert any(e.name == "calc_tax" for e in sql_elements)


class TestTriggerExtractionRegex:
    """Cover lines 2010-2069: regex-based trigger extraction."""

    @pytest.fixture
    def extractor(self):
        return SQLElementExtractor()

    def _setup(self, extractor, code):
        extractor.source_code = code
        extractor.content_lines = code.split("\n")
        extractor._reset_caches()
        root = Mock()
        root.type = "root"
        root.children = []
        return root

    def test_trigger_regex_extraction(self, extractor):
        """Regex trigger extraction with timing and event."""
        code = """CREATE TRIGGER trg_audit
BEFORE INSERT ON users
FOR EACH ROW
BEGIN
    INSERT INTO audit_log VALUES (NEW.id);
END;"""
        root = self._setup(extractor, code)
        sql_elements = []
        extractor._extract_sql_triggers(root, sql_elements)
        assert any(e.name == "trg_audit" for e in sql_elements)

    def test_trigger_regex_no_end_semicolon(self, extractor):
        """Trigger without END; uses fallback end_line."""
        code = "CREATE TRIGGER short_trg AFTER DELETE ON logs FOR EACH ROW INSERT INTO del_log VALUES (OLD.id)"
        root = self._setup(extractor, code)
        sql_elements = []
        extractor._extract_sql_triggers(root, sql_elements)
        assert any(e.name == "short_trg" for e in sql_elements)

    def test_trigger_skips_short_name(self, extractor):
        """Trigger names <= 2 chars are skipped."""
        code = "CREATE TRIGGER ab AFTER INSERT ON t FOR EACH ROW BEGIN END;"
        root = self._setup(extractor, code)
        sql_elements = []
        extractor._extract_sql_triggers(root, sql_elements)
        assert not any(e.name == "ab" for e in sql_elements)

    def test_trigger_skips_keyword_names(self, extractor):
        """Trigger names that are SQL keywords (KEY, INDEX, etc.) are skipped."""
        code = "CREATE TRIGGER KEY AFTER INSERT ON t FOR EACH ROW BEGIN END;"
        root = self._setup(extractor, code)
        sql_elements = []
        extractor._extract_sql_triggers(root, sql_elements)
        assert not any(e.name == "KEY" for e in sql_elements)

    def test_trigger_skips_invalid_identifier(self, extractor):
        """Trigger names that fail _is_valid_identifier are skipped."""
        code = "CREATE TRIGGER trg_valid AFTER INSERT ON t FOR EACH ROW BEGIN END;"
        extractor.source_code = code
        extractor.content_lines = code.split("\n")
        extractor._reset_caches()
        root = Mock()
        root.type = "root"
        root.children = []
        sql_elements = []
        with patch.object(extractor, "_is_valid_identifier", return_value=False):
            extractor._extract_sql_triggers(root, sql_elements)
        assert not any(e.name == "trg_valid" for e in sql_elements)


class TestIndexExtractionRegexFallback:
    """Cover lines 2190-2248: regex-based index extraction."""

    @pytest.fixture
    def extractor(self):
        return SQLElementExtractor()

    def test_regex_index_extraction(self, extractor):
        """Regex fallback extracts CREATE INDEX."""
        code = "CREATE UNIQUE INDEX idx_email ON users (email, name)"
        extractor.source_code = code
        extractor.content_lines = code.split("\n")
        extractor._reset_caches()

        sql_elements = []
        extractor._extract_indexes_with_regex(sql_elements, set())
        assert any(e.name == "idx_email" for e in sql_elements)

    def test_regex_index_already_processed(self, extractor):
        """Already-processed indexes are skipped."""
        code = "CREATE INDEX idx_dup ON users (id)"
        extractor.source_code = code
        extractor.content_lines = code.split("\n")
        extractor._reset_caches()

        sql_elements = []
        extractor._extract_indexes_with_regex(sql_elements, {"idx_dup"})
        assert not any(e.name == "idx_dup" for e in sql_elements)


class TestViewSourceExtraction:
    """Cover lines 1539-1551: _extract_view_sources."""

    @pytest.fixture
    def extractor(self):
        ext = SQLElementExtractor()
        ext.source_code = "SELECT * FROM users"
        ext.content_lines = ext.source_code.split("\n")
        ext._reset_caches()
        return ext

    def test_extract_view_sources_with_from_clause(self, extractor):
        """Extract source tables from view definition with from_clause."""
        identifier = Mock()
        identifier.type = "identifier"
        identifier.start_byte = 14
        identifier.end_byte = 19
        identifier.start_point = (0, 14)
        identifier.end_point = (0, 19)
        identifier.children = []

        obj_ref = Mock()
        obj_ref.type = "object_reference"
        obj_ref.start_byte = 14
        obj_ref.end_byte = 19
        obj_ref.start_point = (0, 14)
        obj_ref.end_point = (0, 19)
        obj_ref.children = [identifier]

        from_clause = Mock()
        from_clause.type = "from_clause"
        from_clause.children = [obj_ref]

        view_node = Mock()
        view_node.type = "create_view"
        view_node.children = [from_clause]

        source_tables = []
        extractor._extract_view_sources(view_node, source_tables)
        assert "users" in source_tables


@pytest.mark.skipif(
    not TREE_SITTER_SQL_AVAILABLE, reason="tree-sitter-sql not installed"
)
class TestSQLPluginAnalyzeFile:
    """Cover lines 2312-2315, 2450-2452: plugin init and analyze_file."""

    @pytest.fixture
    def plugin(self):
        with patch("tree_sitter_analyzer.languages.sql_plugin.PlatformDetector") as mock_pd:
            mock_pd.detect.side_effect = Exception("no platform")
            return SQLPlugin()

    def test_plugin_init_platform_failure(self):
        """Plugin init handles platform detection failure gracefully."""
        with patch("tree_sitter_analyzer.languages.sql_plugin.PlatformDetector") as mock_pd:
            mock_pd.detect.side_effect = Exception("platform error")
            p = SQLPlugin()
            assert p.adapter is not None

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
