"""Tests for sql_plugin._class_view_extractor — view extraction from SQL AST."""

from unittest.mock import MagicMock

from tree_sitter_analyzer.languages.sql_plugin._class_view_extractor import (
    _RESERVED_VIEW_NAMES,
    _find_view_statement_end,
    _is_valid_view_identifier,
    _recover_single_line_view_span,
    _view_name,
    _view_name_from_children,
    _view_name_from_text,
    extract_class_views,
)


def _mock_node(node_type="create_view", start_row=0, end_row=0, children=None, text=""):
    node = MagicMock()
    node.type = node_type
    node.start_point = (start_row, 0)
    node.end_point = (end_row, 0)
    node.children = children or []
    node.text = text.encode() if isinstance(text, str) else text
    return node


def _mock_identifier_child(name="my_view"):
    subchild = MagicMock()
    subchild.type = "identifier"
    subchild.text = name.encode()
    return subchild


def _mock_object_ref_child(name="my_view"):
    child = MagicMock()
    child.type = "object_reference"
    subchild = _mock_identifier_child(name)
    child.children = [subchild]
    return child


def _get_node_text(node):
    if hasattr(node, "text") and isinstance(node.text, bytes):
        return node.text.decode()
    return str(node)


def _is_valid_id(name):
    return bool(name) and name not in _RESERVED_VIEW_NAMES


class TestViewNameFromText:
    def test_extracts_simple_name(self):
        result = _view_name_from_text("CREATE VIEW my_view AS SELECT 1", _is_valid_id)
        assert result == "my_view"

    def test_extracts_if_not_exists(self):
        result = _view_name_from_text(
            "CREATE VIEW IF NOT EXISTS v1 AS SELECT 1", _is_valid_id
        )
        assert result == "v1"

    def test_reserved_name_rejected(self):
        result = _view_name_from_text("CREATE VIEW SELECT AS SELECT 1", _is_valid_id)
        assert result is None

    def test_empty_text(self):
        assert _view_name_from_text("", _is_valid_id) is None

    def test_no_match(self):
        assert _view_name_from_text("DROP TABLE x", _is_valid_id) is None

    def test_case_insensitive(self):
        result = _view_name_from_text("create view V1 as select 1", _is_valid_id)
        assert result == "V1"


class TestViewNameFromChildren:
    def test_extracts_from_object_reference(self):
        node = _mock_node(children=[_mock_object_ref_child("orders_view")])
        result = _view_name_from_children(node, _get_node_text, _is_valid_id)
        assert result == "orders_view"

    def test_skips_non_identifier_children(self):
        other = MagicMock()
        other.type = "keyword"
        other.children = []
        node = _mock_node(children=[other])
        result = _view_name_from_children(node, _get_node_text, _is_valid_id)
        assert result is None

    def test_reserved_identifier_skipped(self):
        child = MagicMock()
        child.type = "object_reference"
        sub = _mock_identifier_child("FROM")
        child.children = [sub]
        node = _mock_node(children=[child])
        result = _view_name_from_children(node, _get_node_text, _is_valid_id)
        assert result is None


class TestViewName:
    def test_prefers_text_match(self):
        node = _mock_node(text="CREATE VIEW my_v AS SELECT 1")
        result = _view_name(node.text.decode(), node, _get_node_text, _is_valid_id)
        assert result == "my_v"

    def test_falls_back_to_children(self):
        ref_child = _mock_object_ref_child("child_view")
        node = _mock_node(text="something without view", children=[ref_child])
        result = _view_name(_get_node_text(node), node, _get_node_text, _is_valid_id)
        assert result == "child_view"


class TestIsValidViewIdentifier:
    def test_valid(self):
        assert _is_valid_view_identifier("my_view", _is_valid_id) is True

    def test_empty(self):
        assert _is_valid_view_identifier("", _is_valid_id) is False

    def test_reserved(self):
        assert _is_valid_view_identifier("SELECT", _is_valid_id) is False


class TestFindViewStatementEnd:
    def test_finds_semicolon(self):
        lines = ["CREATE VIEW v AS SELECT 1;", "next line"]
        result = _find_view_statement_end(0, lines)
        assert result == 1

    def test_no_semicolon_finds_next_create(self):
        lines = ["CREATE VIEW v AS SELECT 1", "CREATE TABLE t (id INT)"]
        result = _find_view_statement_end(0, lines)
        assert result == 1

    def test_no_end_returns_none(self):
        lines = ["SELECT 1"]
        result = _find_view_statement_end(0, lines)
        assert result is None

    def test_empty_line_stops(self):
        lines = ["CREATE VIEW v AS SELECT 1", "", "next"]
        result = _find_view_statement_end(0, lines)
        assert result == 1


class TestRecoverSingleLineViewSpan:
    def test_multiline_stays_unchanged(self):
        text, end = _recover_single_line_view_span(
            "raw", 1, 5, "v", "src", ["a", "b", "c", "d", "e"]
        )
        assert text == "raw"
        assert end == 5

    def test_single_line_recovered(self):
        lines = ["CREATE VIEW v AS", "SELECT 1", "FROM t;"]
        text, end = _recover_single_line_view_span("CREATE VIEW v AS", 1, 1, "v", "src\n", lines)
        assert end == 3
        assert "FROM t" in text

    def test_empty_source(self):
        text, end = _recover_single_line_view_span("raw", 1, 1, "v", "", ["line"])
        assert text == "raw"


class TestExtractClassViews:
    def test_extracts_view(self):
        node = _mock_node(
            node_type="create_view",
            start_row=0,
            end_row=0,
            text="CREATE VIEW test_v AS SELECT 1",
        )
        classes = []

        def traverse(n):
            yield n

        extract_class_views(
            node, classes, traverse, _get_node_text, _is_valid_id,
            "CREATE VIEW test_v AS SELECT 1", ["CREATE VIEW test_v AS SELECT 1"]
        )
        assert len(classes) == 1
        assert classes[0].name == "test_v"
        assert classes[0].language == "sql"

    def test_skips_non_view_nodes(self):
        other = _mock_node(node_type="select_statement")
        classes = []

        def traverse(n):
            yield n

        extract_class_views(other, classes, traverse, _get_node_text, _is_valid_id, "x", ["x"])
        assert len(classes) == 0
