"""Helpers for compact HTML formatter output."""

from dataclasses import dataclass, field

from ..models import CodeElement, MarkupElement, StyleElement

IMPORTANT_HTML_TAGS = frozenset(
    {
        "html",
        "head",
        "body",
        "main",
        "header",
        "footer",
        "nav",
        "section",
        "article",
        "aside",
    }
)


@dataclass
class CompactMarkupGroups:
    structure_elements: list[MarkupElement] = field(default_factory=list)
    heading_elements: list[MarkupElement] = field(default_factory=list)
    text_elements: list[MarkupElement] = field(default_factory=list)
    form_elements: list[MarkupElement] = field(default_factory=list)
    media_elements: list[MarkupElement] = field(default_factory=list)
    table_elements: list[MarkupElement] = field(default_factory=list)
    list_elements: list[MarkupElement] = field(default_factory=list)
    metadata_elements: list[MarkupElement] = field(default_factory=list)
    other_elements: list[MarkupElement] = field(default_factory=list)


def format_compact_html(elements: list[CodeElement], file_path: str = "") -> str:
    """Format HTML elements in compact table format."""
    if not elements:
        return "No HTML elements found."

    groups = group_compact_markup_elements(elements)
    lines = [
        f"# {_compact_filename(file_path)}",
        "",
        *_compact_summary_lines(elements, groups),
        *_compact_top_level_lines(compact_important_elements(elements)),
    ]
    return "\n".join(lines)


def group_compact_markup_elements(elements: list[CodeElement]) -> CompactMarkupGroups:
    groups = CompactMarkupGroups()
    for element in elements:
        if isinstance(element, MarkupElement):
            _append_compact_markup_element(groups, element)
    return groups


def compact_important_elements(elements: list[CodeElement]) -> list[MarkupElement]:
    important_elements = []
    for element in elements:
        if isinstance(element, MarkupElement) and _is_compact_important_element(
            element
        ):
            important_elements.append(element)
    return important_elements


def _compact_filename(file_path: str) -> str:
    filename = "comprehensive_sample"
    if file_path:
        filename = file_path.split("/")[-1].split("\\")[-1]
        if filename.endswith(".html") or filename.endswith(".htm"):
            filename = filename.rsplit(".", 1)[0]
    return filename


def _append_compact_markup_element(
    groups: CompactMarkupGroups,
    element: MarkupElement,
) -> None:
    target = {
        "structure": groups.structure_elements,
        "heading": groups.heading_elements,
        "text": groups.text_elements,
        "form": groups.form_elements,
        "media": groups.media_elements,
        "table": groups.table_elements,
        "list": groups.list_elements,
        "metadata": groups.metadata_elements,
    }.get(element.element_class or "other", groups.other_elements)
    target.append(element)


def _compact_summary_lines(
    elements: list[CodeElement],
    groups: CompactMarkupGroups,
) -> list[str]:
    style_count = sum(1 for element in elements if isinstance(element, StyleElement))
    lines = [
        "## Summary",
        "",
        "| Element Type | Count |",
        "|--------------|-------|",
        f"| Structure | {len(groups.structure_elements)} |",
        f"| Headings | {len(groups.heading_elements)} |",
        f"| Text | {len(groups.text_elements)} |",
        f"| Forms | {len(groups.form_elements)} |",
        f"| Media | {len(groups.media_elements)} |",
        f"| Tables | {len(groups.table_elements)} |",
        f"| Lists | {len(groups.list_elements)} |",
        f"| Metadata | {len(groups.metadata_elements)} |",
    ]
    if groups.other_elements:
        lines.append(f"| Other | {len(groups.other_elements)} |")
    if style_count > 0:
        lines.append(f"| CSS Rules | {style_count} |")
    lines.extend([f"| **Total** | **{len(elements)}** |", ""])
    return lines


def _compact_top_level_lines(important_elements: list[MarkupElement]) -> list[str]:
    lines = [
        "## Top-Level Elements",
        "",
        "| Tag | ID/Class | Lines | Children |",
        "|-----|----------|-------|----------|",
    ]
    for element in important_elements[:20]:
        lines.append(_compact_element_row(element))
    if len(important_elements) > 20:
        lines.append(f"| ... | ({len(important_elements) - 20} more) | | |")
    lines.append("")
    return lines


def _compact_element_row(element: MarkupElement) -> str:
    tag = element.tag_name or "unknown"
    lines_str = f"{element.start_line}-{element.end_line}"
    children_count = len(element.children)
    return (
        f"| `{tag}` | {_compact_id_class(element)} | {lines_str} | {children_count} |"
    )


def _compact_id_class(element: MarkupElement) -> str:
    id_class = []
    if element.attributes.get("id"):
        id_class.append(f"#{element.attributes['id']}")
    if element.attributes.get("class"):
        classes = element.attributes["class"].split()[:2]
        id_class.extend([f".{class_name}" for class_name in classes])
    return " ".join(id_class) if id_class else "-"


def _is_compact_important_element(element: MarkupElement) -> bool:
    return element.parent is None or element.tag_name in IMPORTANT_HTML_TAGS
