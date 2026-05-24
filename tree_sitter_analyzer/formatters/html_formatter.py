#!/usr/bin/env python3
"""
HTML Formatter

Specialized formatter for HTML/CSS code elements including MarkupElement and StyleElement.
Provides HTML-specific formatting with element classification and hierarchy display.
"""

import json
from typing import Any

from ..models import CodeElement, MarkupElement, StyleElement
from ._html_classification_helpers import classify_html_elements
from ._html_compact_formatter_helpers import format_compact_html
from ._html_csv_formatter_helpers import format_html_csv
from ._html_formatter_helpers import (
    element_to_dict,
    format_element_tree,
    format_markup_elements,
    format_other_elements,
    format_style_elements,
)
from ._html_json_formatter_helpers import build_html_json_result
from .base_formatter import BaseFormatter
from .formatter_registry import IFormatter


class HtmlFormatter(BaseFormatter, IFormatter):
    """HTML-specific formatter for MarkupElement and StyleElement"""

    def __init__(self) -> None:
        """Initialize HTML formatter"""
        pass

    @staticmethod
    def get_format_name() -> str:
        return "html"

    def format(self, elements: list[CodeElement]) -> str:
        """Format HTML elements with hierarchy and classification"""
        if not elements:
            return "No HTML elements found."

        lines = ["# HTML Structure Analysis", ""]
        groups = classify_html_elements(
            elements,
            self._dict_to_markup_element,
            self._dict_to_style_element,
            self._element_to_dict,
        )

        if groups.markup_elements:
            lines.extend(self._format_markup_elements(groups.markup_elements))
        if groups.style_elements:
            lines.extend(self._format_style_elements(groups.style_elements))
        if groups.other_elements:
            lines.extend(self._format_other_elements(groups.other_elements))

        return "\n".join(lines)

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for HTML elements"""
        elements = analysis_result.get("elements", [])
        if not elements:
            return "No HTML elements found."

        markup_count = sum(1 for e in elements if isinstance(e, MarkupElement))
        style_count = sum(1 for e in elements if isinstance(e, StyleElement))
        other_count = len(elements) - markup_count - style_count

        lines = []
        lines.append("# HTML Analysis Summary")
        lines.append("")
        lines.append(f"**Total Elements:** {len(elements)}")
        lines.append(f"- Markup Elements: {markup_count}")
        lines.append(f"- Style Elements: {style_count}")
        lines.append(f"- Other Elements: {other_count}")

        return "\n".join(lines)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output"""
        elements = analysis_result.get("elements", [])
        return self.format(elements)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output"""
        elements = analysis_result.get("elements", [])

        if output_format == "json":
            formatter = HtmlJsonFormatter()
            return formatter.format(elements)
        else:
            return self.format(elements)

    def format_analysis_result(
        self, analysis_result: Any, table_type: str = "full"
    ) -> str:
        """Format AnalysisResult directly for HTML files."""
        # Extract elements from AnalysisResult object
        if hasattr(analysis_result, "elements"):
            elements = analysis_result.elements
        else:
            elements = []

        if table_type == "compact":
            formatter: IFormatter = HtmlCompactFormatter()
            return formatter.format(elements)
        elif table_type == "json":
            formatter = HtmlJsonFormatter()
            return formatter.format(elements)
        elif table_type == "csv":
            formatter = HtmlCsvFormatter()
            return formatter.format(elements)
        else:
            # Default to full format (including "html" and "full")
            return self.format(elements)

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output"""
        elements = analysis_result.get("elements", [])
        file_path = analysis_result.get("file_path", "")

        if table_type == "compact":
            compact_formatter = HtmlCompactFormatter()
            return compact_formatter.format(elements, file_path=file_path)
        elif table_type == "json":
            json_formatter = HtmlJsonFormatter()
            return json_formatter.format(elements)
        else:
            # Default to full format (including "html" and "full")
            return self.format(elements)

    def _format_markup_elements(self, elements: list[MarkupElement]) -> list[str]:
        """Format MarkupElement list with hierarchy"""
        return format_markup_elements(elements)

    def _format_element_tree(self, element: MarkupElement, depth: int) -> list[str]:
        """Format element tree hierarchy"""
        return format_element_tree(element, depth)

    def _format_style_elements(self, elements: list[StyleElement]) -> list[str]:
        """Format StyleElement list"""
        return format_style_elements(elements)

    def _format_other_elements(self, elements: list) -> list[str]:
        """Format other code elements"""
        return format_other_elements(elements)

    def _dict_to_markup_element(self, data: dict) -> Any:
        """Convert dictionary to MarkupElement-like object"""

        # Create a mock MarkupElement-like object
        class MockMarkupElement:
            def __init__(self, data: dict[str, Any]) -> None:
                self.name = data.get("name", "unknown")
                self.tag_name = data.get("tag_name", data.get("name", "unknown"))
                self.element_class = data.get("element_class", "unknown")
                self.start_line = data.get("start_line", 0)
                self.end_line = data.get("end_line", 0)
                self.attributes = data.get("attributes", {})
                self.children: list[MockMarkupElement] = []
                self.parent = None
                self.language = data.get("language", "html")

        return MockMarkupElement(data)

    def _dict_to_style_element(self, data: dict) -> Any:
        """Convert dictionary to StyleElement-like object"""

        # Create a mock StyleElement-like object
        class MockStyleElement:
            def __init__(self, data: dict[str, Any]) -> None:
                self.name = data.get("name", "unknown")
                self.selector = data.get("selector", data.get("name", "unknown"))
                self.element_class = data.get("element_class", "unknown")
                self.start_line = data.get("start_line", 0)
                self.end_line = data.get("end_line", 0)
                self.properties = data.get("properties", {})
                self.language = data.get("language", "css")

        return MockStyleElement(data)

    def _element_to_dict(self, element: CodeElement) -> dict[str, Any]:
        """Convert generic CodeElement to dictionary"""
        return element_to_dict(element)


class HtmlJsonFormatter(IFormatter):
    """JSON formatter specifically for HTML elements"""

    @staticmethod
    def get_format_name() -> str:
        return "html_json"

    def format(self, elements: list[CodeElement]) -> str:
        """Format HTML elements as JSON with hierarchy"""
        result = build_html_json_result(
            elements,
            self._markup_to_dict,
            self._style_to_dict,
            self._element_to_dict,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    def _markup_to_dict(self, element: MarkupElement) -> dict[str, Any]:
        """Convert MarkupElement to dictionary"""
        return {
            "name": element.name,
            "tag_name": element.tag_name,
            "element_class": element.element_class,
            "start_line": element.start_line,
            "end_line": element.end_line,
            "attributes": element.attributes,
            "children_count": len(element.children),
            "children": [self._markup_to_dict(child) for child in element.children],
            "language": element.language,
        }

    def _style_to_dict(self, element: StyleElement) -> dict[str, Any]:
        """Convert StyleElement to dictionary"""
        return {
            "name": element.name,
            "selector": element.selector,
            "element_class": element.element_class,
            "start_line": element.start_line,
            "end_line": element.end_line,
            "properties": element.properties,
            "language": element.language,
        }

    def _element_to_dict(self, element: CodeElement) -> dict[str, Any]:
        """Convert generic CodeElement to dictionary"""
        return {
            "name": element.name,
            "type": getattr(element, "element_type", "unknown"),
            "start_line": element.start_line,
            "end_line": element.end_line,
            "language": element.language,
        }


class HtmlCompactFormatter(IFormatter):
    """Compact formatter for HTML elements"""

    @staticmethod
    def get_format_name() -> str:
        return "html_compact"

    def format(self, elements: list[CodeElement], file_path: str = "") -> str:
        """Format HTML elements in compact table format"""
        return format_compact_html(elements, file_path)


class HtmlCsvFormatter(IFormatter):
    """CSV formatter for HTML elements"""

    @staticmethod
    def get_format_name() -> str:
        return "html_csv"

    def format(self, elements: list[CodeElement]) -> str:
        """Format HTML elements as CSV"""
        return format_html_csv(elements)


# HTML formatters are registered via formatter_registry.py
# to avoid duplicate registration warnings
