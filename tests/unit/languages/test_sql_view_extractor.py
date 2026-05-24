"""Tests for sql_plugin/view_extractor.py — 100% coverage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages.sql_plugin.view_extractor import (
    _extract_view_sources,
    extract_sql_views,
)
from tree_sitter_analyzer.models import SQLView


@dataclass
class FakeNode:
    type: str = "create_view"
    start_point: tuple[int, int] = (0, 0)
    end_point: tuple[int, int] = (3, 0)
    children: list[Any] = field(default_factory=list)

    def child_by_field_name(self, name: str) -> Any:
        return None


def _traverse(nodes):
    def _gen(root):
        yield root
        for child in getattr(root, "children", []):
            yield from _gen(child)

    return _gen(nodes)


class TestExtractSqlViewsFromErrorNode:
    def test_error_node_with_view(self):
        error_node = FakeNode(
            type="ERROR",
            start_point=(0, 0),
            end_point=(5, 0),
        )
        error_node.children = []

        def get_text(n):
            return "CREATE VIEW my_view AS SELECT * FROM users, orders JOIN products ON orders.id = products.id;"

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=error_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 1
        assert isinstance(sql_elements[0], SQLView)
        assert sql_elements[0].name == "my_view"
        assert "users" in sql_elements[0].source_tables
        assert "products" in sql_elements[0].source_tables

    def test_error_node_with_if_not_exists(self):
        error_node = FakeNode(type="ERROR", start_point=(0, 0), end_point=(2, 0))
        error_node.children = []

        def get_text(n):
            return "CREATE VIEW IF NOT EXISTS backup_view AS SELECT * FROM data;"

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=error_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 1
        assert sql_elements[0].name == "backup_view"

    def test_error_node_empty_text_skipped(self):
        error_node = FakeNode(type="ERROR", start_point=(0, 0), end_point=(1, 0))
        error_node.children = []

        def get_text(n):
            return ""

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=error_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 0

    def test_error_node_invalid_identifier_skipped(self):
        error_node = FakeNode(type="ERROR", start_point=(0, 0), end_point=(1, 0))
        error_node.children = []

        def get_text(n):
            return "CREATE VIEW SELECT AS SELECT 1"

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=error_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 0

    def test_error_node_duplicate_view_skipped(self):
        error_node = FakeNode(type="ERROR", start_point=(0, 0), end_point=(2, 0))
        error_node.children = []

        def get_text(n):
            return "CREATE VIEW dup_view AS SELECT 1"

        existing = SQLView(
            name="dup_view",
            start_line=1,
            end_line=1,
            raw_text="CREATE VIEW dup_view AS SELECT 1",
            language="sql",
            source_tables=[],
            dependencies=[],
        )
        sql_elements: list[Any] = [existing]
        extract_sql_views(
            root_node=error_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 1

    def test_error_node_view_without_semicolon(self):
        error_node = FakeNode(type="ERROR", start_point=(0, 0), end_point=(1, 0))
        error_node.children = []

        def get_text(n):
            return "CREATE VIEW no_semi AS SELECT * FROM users"

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=error_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 1
        assert sql_elements[0].name == "no_semi"

    def test_error_node_multiple_views(self):
        error_node = FakeNode(type="ERROR", start_point=(0, 0), end_point=(5, 0))
        error_node.children = []

        def get_text(n):
            return "CREATE VIEW v1 AS SELECT 1; CREATE VIEW v2 AS SELECT 2;"

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=error_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 2


class TestExtractSqlViewsFromCreateViewNode:
    def test_create_view_with_regex_name(self):
        view_node = FakeNode(type="create_view", start_point=(0, 0), end_point=(3, 0))

        def get_text(n):
            if n is view_node:
                return "CREATE VIEW my_view AS SELECT * FROM users"
            return str(n)

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=view_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 1
        assert sql_elements[0].name == "my_view"

    def test_create_view_if_not_exists(self):
        view_node = FakeNode(type="create_view", start_point=(0, 0), end_point=(2, 0))

        def get_text(n):
            if n is view_node:
                return "CREATE VIEW IF NOT EXISTS safe_view AS SELECT 1"
            return str(n)

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=view_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 1
        assert sql_elements[0].name == "safe_view"

    def test_create_view_invalid_name_falls_back_to_children(self):
        child_id = FakeNode(type="identifier", start_point=(0, 0), end_point=(0, 10))
        child_ref = FakeNode(
            type="object_reference",
            start_point=(0, 0),
            end_point=(0, 10),
            children=[child_id],
        )
        view_node = FakeNode(
            type="create_view",
            start_point=(0, 0),
            end_point=(3, 0),
            children=[child_ref],
        )

        def get_text(n):
            if n is child_id:
                return "valid_name"
            if n is view_node:
                return "SOME INVALID TEXT"
            return str(n)

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=view_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 1
        assert sql_elements[0].name == "valid_name"

    def test_create_view_child_name_is_sql_keyword_skipped(self):
        child_id = FakeNode(type="identifier", start_point=(0, 0), end_point=(0, 10))
        child_ref = FakeNode(
            type="object_reference",
            children=[child_id],
        )
        view_node = FakeNode(
            type="create_view",
            start_point=(0, 0),
            end_point=(3, 0),
            children=[child_ref],
        )

        def get_text(n):
            if n is child_id:
                return "SELECT"
            if n is view_node:
                return ""
            return str(n)

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=view_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 0

    def test_create_view_no_name_found(self):
        view_node = FakeNode(
            type="create_view", start_point=(0, 0), end_point=(1, 0), children=[]
        )

        def get_text(n):
            return ""

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=view_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 0

    def test_create_view_empty_text_skips_regex(self):
        child_id = FakeNode(type="identifier", start_point=(0, 0), end_point=(0, 10))
        child_ref = FakeNode(
            type="object_reference",
            children=[child_id],
        )
        view_node = FakeNode(
            type="create_view",
            start_point=(0, 0),
            end_point=(3, 0),
            children=[child_ref],
        )

        def get_text(n):
            if n is child_id:
                return "child_view"
            if n is view_node:
                return ""
            return str(n)

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=view_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 1
        assert sql_elements[0].name == "child_view"

    def test_create_view_exception_handled(self):
        view_node = FakeNode(type="create_view", start_point=(0, 0), end_point=(1, 0))
        view_node.children = []

        class BadNode:
            type = "create_view"
            start_point = (0, 0)
            end_point = (1, 0)
            children = []

            def child_by_field_name(self, name):
                return None

        def get_text(n):
            if n is view_node:
                return "CREATE VIEW ok_view AS SELECT 1"
            raise RuntimeError("unexpected node")

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=view_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )

    def test_create_view_regex_match_but_invalid_name_falls_to_children(self):
        child_id = FakeNode(type="identifier", start_point=(0, 0), end_point=(0, 10))
        child_ref = FakeNode(
            type="object_reference",
            children=[child_id],
        )
        view_node = FakeNode(
            type="create_view",
            start_point=(0, 0),
            end_point=(3, 0),
            children=[child_ref],
        )

        def get_text(n):
            if n is view_node:
                return "CREATE VIEW 123invalid AS SELECT 1"
            if n is child_id:
                return "fallback_name"
            return str(n)

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=view_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 1
        assert sql_elements[0].name == "fallback_name"

    def test_create_view_object_ref_no_identifier_child(self):
        child_ref = FakeNode(
            type="object_reference",
            children=[FakeNode(type="number")],
        )
        view_node = FakeNode(
            type="create_view",
            start_point=(0, 0),
            end_point=(3, 0),
            children=[child_ref],
        )

        def get_text(n):
            if n is view_node:
                return ""
            return str(n)

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=view_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 0

    def test_create_view_empty_object_ref_name(self):
        child_id = FakeNode(type="identifier", start_point=(0, 0), end_point=(0, 10))
        child_ref = FakeNode(
            type="object_reference",
            children=[child_id],
        )
        view_node = FakeNode(
            type="create_view",
            start_point=(0, 0),
            end_point=(3, 0),
            children=[child_ref],
        )

        def get_text(n):
            if n is child_id:
                return ""
            if n is view_node:
                return ""
            return str(n)

        sql_elements: list[Any] = []
        extract_sql_views(
            root_node=view_node,
            traverse_nodes=_traverse,
            get_node_text=get_text,
            source_code="",
            content_lines=[],
            sql_elements=sql_elements,
        )
        assert len(sql_elements) == 0


class TestExtractViewSources:
    def test_from_clause_with_object_reference(self):
        id_child = FakeNode(type="identifier")
        obj_ref = FakeNode(
            type="object_reference", start_point=(0, 0), end_point=(0, 5), children=[id_child]
        )
        from_clause = FakeNode(type="from_clause", children=[obj_ref])
        view_node = FakeNode(type="create_view", children=[from_clause])

        source_tables: list[str] = []
        _extract_view_sources(
            view_node=view_node,
            source_tables=source_tables,
            traverse_nodes=_traverse,
            get_node_text=lambda n: "users" if n is obj_ref else str(n),
        )
        assert "users" in source_tables

    def test_duplicate_table_not_added(self):
        id_child = FakeNode(type="identifier")
        obj_ref = FakeNode(
            type="object_reference", start_point=(0, 0), end_point=(0, 5), children=[id_child]
        )
        from_clause = FakeNode(type="from_clause", children=[obj_ref])
        view_node = FakeNode(type="create_view", children=[from_clause])

        source_tables = ["users"]
        _extract_view_sources(
            view_node=view_node,
            source_tables=source_tables,
            traverse_nodes=_traverse,
            get_node_text=lambda n: "users" if n is obj_ref else str(n),
        )
        assert source_tables.count("users") == 1

    def test_no_from_clause(self):
        view_node = FakeNode(type="create_view", children=[])

        source_tables: list[str] = []
        _extract_view_sources(
            view_node=view_node,
            source_tables=source_tables,
            traverse_nodes=_traverse,
            get_node_text=lambda n: "",
        )
        assert len(source_tables) == 0

    def test_empty_object_reference_identifier(self):
        id_child = FakeNode(type="identifier")
        obj_ref = FakeNode(
            type="object_reference", children=[id_child]
        )
        from_clause = FakeNode(type="from_clause", children=[obj_ref])
        view_node = FakeNode(type="create_view", children=[from_clause])

        source_tables: list[str] = []
        _extract_view_sources(
            view_node=view_node,
            source_tables=source_tables,
            traverse_nodes=_traverse,
            get_node_text=lambda n: "",
        )
        assert len(source_tables) == 0
