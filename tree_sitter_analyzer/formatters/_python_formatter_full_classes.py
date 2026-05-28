"""Class sections for Python full formatter output."""

from typing import Any


def append_classes(
    lines: list[str], data: dict[str, Any], classes: list[dict[str, Any]]
) -> None:
    if not classes:
        return

    if len(classes) == 1:
        _append_single_class_info(lines, data, classes[0])
    else:
        _append_classes_overview(lines, data, classes)


def _append_single_class_info(
    lines: list[str], data: dict[str, Any], class_info: dict[str, Any] | None
) -> None:
    if class_info is None:
        return

    lines.append("## Class Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.extend(_single_class_info_rows(data, class_info))
    lines.append("")


def _single_class_info_rows(
    data: dict[str, Any], class_info: dict[str, Any]
) -> list[str]:
    class_type = str(class_info.get("type", "class"))
    visibility = str(class_info.get("visibility", "public"))
    stats = data.get("statistics", {})
    return [
        f"| Type | {class_type} |",
        f"| Visibility | {visibility} |",
        f"| Lines | {_lines_text(class_info)} |",
        f"| Total Methods | {stats.get('method_count', 0)} |",
        f"| Total Fields | {stats.get('field_count', 0)} |",
    ]


def _append_classes_overview(
    lines: list[str], data: dict[str, Any], classes: list[dict[str, Any]]
) -> None:
    lines.append("## Classes Overview")
    lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
    lines.append("|-------|------|------------|-------|---------|--------|")

    for class_info in classes:
        if class_info is None:
            continue
        lines.append(_class_overview_row(data, class_info))
    lines.append("")


def _class_overview_row(data: dict[str, Any], class_info: dict[str, Any]) -> str:
    name = str(class_info.get("name", "Unknown"))
    class_type = str(class_info.get("type", "class"))
    visibility = str(class_info.get("visibility", "public"))
    line_range = class_info.get("line_range") or {}
    class_methods = _items_in_range(data.get("methods", []), line_range)
    class_fields = _items_in_range(data.get("fields", []), line_range)
    return (
        f"| {name} | {class_type} | {visibility} | {_lines_text(class_info)} | "
        f"{len(class_methods)} | {len(class_fields)} |"
    )


def append_class_sections(
    lines: list[str],
    formatter: Any,
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
) -> None:
    for class_info in classes:
        if class_info is None:
            continue

        line_range = class_info.get("line_range") or {}
        class_methods = _items_in_range(methods, line_range)
        if class_methods:
            lines.append(
                f"## {class_info.get('name', 'Unknown')} ({_lines_text(class_info)})"
            )
            append_method_rows(lines, formatter, class_methods)


def append_method_rows(
    lines: list[str], formatter: Any, methods: list[dict[str, Any]]
) -> None:
    lines.append("### Public Methods")
    lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
    lines.append("|--------|-----------|-----|-------|----|----| ")

    for method in methods:
        lines.append(formatter.format_class_method_row(method))
    lines.append("")


def _items_in_range(
    items: list[dict[str, Any]], line_range: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if line_range.get("start", 0)
        <= (item.get("line_range") or {}).get("start", 0)
        <= line_range.get("end", 0)
    ]


def _lines_text(element: dict[str, Any]) -> str:
    line_range = element.get("line_range") or {}
    return f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
