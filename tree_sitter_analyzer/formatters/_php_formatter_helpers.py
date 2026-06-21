"""Helper functions for PHP table formatting."""

from __future__ import annotations

from typing import Any


def get_visibility_symbol(visibility: str) -> str:
    """Convert visibility to a compact symbol."""
    visibility_map = {
        "public": "+",
        "private": "-",
        "protected": "#",
    }
    return visibility_map.get(str(visibility).lower(), "+")


def format_signature(method: dict[str, Any]) -> str:
    """Format method signature like Java: ($param:type):returnType."""
    param_strs = []
    for param in method.get("parameters", []):
        if isinstance(param, dict):
            name = param.get("name", "")
            param_type = param.get("type", "mixed")
            if name:
                param_strs.append(f"${str(name).lstrip('$')}:{param_type}")
            else:
                param_strs.append(str(param_type))
        else:
            param_strs.append(str(param))

    return_type = method.get("return_type", "void")
    return f"({', '.join(param_strs)}):{return_type}"


def format_compact_signature(method: dict[str, Any]) -> str:
    """Format compact method signature."""
    param_strs = []
    for param in method.get("parameters", []):
        if isinstance(param, dict):
            param_strs.append(str(param.get("type", "Any")))
        else:
            param_strs.append(str(param))

    return_type = method.get("return_type", "")
    suffix = str(return_type) if return_type else ""
    return f"({', '.join(param_strs)}):{suffix}"


def extract_namespace(data: dict[str, Any]) -> str:
    """Extract namespace from class metadata."""
    for class_info in data.get("classes", []):
        fqn = class_info.get("full_qualified_name", "")
        if fqn and "\\" in fqn:
            return "\\".join(fqn.split("\\")[:-1])

        namespace = class_info.get("metadata", {}).get("namespace", "")
        if namespace:
            return str(namespace)
    return ""


def format_full_table(data: dict[str, Any]) -> str:
    """Full table format for PHP, following Java golden master format."""
    lines = _header_lines(data)
    _append_imports(lines, data.get("imports", []))

    classes = data.get("classes", [])
    methods = data.get("methods", [])
    fields = data.get("fields", [])
    _append_classes_overview(lines, classes, methods, fields)
    _append_class_details(lines, classes, methods, fields)
    _append_module_level_functions(lines, classes, methods)
    return "\n".join(lines)


def _header_lines(data: dict[str, Any]) -> list[str]:
    file_path = data.get("file_path", "Unknown")
    file_name = str(file_path).split("/")[-1].split("\\")[-1]
    return [f"# {file_name}", ""]


def _append_imports(lines: list[str], imports: list[dict[str, Any]]) -> None:
    if not imports:
        return

    lines.append("## Imports")
    lines.append("```php")
    for import_info in imports:
        import_text = import_info.get("raw_text", "").strip()
        if import_text:
            lines.append(import_text)
    lines.append("```")
    lines.append("")


def _append_classes_overview(
    lines: list[str],
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> None:
    if not classes:
        return

    lines.append("## Classes Overview")
    lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
    lines.append("|-------|------|------------|-------|---------|--------|")

    for class_info in classes:
        lines.append(_class_overview_row(class_info, methods, fields))
    lines.append("")


def _class_overview_row(
    class_info: dict[str, Any],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> str:
    start_line, end_line = _class_line_range(class_info)
    return (
        f"| {class_info.get('name', 'Unknown')} | "
        f"{class_info.get('class_type', class_info.get('type', 'class'))} | "
        f"{class_info.get('visibility', 'public')} | "
        f"{start_line}-{end_line} | "
        f"{_range_count(methods, start_line, end_line)} | "
        f"{_range_count(fields, start_line, end_line)} |"
    )


def _range_count(elements: list[dict[str, Any]], start_line: int, end_line: int) -> int:
    return len(_elements_in_range(elements, start_line, end_line))


def _append_class_details(
    lines: list[str],
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> None:
    for class_info in classes:
        class_name = str(class_info.get("name", "Unknown"))
        start_line, end_line = _class_line_range(class_info)
        simple_class_name = _simple_class_name(class_name)

        lines.append(f"## {class_name} ({start_line}-{end_line})")
        class_fields = _elements_in_range(fields, start_line, end_line)
        _append_class_fields(lines, simple_class_name, class_fields)

        class_methods = _elements_in_range(methods, start_line, end_line)
        _append_class_methods(lines, simple_class_name, class_methods)


def _append_class_fields(
    lines: list[str], simple_class_name: str, fields: list[dict[str, Any]]
) -> None:
    if not fields:
        return

    lines.append("### Fields")
    lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
    lines.append("|------|------|-----|-----------|------|-----|")
    for field in fields:
        lines.append(_field_row(field, simple_class_name))
    lines.append("")


def _field_row(field: dict[str, Any], simple_class_name: str) -> str:
    field_name = str(field.get("name", "Unknown"))
    return (
        f"| {_qualified_field_name(field_name, simple_class_name)} | "
        f"{field.get('variable_type', field.get('type', 'mixed'))} | "
        f"{get_visibility_symbol(field.get('visibility', 'public'))} | "
        f"{_field_modifiers(field)} | "
        f"{field.get('line_range', {}).get('start', 0)} | "
        f"{_trim_doc(field.get('documentation', '-') or '-', 30)} |"
    )


def _qualified_field_name(field_name: str, simple_class_name: str) -> str:
    return field_name if "::" in field_name else f"{simple_class_name}::{field_name}"


def _field_modifiers(field: dict[str, Any]) -> str:
    modifiers = []
    if field.get("visibility"):
        modifiers.append(str(field.get("visibility")))
    if field.get("is_static"):
        modifiers.append("static")
    if field.get("is_readonly"):
        modifiers.append("readonly")
    return ",".join(modifiers)


def _append_class_methods(
    lines: list[str], simple_class_name: str, methods: list[dict[str, Any]]
) -> None:
    for group_name, group_methods in _method_groups(methods):
        if not group_methods:
            continue

        lines.append(f"### {group_name}")
        header = "Constructor" if group_name == "Constructors" else "Method"
        lines.append(f"| {header} | Signature | Vis | Lines | Cx | Doc |")
        lines.append("|--------|-----------|-----|-------|----|----|")
        for method in group_methods:
            lines.append(_full_method_row(method, simple_class_name))
        lines.append("")


def _method_groups(
    methods: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    constructors = _constructor_methods(methods)
    return [
        ("Constructors", constructors),
        ("Public Methods", _public_methods(methods, constructors)),
        ("Protected Methods", _methods_with_visibility(methods, "protected")),
        ("Private Methods", _methods_with_visibility(methods, "private")),
    ]


def _constructor_methods(methods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [method for method in methods if _is_constructor(method)]


def _is_constructor(method: dict[str, Any]) -> bool:
    return bool(method.get("is_constructor")) or str(method.get("name", "")).startswith(
        "__construct"
    )


def _public_methods(
    methods: list[dict[str, Any]], constructors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        method
        for method in methods
        if method.get("visibility", "public") == "public" and method not in constructors
    ]


def _methods_with_visibility(
    methods: list[dict[str, Any]], visibility: str
) -> list[dict[str, Any]]:
    return [method for method in methods if method.get("visibility") == visibility]


def _full_method_row(
    method: dict[str, Any], simple_class_name: str | None = None
) -> str:
    method_name = str(method.get("name", "Unknown"))
    if simple_class_name and "::" not in method_name:
        method_name = f"{simple_class_name}::{method_name}"

    signature = format_signature(method)
    if method.get("is_static"):
        signature += " [static]"

    visibility = get_visibility_symbol(method.get("visibility", "public"))
    line_range = method.get("line_range", {})
    lines = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    complexity = method.get("complexity_score", method.get("complexity", 1))
    doc = _trim_doc(method.get("documentation", "-") or "-", 30)
    return f"| {method_name} | {signature} | {visibility} | {lines} | {complexity} | {doc} |"


def _append_module_level_functions(
    lines: list[str], classes: list[dict[str, Any]], methods: list[dict[str, Any]]
) -> None:
    module_methods = _module_level_methods(classes, methods)
    if not module_methods:
        return

    lines.append("## Functions")
    lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
    lines.append("|--------|-----------|-----|-------|----|----|")
    for method in module_methods:
        lines.append(_full_method_row(method))
    lines.append("")


def _module_level_methods(
    classes: list[dict[str, Any]], methods: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    class_ranges = [_class_line_range(class_info) for class_info in classes]
    return [
        method
        for method in methods
        if not _line_in_any_range(_method_start_line(method), class_ranges)
    ]


def _method_start_line(method: dict[str, Any]) -> int:
    return int(method.get("line_range", {}).get("start", 0))


def format_compact_table(data: dict[str, Any]) -> str:
    """Compact table format for PHP, following Java golden master format."""
    lines = _header_lines(data)
    _append_compact_info(lines, data)
    _append_compact_methods(lines, data.get("methods", []))
    return "\n".join(lines)


def _append_compact_info(lines: list[str], data: dict[str, Any]) -> None:
    stats = data.get("statistics") or {}
    lines.append("## Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    namespace = extract_namespace(data)
    lines.append(f"| Namespace | {namespace if namespace else ''} |")
    lines.append(
        f"| Methods | {stats.get('method_count', len(data.get('methods', [])))} |"
    )
    lines.append(
        f"| Fields | {stats.get('field_count', len(data.get('fields', [])))} |"
    )
    lines.append("")


def _append_compact_methods(lines: list[str], methods: list[dict[str, Any]]) -> None:
    if not methods:
        return

    lines.append("## Methods")
    lines.append("| Method | Sig | V | L | Cx | Doc |")
    lines.append("|--------|-----|---|---|----|----|")
    for method in methods:
        lines.append(_compact_method_row(method))


def _compact_method_row(method: dict[str, Any]) -> str:
    method_name = str(method.get("name", "Unknown"))
    parent_class = method.get("parent_class", "")
    if parent_class:
        method_name = f"{parent_class}::{method_name}"

    signature = format_compact_signature(method)
    visibility = get_visibility_symbol(method.get("visibility", "public"))
    line_range = method.get("line_range", {})
    lines = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    complexity = method.get("complexity_score", method.get("complexity", 1))
    doc = _trim_doc(method.get("documentation", "-") or "-", 20)
    return f"| {method_name} | {signature} | {visibility} | {lines} | {complexity} | {doc} |"


def _class_line_range(class_info: dict[str, Any]) -> tuple[int, int]:
    line_range = class_info.get("line_range", {})
    return line_range.get("start", 0), line_range.get("end", 0)


def _elements_in_range(
    elements: list[dict[str, Any]], start_line: int, end_line: int
) -> list[dict[str, Any]]:
    return [
        element
        for element in elements
        if start_line <= element.get("line_range", {}).get("start", 0) <= end_line
    ]


def _line_in_any_range(line: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= line <= end for start, end in ranges)


def _simple_class_name(class_name: str) -> str:
    return class_name.split("\\")[-1] if "\\" in class_name else class_name


def _trim_doc(doc: str, limit: int) -> str:
    return doc[: limit - 3] + "..." if doc and len(doc) > limit else doc
