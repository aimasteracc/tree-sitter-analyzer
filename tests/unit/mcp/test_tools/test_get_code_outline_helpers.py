"""Direct tests for the outline helpers split out in #1956.

The per-language enrichers only add a section when the file has no class
structure; each one is pinned here with plain element stand-ins.
"""

from __future__ import annotations

from types import SimpleNamespace as El
from typing import Any

from tree_sitter_analyzer.mcp.tools.get_code_outline_helpers import (
    _enrich_json_outline,
    _enrich_markdown_outline,
    _enrich_markup_outline,
    _enrich_sql_outline,
    _enrich_yaml_outline,
    _method_owned_by_class,
)


def _outline() -> dict[str, Any]:
    return {"statistics": {}}


def test_markup_outline_lists_html_and_css() -> None:
    outline = _outline()
    elements = [
        El(
            element_type="html_element",
            tag_name="div",
            element_class="box",
            start_line=1,
            end_line=3,
            attributes={"id": "a"},
        ),
        El(
            element_type="css_rule",
            selector=".box",
            element_class="box",
            start_line=5,
            end_line=7,
        ),
    ]

    _enrich_markup_outline(outline, elements, [])

    assert outline["html_elements"][0]["attributes"] == ["id"]
    assert outline["css_rules"][0]["selector"] == ".box"
    assert outline["statistics"]["html_element_count"] == 1
    assert outline["statistics"]["css_rule_count"] == 1


def test_sql_outline_groups_objects_by_type() -> None:
    outline = _outline()
    elements = [
        El(element_type="table", name="users", start_line=1, end_line=4),
        El(element_type="view", name="active", start_line=6, end_line=8),
    ]

    _enrich_sql_outline(outline, elements, [])

    assert outline["sql_objects"]["table"][0]["name"] == "users"
    assert outline["statistics"]["sql_object_count"] == 2


def test_markdown_outline_lists_blocks() -> None:
    outline = _outline()
    elements = [
        El(
            element_type="code_block",
            name="py",
            language="markdown",
            start_line=3,
            end_line=5,
        ),
    ]

    _enrich_markdown_outline(outline, elements, [])

    assert outline["blocks"][0]["type"] == "code_block"
    assert outline["statistics"]["block_count"] == 1


def test_yaml_outline_lists_documents_and_top_keys() -> None:
    outline = _outline()
    elements = [
        El(
            element_type="document",
            language="yaml",
            document_index=0,
            start_line=1,
            end_line=9,
        ),
        El(
            element_type="mapping",
            nesting_level=0,
            key="name",
            value_type="str",
            start_line=1,
            end_line=1,
        ),
    ]

    _enrich_yaml_outline(outline, elements, [])

    assert outline["yaml_documents"][0]["index"] == 0
    assert outline["yaml_top_keys"][0]["key"] == "name"


def test_json_outline_lists_root_and_top_keys() -> None:
    outline = _outline()
    elements = [
        El(
            element_type="document",
            language="json",
            value_type="object",
            child_count=1,
            start_line=1,
            end_line=3,
        ),
        El(
            element_type="pair",
            nesting_level=1,
            key="a",
            value_type="number",
            child_count=None,
            start_line=2,
            end_line=2,
        ),
    ]

    _enrich_json_outline(outline, elements, [])

    assert outline["json_root"]["type"] == "object"
    assert outline["json_top_keys"][0]["key"] == "a"
    assert outline["statistics"]["json_top_key_count"] == 1


def test_enrichers_skip_files_with_classes() -> None:
    outline = _outline()
    elements = [El(element_type="table", name="t", start_line=1, end_line=1)]

    _enrich_sql_outline(outline, elements, [object()])

    assert "sql_objects" not in outline


def test_method_owned_by_class_by_span_or_receiver() -> None:
    inside = El(start_line=5, receiver_type=None)
    bound = El(start_line=50, receiver_type="*Counter")

    assert _method_owned_by_class(inside, "Counter", 1, 10)
    assert _method_owned_by_class(bound, "Counter", 1, 10)
    assert not _method_owned_by_class(bound, "Other", 1, 10)
