#!/usr/bin/env python3
"""
HTML Formatter

Specialized formatter for HTML/CSS code elements including MarkupElement and StyleElement.
Provides HTML-specific formatting with element classification and hierarchy display.
"""

import json
from typing import Any

from ..models import CodeElement, MarkupElement, StyleElement
from .formatter_registry import IFormatter


class HtmlFormatter(IFormatter):
    """HTML-specific formatter for MarkupElement and StyleElement"""

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

        # Separate MarkupElements and StyleElements
        markup_elements = [e for e in elements if isinstance(e, MarkupElement)]
        style_elements = [e for e in elements if isinstance(e, StyleElement)]
        other_elements = [e for e in elements if not isinstance(e, (MarkupElement, StyleElement))]

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
            lines.append(f"### {element_class.title()} Elements ({len(group_elements)})")
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
                        attrs.append(f"{key}=\"{value}\"")
                    else:
                        attrs.append(key)
                attrs_str = ", ".join(attrs) if attrs else "-"
                if len(attrs_str) > 30:
                    attrs_str = attrs_str[:27] + "..."

                # Count children
                children_count = len(element.children)

                lines.append(f"| `{tag_name}` | {name} | {lines_str} | {attrs_str} | {children_count} |")

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
                    key_attrs.append(f"{key}=\"{value}\"" if value else key)
            if key_attrs:
                attrs_info = f" ({', '.join(key_attrs)})"

        lines.append(f"{indent}- `{tag_name}`{attrs_info} [{element.start_line}-{element.end_line}]")

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

    def _format_other_elements(self, elements: list[CodeElement]) -> list[str]:
        """Format other code elements"""
        lines = []
        lines.append("## Other Elements")
        lines.append("")
        lines.append("| Type | Name | Lines | Language |")
        lines.append("|------|------|-------|----------|")

        for element in elements:
            element_type = getattr(element, "element_type", "unknown")
            name = element.name
            lines_str = f"{element.start_line}-{element.end_line}"
            language = element.language

            lines.append(f"| {element_type} | {name} | {lines_str} | {language} |")

        lines.append("")
        return lines


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
                "other_elements": []
            }
        }

        for element in elements:
            if isinstance(element, MarkupElement):
                result["html_analysis"]["markup_elements"].append(self._markup_to_dict(element))
            elif isinstance(element, StyleElement):
                result["html_analysis"]["style_elements"].append(self._style_to_dict(element))
            else:
                result["html_analysis"]["other_elements"].append(self._element_to_dict(element))

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
            "language": element.language
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
            "language": element.language
        }

    def _element_to_dict(self, element: CodeElement) -> dict[str, Any]:
        """Convert generic CodeElement to dictionary"""
        return {
            "name": element.name,
            "type": getattr(element, "element_type", "unknown"),
            "start_line": element.start_line,
            "end_line": element.end_line,
            "language": element.language
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
            elif isinstance(element, StyleElement):
                symbol = "🎨"
                info = element.selector
            else:
                symbol = "📄"
                info = getattr(element, "element_type", "unknown")

            lines.append(f"{symbol} {element.name} {info} [{element.start_line}-{element.end_line}]")

        return "\n".join(lines)


# Register HTML formatters
def register_html_formatters() -> None:
    """Register HTML-specific formatters"""
    from .formatter_registry import FormatterRegistry
    
    FormatterRegistry.register_formatter(HtmlFormatter)
    FormatterRegistry.register_formatter(HtmlJsonFormatter)
    FormatterRegistry.register_formatter(HtmlCompactFormatter)


# Auto-register when module is imported
register_html_formatters()