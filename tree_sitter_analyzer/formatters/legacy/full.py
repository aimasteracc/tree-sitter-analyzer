"""Full table helpers for the legacy table formatter."""

from __future__ import annotations

from typing import Any


def format_simple_method_row(method: dict[str, Any]) -> str:
    """Format a legacy full-table method row."""
    name = str(method.get("name", ""))
    is_constructor = method.get("is_constructor", False)
    return_type = "-" if is_constructor else str(method.get("return_type", "void"))
    params_str = _simple_parameters(method.get("parameters", []))
    access = str(method.get("visibility", "public"))
    line_num = method.get("line_range", {}).get("start", 0)

    return f"| {name} | {return_type} | {params_str} | {access} | {line_num} |"


def format_simple_field_row(field: dict[str, Any]) -> str:
    """Format a legacy full-table field row."""
    name = str(field.get("name", ""))
    field_type = str(field.get("type", "Object"))
    access = str(field.get("visibility", "private"))

    modifiers = field.get("modifiers", [])
    is_static = "static" in modifiers or field.get("is_static", False)
    is_final = "final" in modifiers or field.get("is_final", False)

    static_str = "true" if is_static else "false"
    final_str = "true" if is_final else "false"
    line_num = field.get("line_range", {}).get("start", 0)

    return (
        f"| {name} | {field_type} | {access} | {static_str} | {final_str} | "
        f"{line_num} |"
    )


def full_table_header(data: dict[str, Any], classes: list[dict[str, Any]]) -> str:
    """Build the legacy full-table header."""
    package_name = (data.get("package") or {}).get("name", "")
    if len(classes) == 1:
        class_name = classes[0].get("name", "Unknown")
        if package_name:
            return f"{package_name}.{class_name}"
        return str(class_name)

    file_path = data.get("file_path", "")
    if file_path and file_path != "Unknown":
        file_name = file_path.split("/")[-1].split("\\")[-1]
        if file_name.endswith(".java"):
            file_name = file_name[:-5]
        elif file_name.endswith(".py"):
            file_name = file_name[:-3]
        elif file_name.endswith(".js"):
            file_name = file_name[:-3]

        if package_name and len(classes) == 0:
            return f"{package_name}.{file_name}"
        return str(file_name)

    if package_name:
        return f"{package_name}.Unknown"
    return "unknown.Unknown"


def append_full_package_section(lines: list[str], package_name: str) -> None:
    """Append the legacy full-table package section."""
    if package_name and package_name != "unknown":
        lines.append("## Package")
        lines.append(f"`{package_name}`")
        lines.append("")


def append_full_imports_section(
    lines: list[str],
    imports: list[dict[str, Any]],
    language: str,
) -> None:
    """Append the legacy full-table imports section."""
    if not imports:
        return

    lines.append("## Imports")
    lines.append(f"```{language}")
    for imp in imports:
        statement = str(imp.get("statement", ""))
        lines.append(statement)
    lines.append("```")
    lines.append("")


def append_full_class_info_section(
    lines: list[str],
    classes: list[dict[str, Any]],
    display_package: str,
) -> None:
    """Append the legacy full-table class info section."""
    lines.append("## Class Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")

    if len(classes) >= 1:
        class_info = classes[0]
        class_name = str(class_info.get("name", "Unknown"))
        lines.append(f"| Name | {class_name} |")
        lines.append(f"| Package | {display_package} |")
        lines.append(f"| Type | {str(class_info.get('type', 'class'))} |")
        lines.append(f"| Access | {str(class_info.get('visibility', 'public'))} |")

        extends = class_info.get("extends")
        if extends:
            lines.append(f"| Extends | {extends} |")

        implements = class_info.get("implements", [])
        if implements:
            lines.append(f"| Implements | {', '.join(implements)} |")
    else:
        lines.append("| Name | Unknown |")
        lines.append(f"| Package | {display_package} |")
        lines.append("| Type | class |")
        lines.append("| Access | public |")

    lines.append("")


def append_multi_class_full_sections(
    lines: list[str],
    data: dict[str, Any],
    classes: list[dict[str, Any]],
    get_class_methods: Any,
    get_class_fields: Any,
) -> None:
    """Append legacy full-table sections for multiple classes."""
    lines.append("## Classes Overview")
    lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
    lines.append("|-------|------|------------|-------|---------|--------|")

    for class_info in classes:
        class_name = str(class_info.get("name", "Unknown"))
        class_type = str(class_info.get("type", "class"))
        visibility = str(class_info.get("visibility", "public"))
        line_range = class_info.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        class_methods = get_class_methods(data, line_range)
        class_fields = get_class_fields(data, line_range)

        lines.append(
            f"| {class_name} | {class_type} | {visibility} | {lines_str} | "
            f"{len(class_methods)} | {len(class_fields)} |"
        )
    lines.append("")

    for class_info in classes:
        class_name = str(class_info.get("name", "Unknown"))
        line_range = class_info.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"

        lines.append(f"## {class_name} ({lines_str})")
        class_methods = get_class_methods(data, line_range)
        if class_methods:
            _append_simple_methods_section(lines, class_methods)

        class_fields = get_class_fields(data, line_range)
        if class_fields:
            _append_simple_fields_section(lines, class_fields)


def append_single_class_full_sections(
    lines: list[str],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> None:
    """Append legacy full-table sections for one or zero classes."""
    lines.append("## Methods")
    _append_simple_methods_table(lines, methods)
    lines.append("")

    lines.append("## Fields")
    _append_simple_fields_table(lines, fields)
    lines.append("")


def _simple_parameters(params: list[Any]) -> str:
    """Format legacy full-table parameter strings."""
    return ", ".join(_simple_parameter(param) for param in params)


def _simple_parameter(param: Any) -> str:
    """Format one legacy full-table parameter."""
    if isinstance(param, dict):
        param_type = str(param.get("type", "Object"))
        param_name = str(param.get("name", "param"))
        return f"{param_type} {param_name}"

    if isinstance(param, str):
        return param

    return str(param)


def _append_simple_methods_section(
    lines: list[str],
    methods: list[dict[str, Any]],
) -> None:
    """Append a headed legacy methods subsection."""
    lines.append("### Methods")
    _append_simple_methods_table(lines, methods)
    lines.append("")


def _append_simple_methods_table(
    lines: list[str],
    methods: list[dict[str, Any]],
) -> None:
    """Append a legacy methods table."""
    lines.append("| Name | Return Type | Parameters | Access | Line |")
    lines.append("|------|-------------|------------|--------|------|")
    for method in methods:
        lines.append(format_simple_method_row(method))


def _append_simple_fields_section(
    lines: list[str],
    fields: list[dict[str, Any]],
) -> None:
    """Append a headed legacy fields subsection."""
    lines.append("### Fields")
    _append_simple_fields_table(lines, fields)
    lines.append("")


def _append_simple_fields_table(
    lines: list[str],
    fields: list[dict[str, Any]],
) -> None:
    """Append a legacy fields table."""
    lines.append("| Name | Type | Access | Static | Final | Line |")
    lines.append("|------|------|--------|--------|-------|------|")
    for field in fields:
        lines.append(format_simple_field_row(field))
