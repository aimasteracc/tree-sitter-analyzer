"""Helpers for CSV HTML formatter output."""

from __future__ import annotations

import csv
import io
from typing import Any

from ..models import CodeElement, MarkupElement, StyleElement
from ._csv_safety import csv_safe_row


def format_html_csv(elements: list[CodeElement]) -> str:
    """Format HTML elements as CSV."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "Name",
            "Tag",
            "Element Class",
            "Start Line",
            "End Line",
            "Attributes",
            "Children Count",
            "Language",
        ]
    )

    for element in elements:
        writer.writerow(csv_safe_row(_csv_row(element)))

    csv_content = output.getvalue()
    output.close()
    return csv_content.rstrip("\n")


def _csv_row(element: CodeElement) -> list[Any]:
    if isinstance(element, MarkupElement):
        return _markup_csv_row(element)
    if isinstance(element, StyleElement):
        return _style_csv_row(element)
    if isinstance(element, dict):
        return _dict_csv_row(element)
    return _object_csv_row(element)


def _markup_csv_row(element: MarkupElement) -> list[Any]:
    return [
        element.name or "",
        element.tag_name or "",
        element.element_class or "",
        element.start_line,
        element.end_line,
        _html_attributes_csv(element.attributes),
        len(element.children),
        element.language,
    ]


def _style_csv_row(element: StyleElement) -> list[Any]:
    return [
        element.name or "",
        element.selector or "",
        element.element_class or "",
        element.start_line,
        element.end_line,
        _style_properties_csv(element.properties),
        0,
        element.language,
    ]


def _dict_csv_row(element: dict[str, Any]) -> list[Any]:
    return [
        element.get("name", ""),
        str(element.get("tag_name", element.get("selector", ""))),
        element.get("element_class", ""),
        element.get("start_line", 0),
        element.get("end_line", 0),
        str(element.get("attributes", element.get("properties", ""))),
        element.get("children_count", 0),
        element.get("language", "html"),
    ]


def _object_csv_row(element: Any) -> list[Any]:
    return [
        getattr(element, "name", ""),
        getattr(element, "tag_name", getattr(element, "selector", "")),
        getattr(element, "element_class", ""),
        getattr(element, "start_line", 0),
        getattr(element, "end_line", 0),
        "",
        0,
        getattr(element, "language", "html"),
    ]


def _html_attributes_csv(attributes: dict[str, Any] | None) -> str:
    if not attributes:
        return ""
    attrs = []
    for key, value in attributes.items():
        if value:
            attrs.append(f"{key}={value}")
        else:
            attrs.append(key)
    return "; ".join(attrs)


def _style_properties_csv(properties: dict[str, Any] | None) -> str:
    if not properties:
        return ""
    return "; ".join(f"{key}:{value}" for key, value in properties.items())
