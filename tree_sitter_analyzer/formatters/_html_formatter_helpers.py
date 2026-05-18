"""Shared helpers for HTML formatter output."""

from typing import Any

from ..models import CodeElement, MarkupElement, StyleElement


def format_markup_elements(elements: list[MarkupElement]) -> list[str]:
    """Format MarkupElement list with hierarchy."""
    lines = ["## HTML Elements", ""]
    element_groups = _group_by_element_class(elements)

    for element_class, group_elements in element_groups.items():
        lines.extend(_markup_group_lines(element_class, group_elements))

    root_elements = [element for element in elements if element.parent is None]
    if root_elements and len(root_elements) < len(elements):
        lines.extend(["### Element Hierarchy", ""])
        for root in root_elements:
            lines.extend(format_element_tree(root, 0))
        lines.append("")

    return lines


def format_element_tree(element: MarkupElement, depth: int) -> list[str]:
    """Format element tree hierarchy."""
    indent = "  " * depth
    tag_name = element.tag_name or "unknown"
    attrs_info = _key_attribute_summary(element.attributes or {})
    lines = [
        f"{indent}- `{tag_name}`{attrs_info} [{element.start_line}-{element.end_line}]"
    ]

    for child in element.children:
        lines.extend(format_element_tree(child, depth + 1))

    return lines


def format_style_elements(elements: list[StyleElement]) -> list[str]:
    """Format StyleElement list."""
    lines = ["## CSS Rules", ""]
    element_groups = _group_by_element_class(elements)

    for element_class, group_elements in element_groups.items():
        lines.extend(_style_group_lines(element_class, group_elements))

    return lines


def format_other_elements(elements: list[Any]) -> list[str]:
    """Format non-HTML/CSS elements."""
    lines = [
        "## Other Elements",
        "",
        "| Type | Name | Lines | Language |",
        "|------|------|-------|----------|",
    ]

    for element in elements:
        values = _other_element_values(element)
        lines.append(
            f"| {values['type']} | {values['name']} | "
            f"{values['start_line']}-{values['end_line']} | {values['language']} |"
        )

    lines.append("")
    return lines


def element_to_dict(element: CodeElement) -> dict[str, Any]:
    """Convert generic CodeElement to dictionary."""
    return {
        "name": element.name,
        "type": getattr(element, "element_type", "unknown"),
        "start_line": element.start_line,
        "end_line": element.end_line,
        "language": element.language,
    }


def _group_by_element_class(elements: list[Any]) -> dict[str, list[Any]]:
    element_groups: dict[str, list[Any]] = {}
    for element in elements:
        element_class = element.element_class or "unknown"
        element_groups.setdefault(element_class, []).append(element)
    return element_groups


def _markup_group_lines(element_class: str, elements: list[MarkupElement]) -> list[str]:
    lines = [
        f"### {element_class.title()} Elements ({len(elements)})",
        "",
        "| Tag | Name | Lines | Attributes | Children |",
        "|-----|------|-------|------------|----------|",
    ]
    for element in elements:
        lines.append(_markup_table_row(element))
    lines.append("")
    return lines


def _markup_table_row(element: MarkupElement) -> str:
    tag_name = element.tag_name or "unknown"
    name = element.name or tag_name
    lines_str = f"{element.start_line}-{element.end_line}"
    attrs_str = _markup_attributes_summary(element.attributes or {})
    children_count = len(element.children)
    return f"| `{tag_name}` | {name} | {lines_str} | {attrs_str} | {children_count} |"


def _markup_attributes_summary(attributes: dict[str, Any]) -> str:
    attrs = []
    for key, value in attributes.items():
        if value:
            attrs.append(f'{key}="{value}"')
        else:
            attrs.append(key)
    attrs_str = ", ".join(attrs) if attrs else "-"
    if len(attrs_str) > 30:
        return attrs_str[:27] + "..."
    return attrs_str


def _key_attribute_summary(attributes: dict[str, Any]) -> str:
    key_attrs = []
    for key, value in attributes.items():
        if key in ["id", "class", "name"]:
            key_attrs.append(f'{key}="{value}"' if value else key)
    if not key_attrs:
        return ""
    return f" ({', '.join(key_attrs)})"


def _style_group_lines(element_class: str, elements: list[StyleElement]) -> list[str]:
    lines = [
        f"### {element_class.title()} Rules ({len(elements)})",
        "",
        "| Selector | Properties | Lines |",
        "|----------|------------|-------|",
    ]
    for element in elements:
        lines.append(_style_table_row(element))
    lines.append("")
    return lines


def _style_table_row(element: StyleElement) -> str:
    selector = element.selector or element.name
    lines_str = f"{element.start_line}-{element.end_line}"
    props_str = _style_properties_summary(element.properties or {})
    return f"| `{selector}` | {props_str} | {lines_str} |"


def _style_properties_summary(properties: dict[str, Any]) -> str:
    props = [f"{key}: {value}" for key, value in properties.items()]
    props_str = "; ".join(props) if props else "-"
    if len(props_str) > 40:
        return props_str[:37] + "..."
    return props_str


def _other_element_values(element: Any) -> dict[str, Any]:
    if isinstance(element, dict):
        return {
            "type": element.get("element_type", element.get("type", "unknown")),
            "name": element.get("name", "unknown"),
            "start_line": element.get("start_line", 0),
            "end_line": element.get("end_line", 0),
            "language": element.get("language", "unknown"),
        }
    return {
        "type": getattr(element, "element_type", "unknown"),
        "name": getattr(element, "name", "unknown"),
        "start_line": getattr(element, "start_line", 0),
        "end_line": getattr(element, "end_line", 0),
        "language": getattr(element, "language", "unknown"),
    }
