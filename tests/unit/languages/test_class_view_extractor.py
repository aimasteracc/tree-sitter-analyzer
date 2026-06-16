"""Coverage-boosting tests for _class_view_extractor.py (target: 20.6% → 85%+)."""

from unittest.mock import Mock

from tree_sitter_analyzer.languages.sql_plugin._class_view_extractor import (
    _append_class_view,
    _find_view_statement_end,
    _is_valid_view_identifier,
    _recover_single_line_view_span,
    _view_name,
    _view_name_from_children,
    _view_name_from_text,
    extract_class_views,
)
from tree_sitter_analyzer.models import Class

# ── _view_name_from_text ────────────────────────────────────────────────

class TestViewNameFromText:
    def test_simple_create_view(self):
        assert _view_name_from_text(
            "CREATE VIEW my_view AS SELECT * FROM t",
            lambda s: True,
        ) == "my_view"

    def test_create_view_if_not_exists(self):
        assert _view_name_from_text(
            "CREATE VIEW IF NOT EXISTS my_view AS SELECT 1",
            lambda s: True,
        ) == "my_view"

    def test_empty_text(self):
        assert _view_name_from_text("", lambda s: True) is None

    def test_no_view_keyword(self):
        assert _view_name_from_text("SELECT * FROM t", lambda s: True) is None

    def test_invalid_identifier(self):
        assert (
            _view_name_from_text(
                "CREATE VIEW SELECT AS SELECT * FROM t",
                lambda s: s.upper() not in {"SELECT"},
            )
            is None
        )

    def test_case_insensitive(self):
        assert _view_name_from_text(
            "create view my_view as select * from t",
            lambda s: True,
        ) == "my_view"


# ── _is_valid_view_identifier ────────────────────────────────────────────

class TestIsValidViewIdentifier:
    def test_valid_identifier(self):
        assert _is_valid_view_identifier("my_view", lambda s: True)

    def test_empty_string(self):
        assert not _is_valid_view_identifier("", lambda s: True)

    def test_invalid_identifier(self):
        assert not _is_valid_view_identifier("bad!", lambda s: s.isidentifier())

    def test_reserved_keyword(self):
        assert not _is_valid_view_identifier("SELECT", lambda s: True)
        assert not _is_valid_view_identifier("FROM", lambda s: True)
        assert not _is_valid_view_identifier("WHERE", lambda s: True)
        assert not _is_valid_view_identifier("AS", lambda s: True)
        assert not _is_valid_view_identifier("NULL", lambda s: True)
        assert not _is_valid_view_identifier("CURRENT_TIMESTAMP", lambda s: True)

    def test_reserved_keyword_lowercase(self):
        """Reserved check is case-insensitive (upper() comparison)."""
        assert not _is_valid_view_identifier("select", lambda s: True)


# ── _view_name_from_children ─────────────────────────────────────────────

class TestViewNameFromChildren:
    def test_object_reference_with_identifier(self):
        node = Mock()
        obj_ref = Mock()
        obj_ref.type = "object_reference"
        ident = Mock()
        ident.type = "identifier"
        obj_ref.children = [ident]
        node.children = [obj_ref]

        result = _view_name_from_children(
            node,
            lambda n: "valid_view",
            lambda s: True,
        )
        assert result == "valid_view"

    def test_no_object_reference(self):
        node = Mock()
        other = Mock()
        other.type = "other"
        node.children = [other]

        result = _view_name_from_children(
            node, lambda n: "x", lambda s: True
        )
        assert result is None

    def test_object_reference_without_identifier(self):
        node = Mock()
        obj_ref = Mock()
        obj_ref.type = "object_reference"
        other_child = Mock()
        other_child.type = "keyword"
        obj_ref.children = [other_child]
        node.children = [obj_ref]

        result = _view_name_from_children(
            node, lambda n: "x", lambda s: True
        )
        assert result is None

    def test_empty_children(self):
        node = Mock()
        node.children = []
        result = _view_name_from_children(
            node, lambda n: "x", lambda s: True
        )
        assert result is None

    def test_reserved_identifier_rejected(self):
        node = Mock()
        obj_ref = Mock()
        obj_ref.type = "object_reference"
        ident = Mock()
        ident.type = "identifier"
        obj_ref.children = [ident]
        node.children = [obj_ref]

        result = _view_name_from_children(
            node,
            lambda n: "SELECT",
            lambda s: True,
        )
        assert result is None


# ── _view_name ───────────────────────────────────────────────────────────

class TestViewName:
    def test_from_text_succeeds(self):
        node = Mock()
        result = _view_name(
            "CREATE VIEW abc AS SELECT 1",
            node,
            lambda n: "",
            lambda s: True,
        )
        assert result == "abc"

    def test_fallback_to_children(self):
        node = Mock()
        obj_ref = Mock()
        obj_ref.type = "object_reference"
        ident = Mock()
        ident.type = "identifier"
        obj_ref.children = [ident]
        node.children = [obj_ref]

        result = _view_name(
            "no view keyword here",
            node,
            lambda n: "from_ast",
            lambda s: True,
        )
        assert result == "from_ast"

    def test_no_name_found(self):
        node = Mock()
        node.children = []
        result = _view_name(
            "no match",
            node,
            lambda n: "",
            lambda s: True,
        )
        assert result is None


# ── _find_view_statement_end ─────────────────────────────────────────────

class TestFindViewStatementEnd:
    def test_finds_semicolon(self):
        lines = ["CREATE VIEW v AS", "SELECT * FROM t;", "other stuff"]
        assert _find_view_statement_end(0, lines) == 2

    def test_falls_back_to_create_keyword(self):
        lines = [
            "CREATE VIEW v AS",
            "SELECT * FROM t",
            "CREATE TABLE x",
        ]
        assert _find_view_statement_end(0, lines) == 2

    def test_empty_line_fallback(self):
        lines = [
            "CREATE VIEW v AS",
            "SELECT * FROM t",
            "something",
            "",
            "  ",
            "other",
        ]
        assert _find_view_statement_end(0, lines) == 3

    def test_beyond_50_lines_returns_none(self):
        lines = ["CREATE VIEW v AS"] + ["x"] * 60
        assert _find_view_statement_end(0, lines) is None

    def test_no_terminator(self):
        """Only one line, no semicolon, no next CREATE statement."""
        lines = ["CREATE VIEW v AS SELECT * FROM t"]
        assert _find_view_statement_end(0, lines) is None


# ── _recover_single_line_view_span ───────────────────────────────────────

class TestRecoverSingleLineViewSpan:
    def test_same_start_end_no_source(self):
        raw_text, end_line = _recover_single_line_view_span(
            "text", 5, 5, "v", "", []
        )
        assert raw_text == "text"
        assert end_line == 5

    def test_multiline_already(self):
        """When start_line != end_line, no recovery needed."""
        raw_text, end_line = _recover_single_line_view_span(
            "text", 5, 7, "v", "source", []
        )
        assert raw_text == "text"
        assert end_line == 7

    def test_recovery_finds_semicolon(self):
        raw_text, end_line = _recover_single_line_view_span(
            "CREATE VIEW v AS",
            1,
            1,
            "v",
            "source",
            [
                "CREATE VIEW v AS",
                "SELECT * FROM t;",
            ],
        )
        assert end_line == 2
        assert "SELECT" in raw_text

    def test_recovery_not_found_returns_original(self):
        raw_text, end_line = _recover_single_line_view_span(
            "CREATE VIEW v AS",
            1,
            1,
            "v",
            "source",
            ["CREATE VIEW v AS"],
        )
        assert end_line == 1
        assert raw_text == "CREATE VIEW v AS"


# ── _append_class_view ──────────────────────────────────────────────────

class TestAppendClassView:
    def test_appends_valid_view(self):
        node = Mock()
        node.start_point = (2, 0)  # line 3
        node.end_point = (3, 0)  # line 4
        node.children = []

        classes: list[Class] = []
        _append_class_view(
            node,
            classes,
            lambda n: "CREATE VIEW valid_v AS SELECT 1;",
            lambda s: True,
            "",
            [],
        )
        assert len(classes) == 1
        assert classes[0].name == "valid_v"
        assert classes[0].start_line == 3
        assert classes[0].language == "sql"

    def test_no_valid_name_returns_early(self):
        node = Mock()
        node.children = []
        classes: list[Class] = []
        _append_class_view(
            node, classes, lambda n: "SELECT * FROM t", lambda s: True, "", []
        )
        assert len(classes) == 0

    def test_exception_handled(self):
        """When start_point raises, exception is caught and logged."""
        node = Mock()
        node.start_point = None  # will raise TypeError
        classes: list[Class] = []
        # Should not raise
        _append_class_view(
            node,
            classes,
            lambda n: "CREATE VIEW v AS SELECT 1",
            lambda s: True,
            "",
            [],
        )
        assert len(classes) == 0


# ── extract_class_views ──────────────────────────────────────────────────

class TestExtractClassViews:
    def test_extracts_create_view_nodes(self):
        root = Mock()
        view_node = Mock()
        view_node.type = "create_view"
        view_node.start_point = (0, 0)
        view_node.end_point = (0, 50)

        def fake_traverse(r):
            yield view_node

        classes: list[Class] = []
        extract_class_views(
            root,
            classes,
            fake_traverse,
            lambda n: "CREATE VIEW v1 AS SELECT 1",
            lambda s: True,
            "",
            [],
        )
        assert len(classes) == 1
        assert classes[0].name == "v1"

    def test_skips_non_view_nodes(self):
        root = Mock()
        other_node = Mock()
        other_node.type = "create_table"

        def fake_traverse(r):
            yield other_node

        classes: list[Class] = []
        extract_class_views(
            root,
            classes,
            fake_traverse,
            lambda n: "",
            lambda s: True,
            "",
            [],
        )
        assert len(classes) == 0

    def test_view_with_invalid_name_skipped(self):
        root = Mock()
        view_node = Mock()
        view_node.type = "create_view"
        view_node.start_point = (0, 0)
        view_node.end_point = (0, 50)
        view_node.children = []

        def fake_traverse(r):
            yield view_node

        classes: list[Class] = []
        extract_class_views(
            root,
            classes,
            fake_traverse,
            lambda n: "CREATE VIEW NULL AS SELECT 1",
            lambda s: s.upper() not in {"NULL"},
            "",
            [],
        )
        assert len(classes) == 0
