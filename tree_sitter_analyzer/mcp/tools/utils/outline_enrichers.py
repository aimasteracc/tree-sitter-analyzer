"""Outline enricher helpers — Phase 3 REQ-CLEAN-003.

Language-specific enrichment functions for GetCodeOutlineTool.

Functions:
    _enrich_markup_outline
    _enrich_sql_outline
    _enrich_markdown_outline
    _enrich_yaml_outline
    _enrich_json_outline
"""

from __future__ import annotations

from typing import Any

_SQL_OBJECT_TYPES: frozenset[str] = frozenset(
    {"table", "view", "procedure", "trigger", "index"}
)
_MD_HEADING_TYPES: frozenset[str] = frozenset({"heading"})
_MD_BLOCK_TYPES: frozenset[str] = frozenset(
    {"code_block", "table", "list", "task_list"}
)


def _enrich_markup_outline(
    outline: dict[str, Any], elements: list[Any], classes: list[Any]
) -> None:
    """Attach HTML / CSS element summaries when no class structure is present."""
    if classes:
        return
    markup_elements = [
        e for e in elements if getattr(e, "element_type", "") == "html_element"
    ]
    if markup_elements:
        outline["html_elements"] = [
            {
                "tag": getattr(e, "tag_name", getattr(e, "name", "?")),
                "class": getattr(e, "element_class", ""),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
                "attributes": list(getattr(e, "attributes", {}).keys()),
            }
            for e in markup_elements
        ]
        outline["statistics"]["html_element_count"] = len(markup_elements)
    css_elements = [e for e in elements if getattr(e, "element_type", "") == "css_rule"]
    if css_elements:
        outline["css_rules"] = [
            {
                "selector": getattr(e, "selector", getattr(e, "name", "?")),
                "class": getattr(e, "element_class", ""),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for e in css_elements
        ]
        outline["statistics"]["css_rule_count"] = len(css_elements)


def _enrich_sql_outline(
    outline: dict[str, Any], elements: list[Any], classes: list[Any]
) -> None:
    """Attach SQL object summaries (tables / views / procedures / ...)."""
    if classes:
        return
    sql_elements = [
        e for e in elements if getattr(e, "element_type", "") in _SQL_OBJECT_TYPES
    ]
    if not sql_elements:
        return
    by_type: dict[str, list[dict[str, Any]]] = {}
    for e in sql_elements:
        etype = getattr(e, "element_type", "unknown")
        by_type.setdefault(etype, []).append(
            {
                "name": getattr(e, "name", "?"),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
        )
    outline["sql_objects"] = by_type
    outline["statistics"]["sql_object_count"] = len(sql_elements)


def _enrich_markdown_outline(
    outline: dict[str, Any], elements: list[Any], classes: list[Any]
) -> None:
    """Attach Markdown headings + block summaries (guarded by language)."""
    if classes:
        return
    md_headings = [
        e
        for e in elements
        if getattr(e, "element_type", "") in _MD_HEADING_TYPES
        and getattr(e, "language", "") == "markdown"
    ]
    md_blocks = [
        e
        for e in elements
        if getattr(e, "element_type", "") in _MD_BLOCK_TYPES
        and getattr(e, "language", "") == "markdown"
    ]
    if md_headings:
        outline["headings"] = [
            {
                "text": getattr(e, "name", "?"),
                "level": getattr(e, "level", 0),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for e in md_headings
        ]
        outline["statistics"]["heading_count"] = len(md_headings)
    if md_blocks:
        outline["blocks"] = [
            {
                "type": getattr(e, "element_type", "?"),
                "name": getattr(e, "name", "?"),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for e in md_blocks
        ]
        outline["statistics"]["block_count"] = len(md_blocks)


def _enrich_yaml_outline(
    outline: dict[str, Any], elements: list[Any], classes: list[Any]
) -> None:
    """Attach YAML document + top-level mapping summaries (guarded by language)."""
    if classes:
        return
    yaml_docs = [
        e
        for e in elements
        if getattr(e, "element_type", "") == "document"
        and getattr(e, "language", "") == "yaml"
    ]
    yaml_mappings = [
        e
        for e in elements
        if getattr(e, "element_type", "") == "mapping"
        and getattr(e, "nesting_level", 1) == 0
    ]
    if yaml_docs:
        outline["yaml_documents"] = [
            {
                "index": getattr(e, "document_index", i),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for i, e in enumerate(yaml_docs)
        ]
        outline["statistics"]["yaml_document_count"] = len(yaml_docs)
    if yaml_mappings:
        outline["yaml_top_keys"] = [
            {
                "key": getattr(e, "key", getattr(e, "name", "?")),
                "value_type": getattr(e, "value_type", "?"),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for e in yaml_mappings
        ]
        outline["statistics"]["yaml_top_key_count"] = len(yaml_mappings)


def _enrich_json_outline(
    outline: dict[str, Any], elements: list[Any], classes: list[Any]
) -> None:
    """Attach JSON document root + top-level property summaries."""
    if classes:
        return
    json_doc = next(
        (
            e
            for e in elements
            if getattr(e, "element_type", "") == "document"
            and getattr(e, "language", "") == "json"
        ),
        None,
    )
    json_props = [
        e
        for e in elements
        if getattr(e, "element_type", "") in ("property", "pair")
        and getattr(e, "nesting_level", 0) == 1
    ]
    if json_doc is None and not json_props:
        return
    if json_doc is not None:
        outline["json_root"] = {
            "type": getattr(json_doc, "value_type", "unknown"),
            "child_count": getattr(json_doc, "child_count", None),
            "line_start": getattr(json_doc, "start_line", 0),
            "line_end": getattr(json_doc, "end_line", 0),
        }
    if json_props:
        outline["json_top_keys"] = [
            {
                "key": getattr(e, "key", getattr(e, "name", "?")),
                "value_type": getattr(e, "value_type", "?"),
                "child_count": getattr(e, "child_count", None),
                "line_start": getattr(e, "start_line", 0),
                "line_end": getattr(e, "end_line", 0),
            }
            for e in json_props
        ]
        outline["statistics"]["json_top_key_count"] = len(json_props)
