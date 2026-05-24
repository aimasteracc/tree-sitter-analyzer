"""Full table rendering for the Java formatter."""

from typing import Any


class JavaTableFormatterFullMixin:
    """Full-format rendering helpers."""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Java - matches golden master format"""
        lines: list[str] = []
        package_name = (data.get("package") or {}).get("name", "")
        classes = data.get("classes", [])

        lines.append(f"# {_java_title(self, data, package_name, classes)}")
        lines.append("")
        _append_package(lines, package_name)
        _append_imports(lines, data.get("imports", []))

        top_level_classes = [
            cls for cls in classes if not self._is_inner_class(cls, classes)
        ]
        if len(top_level_classes) == 1:
            _append_single_class(lines, top_level_classes[0], data, package_name, self)
        else:
            _append_multi_class(lines, classes, data, self)

        _trim_trailing_blank_lines(lines)
        return "\n".join(lines)


def _java_title(
    formatter: Any,
    data: dict[str, Any],
    package_name: str,
    classes: list[dict[str, Any]],
) -> str:
    file_path = data.get("file_path", "")
    if file_path:
        file_name = _java_file_stem(file_path)
        return f"{package_name}.{file_name}" if package_name else file_name

    if not classes:
        return "Unknown"

    main_classes = [
        cls for cls in classes if not formatter._is_inner_class(cls, classes)
    ]
    main_class = main_classes[0] if main_classes else classes[0]
    class_name = main_class.get("name", "Unknown")
    return f"{package_name}.{class_name}" if package_name else str(class_name)


def _java_file_stem(file_path: str) -> str:
    file_name = file_path.split("/")[-1].split("\\")[-1]
    if file_name.endswith(".java"):
        return file_name[:-5]
    return file_name


def _append_package(lines: list[str], package_name: str) -> None:
    if not package_name:
        return

    lines.append("## Package")
    lines.append(f"`{package_name}`")
    lines.append("")


def _append_imports(lines: list[str], imports: list[dict[str, Any]]) -> None:
    if not imports:
        return

    lines.append("## Imports")
    lines.append("```java")
    for imp in imports:
        lines.append(str(imp.get("statement", "")))
    lines.append("```")
    lines.append("")


def _append_single_class(
    lines: list[str],
    single_class: dict[str, Any],
    data: dict[str, Any],
    package_name: str,
    formatter: Any,
) -> None:
    stats = data.get("statistics") or {}
    line_range = single_class.get("line_range", {})

    lines.append("## Class Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Package | {package_name} |")
    lines.append(f"| Type | {single_class.get('type', 'class')} |")
    lines.append(f"| Visibility | {single_class.get('visibility', 'package')} |")
    lines.append(f"| Lines | {line_range.get('start', 0)}-{line_range.get('end', 0)} |")
    lines.append(f"| Total Methods | {stats.get('method_count', 0)} |")
    lines.append(f"| Total Fields | {stats.get('field_count', 0)} |")
    lines.append("")
    lines.extend(
        formatter._format_class_section(single_class, data, data.get("classes", []))
    )


def _append_multi_class(
    lines: list[str],
    classes: list[dict[str, Any]],
    data: dict[str, Any],
    formatter: Any,
) -> None:
    if classes:
        lines.append("## Classes Overview")
        lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
        lines.append("|-------|------|------------|-------|---------|--------|")
        for class_info in classes:
            lines.append(_class_overview_row(class_info, data, classes, formatter))
        lines.append("")

    for class_info in classes:
        lines.extend(formatter._format_class_section(class_info, data, classes))


def _class_overview_row(
    class_info: dict[str, Any],
    data: dict[str, Any],
    classes: list[dict[str, Any]],
    formatter: Any,
) -> str:
    name = str(class_info.get("name", "Unknown"))
    class_type = str(class_info.get("type", "class"))
    visibility = str(class_info.get("visibility", "package"))
    line_range = class_info.get("line_range", {})
    lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    class_methods = formatter._get_class_methods(data.get("methods", []), line_range)
    class_fields = formatter._get_class_fields(data.get("fields", []), line_range)
    class_methods, class_fields = _exclude_inner_members(
        formatter, class_info, classes, class_methods, class_fields
    )

    return (
        f"| {name} | {class_type} | {visibility} | "
        f"{lines_str} | {len(class_methods)} | {len(class_fields)} |"
    )


def _exclude_inner_members(
    formatter: Any,
    class_info: dict[str, Any],
    classes: list[dict[str, Any]],
    class_methods: list[dict[str, Any]],
    class_fields: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    for inner in formatter._get_inner_classes(class_info, classes):
        inner_range = inner.get("line_range", {})
        class_methods = [
            method
            for method in class_methods
            if not formatter._is_in_range(method.get("line_range", {}), inner_range)
        ]
        class_fields = [
            field
            for field in class_fields
            if not formatter._is_in_range(field.get("line_range", {}), inner_range)
        ]
    return class_methods, class_fields


def _trim_trailing_blank_lines(lines: list[str]) -> None:
    while lines and lines[-1] == "":
        lines.pop()
