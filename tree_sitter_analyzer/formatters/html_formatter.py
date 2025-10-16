#!/usr/bin/env python3
"""
HTML Formatter

Specialized formatter for HTML/CSS code elements including MarkupElement and StyleElement.
Provides HTML-specific formatting with element classification and hierarchy display.
"""

import json
from typing import Any

from ..models import CodeElement, MarkupElement, StyleElement
from .base_formatter import BaseFormatter
from .formatter_registry import IFormatter


class HtmlFormatter(BaseFormatter, IFormatter):
    """HTML-specific formatter for MarkupElement and StyleElement"""

    def __init__(self):
        """Initialize HTML formatter"""
        pass

    @staticmethod
    def get_format_name() -> str:
        return "html"

    def format(self, elements: list[CodeElement]) -> str:
        """Format HTML elements with hierarchy and classification"""
        if not elements:
            return "No HTML elements found."

        lines = []
        lines.append("# HTML Structure Analysis")
        lines.append("")

        # Handle both CodeElement objects and dictionaries
        markup_elements = []
        style_elements = []
        other_elements = []

        for e in elements:
            if isinstance(e, MarkupElement):
                markup_elements.append(e)
            elif isinstance(e, StyleElement):
                style_elements.append(e)
            elif isinstance(e, dict):
                # Convert dictionary to appropriate element type based on content
                element_type = e.get("type", e.get("element_type", "unknown"))
                if "tag_name" in e or element_type in ["tag", "element", "markup"]:
                    markup_elements.append(self._dict_to_markup_element(e))
                elif "selector" in e or element_type in ["rule", "style"]:
                    style_elements.append(self._dict_to_style_element(e))
                else:
                    other_elements.append(e)
            else:
                other_elements.append(e)

        # Format markup elements
        if markup_elements:
            lines.extend(self._format_markup_elements(markup_elements))

        # Format style elements
        if style_elements:
            lines.extend(self._format_style_elements(style_elements))

        # Format other elements
        if other_elements:
            lines.extend(self._format_other_elements(other_elements))

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

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output"""
        elements = analysis_result.get("elements", [])

        if table_type == "compact":
            formatter = HtmlCompactFormatter()
            return formatter.format(elements)
        elif table_type == "json":
            formatter = HtmlJsonFormatter()
            return formatter.format(elements)
        else:
            # Default to full format (including "html" and "full")
            return self.format(elements)

    def _format_markup_elements(self, elements: list[MarkupElement]) -> list[str]:
        """Format MarkupElement list with hierarchy"""
        lines = []
        lines.append("## HTML Elements")
        lines.append("")

        # Group by element class
        element_groups = {}
        for element in elements:
            element_class = element.element_class or "unknown"
            if element_class not in element_groups:
                element_groups[element_class] = []
            element_groups[element_class].append(element)

        # Format each group
        for element_class, group_elements in element_groups.items():
            lines.append(
                f"### {element_class.title()} Elements ({len(group_elements)})"
            )
            lines.append("")
            lines.append("| Tag | Name | Lines | Attributes | Children |")
            lines.append("|-----|------|-------|------------|----------|")

            for element in group_elements:
                tag_name = element.tag_name or "unknown"
                name = element.name or tag_name
                lines_str = f"{element.start_line}-{element.end_line}"

                # Format attributes
                attrs = []
                attributes = element.attributes or {}
                for key, value in attributes.items():
                    if value:
                        attrs.append(f'{key}="{value}"')
                    else:
                        attrs.append(key)
                attrs_str = ", ".join(attrs) if attrs else "-"
                if len(attrs_str) > 30:
                    attrs_str = attrs_str[:27] + "..."

                # Count children
                children_count = len(element.children)

                lines.append(
                    f"| `{tag_name}` | {name} | {lines_str} | {attrs_str} | {children_count} |"
                )

            lines.append("")

        # Show hierarchy for root elements
        root_elements = [e for e in elements if e.parent is None]
        if root_elements and len(root_elements) < len(elements):
            lines.append("### Element Hierarchy")
            lines.append("")
            for root in root_elements:
                lines.extend(self._format_element_tree(root, 0))
            lines.append("")

        return lines

    def _format_element_tree(self, element: MarkupElement, depth: int) -> list[str]:
        """Format element tree hierarchy"""
        lines = []
        indent = "  " * depth
        tag_name = element.tag_name or "unknown"

        # Format element info
        attrs_info = ""
        attributes = element.attributes or {}
        if attributes:
            key_attrs = []
            for key, value in attributes.items():
                if key in ["id", "class", "name"]:
                    key_attrs.append(f'{key}="{value}"' if value else key)
            if key_attrs:
                attrs_info = f" ({', '.join(key_attrs)})"

        lines.append(
            f"{indent}- `{tag_name}`{attrs_info} [{element.start_line}-{element.end_line}]"
        )

        # Format children
        for child in element.children:
            lines.extend(self._format_element_tree(child, depth + 1))

        return lines

    def _format_style_elements(self, elements: list[StyleElement]) -> list[str]:
        """Format StyleElement list"""
        lines = []
        lines.append("## CSS Rules")
        lines.append("")

        # Group by element class
        element_groups = {}
        for element in elements:
            element_class = element.element_class or "unknown"
            if element_class not in element_groups:
                element_groups[element_class] = []
            element_groups[element_class].append(element)

        # Format each group
        for element_class, group_elements in element_groups.items():
            lines.append(f"### {element_class.title()} Rules ({len(group_elements)})")
            lines.append("")
            lines.append("| Selector | Properties | Lines |")
            lines.append("|----------|------------|-------|")

            for element in group_elements:
                selector = element.selector or element.name
                lines_str = f"{element.start_line}-{element.end_line}"

                # Format properties
                props = []
                properties = element.properties or {}
                for key, value in properties.items():
                    props.append(f"{key}: {value}")
                props_str = "; ".join(props) if props else "-"
                if len(props_str) > 40:
                    props_str = props_str[:37] + "..."

                lines.append(f"| `{selector}` | {props_str} | {lines_str} |")

            lines.append("")

        return lines

    def _format_other_elements(self, elements: list) -> list[str]:
        """Format other code elements"""
        lines = []
        lines.append("## Other Elements")
        lines.append("")
        lines.append("| Type | Name | Lines | Language |")
        lines.append("|------|------|-------|----------|")

        for element in elements:
            if isinstance(element, dict):
                element_type = element.get(
                    "element_type", element.get("type", "unknown")
                )
                name = element.get("name", "unknown")
                start_line = element.get("start_line", 0)
                end_line = element.get("end_line", 0)
                language = element.get("language", "unknown")
            else:
                element_type = getattr(element, "element_type", "unknown")
                name = getattr(element, "name", "unknown")
                start_line = getattr(element, "start_line", 0)
                end_line = getattr(element, "end_line", 0)
                language = getattr(element, "language", "unknown")

            lines_str = f"{start_line}-{end_line}"
            lines.append(f"| {element_type} | {name} | {lines_str} | {language} |")

        lines.append("")
        return lines

    def _dict_to_markup_element(self, data: dict):
        """Convert dictionary to MarkupElement-like object"""

        # Create a mock MarkupElement-like object
        class MockMarkupElement:
            def __init__(self, data):
                self.name = data.get("name", "unknown")
                self.tag_name = data.get("tag_name", data.get("name", "unknown"))
                self.element_class = data.get("element_class", "unknown")
                self.start_line = data.get("start_line", 0)
                self.end_line = data.get("end_line", 0)
                self.attributes = data.get("attributes", {})
                self.children = []
                self.parent = None
                self.language = data.get("language", "html")

        return MockMarkupElement(data)

    def _dict_to_style_element(self, data: dict):
        """Convert dictionary to StyleElement-like object"""

        # Create a mock StyleElement-like object
        class MockStyleElement:
            def __init__(self, data):
                self.name = data.get("name", "unknown")
                self.selector = data.get("selector", data.get("name", "unknown"))
                self.element_class = data.get("element_class", "unknown")
                self.start_line = data.get("start_line", 0)
                self.end_line = data.get("end_line", 0)
                self.properties = data.get("properties", {})
                self.language = data.get("language", "css")

        return MockStyleElement(data)


class HtmlJsonFormatter(IFormatter):
    """JSON formatter specifically for HTML elements"""

    @staticmethod
    def get_format_name() -> str:
        return "html_json"

    def format(self, elements: list[CodeElement]) -> str:
        """Format HTML elements as JSON with hierarchy"""
        result = {
            "html_analysis": {
                "total_elements": len(elements),
                "markup_elements": [],
                "style_elements": [],
                "other_elements": [],
            }
        }

        for element in elements:
            if isinstance(element, MarkupElement):
                result["html_analysis"]["markup_elements"].append(
                    self._markup_to_dict(element)
                )
            elif isinstance(element, StyleElement):
                result["html_analysis"]["style_elements"].append(
                    self._style_to_dict(element)
                )
            elif isinstance(element, dict):
                # Handle dictionary format
                element_type = element.get(
                    "element_type", element.get("type", "unknown")
                )
                if "tag_name" in element or element_type in [
                    "tag",
                    "element",
                    "markup",
                ]:
                    result["html_analysis"]["markup_elements"].append(element)
                elif "selector" in element or element_type in ["rule", "style"]:
                    result["html_analysis"]["style_elements"].append(element)
                else:
                    result["html_analysis"]["other_elements"].append(element)
            else:
                result["html_analysis"]["other_elements"].append(
                    self._element_to_dict(element)
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

    def format(self, elements: list[CodeElement]) -> str:
        """Format HTML elements in compact format"""
        if not elements:
            return "No HTML elements found."

        lines = []
        lines.append("HTML ELEMENTS")
        lines.append("-" * 20)

        markup_count = sum(1 for e in elements if isinstance(e, MarkupElement))
        style_count = sum(1 for e in elements if isinstance(e, StyleElement))
        other_count = len(elements) - markup_count - style_count

        lines.append(f"Total: {len(elements)} elements")
        lines.append(f"  Markup: {markup_count}")
        lines.append(f"  Style: {style_count}")
        lines.append(f"  Other: {other_count}")
        lines.append("")

        for element in elements:
            if isinstance(element, MarkupElement):
                symbol = "🏷️"
                info = f"<{element.tag_name}>"
                if element.attributes.get("id"):
                    info += f" #{element.attributes['id']}"
                if element.attributes.get("class"):
                    info += f" .{element.attributes['class']}"
                name = element.name
                start_line = element.start_line
                end_line = element.end_line
            elif isinstance(element, StyleElement):
                symbol = "🎨"
                info = element.selector
                name = element.name
                start_line = element.start_line
                end_line = element.end_line
            elif isinstance(element, dict):
                # Handle dictionary format
                element_type = element.get(
                    "element_type", element.get("type", "unknown")
                )
                name = element.get("name", "unknown")
                start_line = element.get("start_line", 0)
                end_line = element.get("end_line", 0)

                if "tag_name" in element or element_type in [
                    "tag",
                    "element",
                    "markup",
                ]:
                    symbol = "🏷️"
                    tag_name = element.get("tag_name", name)
                    info = f"<{tag_name}>"
                    attributes = element.get("attributes", {})
                    if attributes.get("id"):
                        info += f" #{attributes['id']}"
                    if attributes.get("class"):
                        info += f" .{attributes['class']}"
                elif "selector" in element or element_type in ["rule", "style"]:
                    symbol = "🎨"
                    info = element.get("selector", name)
                else:
                    symbol = "📄"
                    info = element_type
            else:
                symbol = "📄"
                info = getattr(element, "element_type", "unknown")
                name = getattr(element, "name", "unknown")
                start_line = getattr(element, "start_line", 0)
                end_line = getattr(element, "end_line", 0)

            lines.append(f"{symbol} {name} {info} [{start_line}-{end_line}]")

        return "\n".join(lines)


# HTML formatters are registered via formatter_registry.py
# to avoid duplicate registration warnings
