"""Class section rendering for the Java formatter."""

from typing import Any, NamedTuple


class MethodSection(NamedTuple):
    """Rendered method section metadata."""

    title: str
    header: str
    separator: str
    methods: list[dict[str, Any]]


class JavaTableFormatterClassMixin:
    """Class, member, and range helpers."""

    def _format_class_section(
        self,
        class_info: dict[str, Any],
        data: dict[str, Any],
        all_classes: list[dict[str, Any]],
    ) -> list[str]:
        """Format a single class section with its fields and methods"""
        lines: list[str] = []
        name = str(class_info.get("name", "Unknown"))
        line_range = class_info.get("line_range", {})
        start = line_range.get("start", 0)
        end = line_range.get("end", 0)
        class_methods = get_class_methods(data.get("methods", []), line_range)
        class_fields = get_class_fields(data.get("fields", []), line_range)
        inner_classes = get_inner_classes(class_info, all_classes)
        class_methods, class_fields = _exclude_inner_members(
            self, inner_classes, class_methods, class_fields
        )

        lines.append(f"## {name} ({start}-{end})")
        _append_fields(lines, class_fields, self)
        _append_method_group(
            lines,
            MethodSection(
                "### Constructors",
                "| Constructor | Signature | Vis | Lines | Cx | Doc |",
                "|-------------|-----------|-----|-------|----|----|",
                _constructor_methods(class_methods),
            ),
            self._format_method_row,
        )
        _append_visibility_groups(
            lines, _non_constructor_methods(class_methods), self._format_method_row
        )

        for inner_cls in inner_classes:
            lines.extend(self._format_class_section(inner_cls, data, all_classes))

        return lines

    def _format_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row for Java (golden master format)"""
        name = str(method.get("name", ""))
        signature = self._create_full_signature(method)
        visibility = self.convert_visibility(str(method.get("visibility", "")))
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = method.get("complexity_score", 1)
        doc = _clean_doc_cell(str(method.get("javadoc", "")) or "-")

        return (
            f"| {name} | {signature} | {visibility} | {lines_str} | "
            f"{complexity} | {doc} |"
        )


def _append_fields(
    lines: list[str], class_fields: list[dict[str, Any]], formatter: Any
) -> None:
    if not class_fields:
        return

    lines.append("### Fields")
    lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
    lines.append("|------|------|-----|-----------|------|-----|")
    for field in class_fields:
        lines.append(_field_row(field, formatter))
    lines.append("")


def _constructor_methods(methods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [method for method in methods if method.get("is_constructor", False)]


def _non_constructor_methods(methods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [method for method in methods if not method.get("is_constructor", False)]


def _field_row(field: dict[str, Any], formatter: Any) -> str:
    field_name = str(field.get("name", ""))
    field_type = str(field.get("type", ""))
    visibility = formatter.convert_visibility(str(field.get("visibility", "")))
    modifiers = ",".join([str(modifier) for modifier in field.get("modifiers", [])])
    line = field.get("line_range", {}).get("start", 0)
    doc = _clean_doc_cell(str(field.get("javadoc", "")) or "-")
    return (
        f"| {field_name} | {field_type} | {visibility} | {modifiers} | {line} | {doc} |"
    )


def _append_visibility_groups(
    lines: list[str],
    methods: list[dict[str, Any]],
    row_formatter: Any,
) -> None:
    for title, visibility_values in _method_groups():
        group = [
            method
            for method in methods
            if str(method.get("visibility", "")) in visibility_values
        ]
        _append_method_group(
            lines,
            MethodSection(
                title,
                "| Method | Signature | Vis | Lines | Cx | Doc |",
                "|--------|-----------|-----|-------|----|----|",
                group,
            ),
            row_formatter,
        )


def _method_groups() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        ("### Public Methods", ("public",)),
        ("### Protected Methods", ("protected",)),
        ("### Package Methods", ("package", "default", "")),
        ("### Private Methods", ("private",)),
    )


def _append_method_group(
    lines: list[str],
    section: MethodSection,
    row_formatter: Any,
) -> None:
    if not section.methods:
        return

    lines.append(section.title)
    lines.append(section.header)
    lines.append(section.separator)
    for method in section.methods:
        lines.append(row_formatter(method))
    lines.append("")


def _exclude_inner_members(
    _formatter: Any,
    inner_classes: list[dict[str, Any]],
    class_methods: list[dict[str, Any]],
    class_fields: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    for inner in inner_classes:
        inner_range = inner.get("line_range", {})
        class_methods = [
            method
            for method in class_methods
            if not is_in_range(method.get("line_range", {}), inner_range)
        ]
        class_fields = [
            field
            for field in class_fields
            if not is_in_range(field.get("line_range", {}), inner_range)
        ]
    return class_methods, class_fields


def _members_in_range(
    members: list[dict[str, Any]], class_range: dict[str, Any]
) -> list[dict[str, Any]]:
    start = class_range.get("start", 0)
    end = class_range.get("end", 0)
    return [
        member
        for member in members
        if start <= member.get("line_range", {}).get("start", 0) <= end
    ]


def get_class_methods(
    methods: list[dict[str, Any]], class_range: dict[str, Any]
) -> list[dict[str, Any]]:
    """Get methods that belong to a class based on line range."""
    return _members_in_range(methods, class_range)


def get_class_fields(
    fields: list[dict[str, Any]], class_range: dict[str, Any]
) -> list[dict[str, Any]]:
    """Get fields that belong to a class based on line range."""
    return _members_in_range(fields, class_range)


def get_inner_classes(
    parent_class: dict[str, Any], all_classes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Get inner classes of a parent class."""
    parent_range = parent_class.get("line_range", {})
    parent_start = parent_range.get("start", 0)
    parent_end = parent_range.get("end", 0)
    return [
        cls
        for cls in all_classes
        if cls is not parent_class and _is_contained(cls, parent_start, parent_end)
    ]


def is_inner_class(
    class_info: dict[str, Any], all_classes: list[dict[str, Any]]
) -> bool:
    """Check if a class is an inner class of another class."""
    class_range = class_info.get("line_range", {})
    class_start = class_range.get("start", 0)
    class_end = class_range.get("end", 0)
    return any(
        parent is not class_info and _range_contains(parent, class_start, class_end)
        for parent in all_classes
    )


def is_in_range(item_range: dict[str, Any], container_range: dict[str, Any]) -> bool:
    """Check if an item's line range is within a container's range."""
    item_start = int(item_range.get("start", 0))
    container_start = int(container_range.get("start", 0))
    container_end = int(container_range.get("end", 0))
    return container_start <= item_start <= container_end


def _is_contained(
    class_info: dict[str, Any], parent_start: int, parent_end: int
) -> bool:
    class_range = class_info.get("line_range", {})
    return (
        parent_start < class_range.get("start", 0)
        and class_range.get("end", 0) < parent_end
    )


def _range_contains(parent: dict[str, Any], class_start: int, class_end: int) -> bool:
    parent_range = parent.get("line_range", {})
    return parent_range.get("start", 0) < class_start and class_end < parent_range.get(
        "end", 0
    )


def _clean_doc_cell(doc: str) -> str:
    doc = doc.replace("\n", " ").replace("|", "\\|")[:50]
    if not doc or doc == "None":
        return "-"
    return doc


JavaTableFormatterClassMixin._get_class_methods = staticmethod(get_class_methods)  # type: ignore[attr-defined]  # noqa: SLF001
JavaTableFormatterClassMixin._get_class_fields = staticmethod(get_class_fields)  # type: ignore[attr-defined]  # noqa: SLF001
JavaTableFormatterClassMixin._get_inner_classes = staticmethod(get_inner_classes)  # type: ignore[attr-defined]  # noqa: SLF001
JavaTableFormatterClassMixin._is_inner_class = staticmethod(is_inner_class)  # type: ignore[attr-defined]  # noqa: SLF001
JavaTableFormatterClassMixin._is_in_range = staticmethod(is_in_range)  # type: ignore[attr-defined]  # noqa: SLF001
# Public alias (no leading underscore) for companion module access
JavaTableFormatterClassMixin.format_class_section = (
    JavaTableFormatterClassMixin._format_class_section  # noqa: SLF001
)  # type: ignore[attr-defined]
