"""Ruby table formatting helpers."""

from typing import Any


def get_visibility_symbol(visibility: str) -> str:
    """Convert visibility to symbol."""
    visibility_map = {
        "public": "+",
        "private": "-",
        "protected": "#",
        "module": "~",
    }
    return visibility_map.get(str(visibility).lower(), "+")


def format_signature(method: dict[str, Any]) -> str:
    """Format method signature like Java: (param:type):returnType."""
    params = method.get("parameters", [])
    param_strs = [_full_param(param) for param in params]

    return_type = method.get("return_type", "")
    signature = f"({', '.join(param_strs)}):"
    return f"{signature}{return_type}" if return_type else signature


def format_compact_signature(method: dict[str, Any]) -> str:
    """Format compact method signature."""
    params = method.get("parameters", [])
    param_strs = [_compact_param(param) for param in params]

    return_type = method.get("return_type", "")
    signature = f"({', '.join(param_strs)}):"
    return f"{signature}{return_type}" if return_type else signature


def format_full_table(data: dict[str, Any]) -> str:
    """Full table format for Ruby, following Java golden master format."""
    lines = _header_lines(data)
    classes = data.get("classes", [])
    imports = data.get("imports", [])
    methods = data.get("methods", [])
    fields = data.get("fields", [])

    _append_imports(lines, imports)
    method_counts, field_counts = _class_member_counts(classes, methods, fields)
    _append_classes_overview(lines, classes, method_counts, field_counts)
    _append_class_details(lines, classes, methods, fields)
    _append_module_level_methods(lines, classes, methods)
    return "\n".join(lines)


def format_compact_table(data: dict[str, Any]) -> str:
    """Compact table format for Ruby, following Java golden master format."""
    lines = _header_lines(data)
    stats = data.get("statistics") or {}
    methods = data.get("methods", [])

    lines.extend(
        [
            "## Info",
            "| Property | Value |",
            "|----------|-------|",
            "| Package |  |",
            f"| Methods | {stats.get('method_count', len(methods))} |",
            f"| Fields | {stats.get('field_count', len(data.get('fields', [])))} |",
            "",
        ]
    )
    _append_compact_methods(lines, methods)
    return "\n".join(lines)


def format_csv(data: dict[str, Any]) -> str:
    """CSV format for Ruby, following Java golden master format."""
    lines = ["Type,Name,Signature,Visibility,Lines,Complexity,Doc"]
    _append_csv_fields(lines, data.get("fields", []))
    _append_csv_methods(lines, data.get("methods", []))
    return "\n".join(lines)


def _full_param(param: Any) -> str:
    if isinstance(param, dict):
        name = param.get("name", "")
        param_type = param.get("type", "Any")
        return f"{name}:{param_type}" if name else str(param_type)
    return str(param)


def _compact_param(param: Any) -> str:
    if isinstance(param, dict):
        return str(param.get("type", "Any"))
    return str(param)


def _header_lines(data: dict[str, Any]) -> list[str]:
    classes = data.get("classes", [])
    file_path = data.get("file_path", "Unknown")
    file_name = file_path.split("/")[-1].split("\\")[-1]
    if len(classes) == 1:
        class_name = classes[0].get("name", file_name)
        return [f"# {class_name}", ""]
    return [f"# {file_name}", ""]


def _append_imports(lines: list[str], imports: list[dict[str, Any]]) -> None:
    if not imports:
        return

    lines.append("## Imports")
    lines.append("```ruby")
    for import_info in imports:
        import_text = import_info.get("raw_text", "").strip()
        if import_text:
            lines.append(import_text)
    lines.append("```")
    lines.append("")


def _class_member_counts(
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> tuple[dict[str, int], dict[str, int]]:
    method_counts = _empty_class_counts(classes)
    field_counts = _empty_class_counts(classes)
    _increment_member_counts(method_counts, methods, classes)
    _increment_member_counts(field_counts, fields, classes)
    return method_counts, field_counts


def _empty_class_counts(classes: list[dict[str, Any]]) -> dict[str, int]:
    return {class_info.get("name", ""): 0 for class_info in classes}


def _increment_member_counts(
    counts: dict[str, int],
    members: list[dict[str, Any]],
    classes: list[dict[str, Any]],
) -> None:
    for member in members:
        parent = _get_parent_class(
            member.get("line_range", {}).get("start", 0), classes
        )
        if parent and parent in counts:
            counts[parent] += 1


def _get_parent_class(item_start: int, classes: list[dict[str, Any]]) -> str | None:
    containing_classes = []
    for class_info in classes:
        class_range = class_info.get("line_range", {})
        class_start = class_range.get("start", 0)
        class_end = class_range.get("end", 0)
        if class_start <= item_start <= class_end:
            containing_classes.append((class_info, class_end - class_start))

    if not containing_classes:
        return None

    containing_classes.sort(key=lambda item: item[1])
    name = containing_classes[0][0].get("name")
    return str(name) if name else None


def _append_classes_overview(
    lines: list[str],
    classes: list[dict[str, Any]],
    method_counts: dict[str, int],
    field_counts: dict[str, int],
) -> None:
    if not classes:
        return

    lines.append("## Classes Overview")
    lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
    lines.append("|-------|------|------------|-------|---------|--------|")
    for class_info in classes:
        lines.append(_class_overview_row(class_info, method_counts, field_counts))
    lines.append("")


def _class_overview_row(
    class_info: dict[str, Any],
    method_counts: dict[str, int],
    field_counts: dict[str, int],
) -> str:
    name = str(class_info.get("name", "Unknown"))
    class_type = str(class_info.get("class_type", class_info.get("type", "class")))
    visibility = str(class_info.get("visibility", "public"))
    line_range = class_info.get("line_range", {})
    lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    return (
        f"| {name} | {class_type} | {visibility} | {lines_str} | "
        f"{method_counts.get(name, 0)} | {field_counts.get(name, 0)} |"
    )


def _append_class_details(
    lines: list[str],
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> None:
    for class_info in classes:
        class_name = str(class_info.get("name", "Unknown"))
        class_range = class_info.get("line_range", {})
        start_line = class_range.get("start", 0)
        end_line = class_range.get("end", 0)

        lines.append(f"## {class_name} ({start_line}-{end_line})")
        _append_class_fields(lines, class_name, classes, fields)
        _append_class_methods(lines, class_name, classes, methods)


def _append_class_fields(
    lines: list[str],
    class_name: str,
    classes: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> None:
    class_fields = [
        field
        for field in fields
        if _get_parent_class(field.get("line_range", {}).get("start", 0), classes)
        == class_name
    ]
    if not class_fields:
        return

    lines.append("### Fields")
    lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
    lines.append("|------|------|-----|-----------|------|-----|")
    for field in class_fields:
        lines.append(_field_row(field))
    lines.append("")


def _field_row(field: dict[str, Any]) -> str:
    field_name = str(field.get("name", "Unknown"))
    field_type = str(field.get("variable_type", field.get("type", "None")))
    visibility = get_visibility_symbol(field.get("visibility", "public"))
    line = field.get("line_range", {}).get("start", 0)
    return (
        f"| {field_name} | {field_type} | {visibility} | "
        f"{_modifiers_text(field.get('modifiers', []))} | {line} | "
        f"{_trim_doc(field.get('documentation', '-') or '-', 30)} |"
    )


def _modifiers_text(modifiers: Any) -> str:
    if isinstance(modifiers, list):
        return ",".join(str(modifier) for modifier in modifiers)
    return str(modifiers) if modifiers else ""


def _append_class_methods(
    lines: list[str],
    class_name: str,
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
) -> None:
    class_methods = [
        method
        for method in methods
        if _get_parent_class(method.get("line_range", {}).get("start", 0), classes)
        == class_name
    ]
    ordered_methods = _ordered_class_methods(class_methods)
    if not ordered_methods:
        return

    lines.append("### Public Methods")
    lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
    lines.append("|--------|-----------|-----|-------|----|----|")
    for method in ordered_methods:
        lines.append(_method_row(method, class_name))
    lines.append("")


def _ordered_class_methods(methods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    constructors = [
        method
        for method in methods
        if method.get("is_constructor") or method.get("name") == "initialize"
    ]
    public_methods = [method for method in methods if method not in constructors]
    return constructors + public_methods


def _method_row(method: dict[str, Any], class_name: str | None = None) -> str:
    method_name = _method_display_name(method, class_name)
    signature = format_signature(method)
    method_type = method.get("metadata", {}).get("method_type", "instance")
    if method.get("is_static") or method_type == "class":
        signature += " [static]"
    visibility = get_visibility_symbol(method.get("visibility", "public"))
    line_range = method.get("line_range", {})
    lines = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    complexity = method.get("complexity_score", method.get("complexity", 1))
    doc = _trim_doc(method.get("documentation", "-") or "-", 30)
    return (
        f"| {method_name} | {signature} | {visibility} | {lines} | "
        f"{complexity} | {doc} |"
    )


def _method_display_name(method: dict[str, Any], class_name: str | None) -> str:
    method_name = str(method.get("name", "Unknown"))
    if not class_name or "#" in method_name or "." in method_name:
        return method_name

    method_type = method.get("metadata", {}).get("method_type", "instance")
    separator = "." if method_type == "class" or method.get("is_static") else "#"
    return f"{class_name}{separator}{method_name}"


def _append_module_level_methods(
    lines: list[str],
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
) -> None:
    module_level_methods = [
        method
        for method in methods
        if _get_parent_class(method.get("line_range", {}).get("start", 0), classes)
        is None
    ]
    if not module_level_methods:
        return

    lines.append("## Module Functions")
    lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
    lines.append("|--------|-----------|-----|-------|----|----|")
    for method in module_level_methods:
        lines.append(_module_method_row(method))
    lines.append("")


def _module_method_row(method: dict[str, Any]) -> str:
    method_name = str(method.get("name", "Unknown"))
    signature = format_signature(method)
    visibility = get_visibility_symbol(method.get("visibility", "public"))
    line_range = method.get("line_range", {})
    lines = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    complexity = method.get("complexity_score", method.get("complexity", 1))
    doc = _trim_doc(method.get("documentation", "-") or "-", 30)
    return (
        f"| {method_name} | {signature} | {visibility} | {lines} | "
        f"{complexity} | {doc} |"
    )


def _append_compact_methods(lines: list[str], methods: list[dict[str, Any]]) -> None:
    if not methods:
        return

    lines.append("## Methods")
    lines.append("| Method | Sig | V | L | Cx | Doc |")
    lines.append("|--------|-----|---|---|----|----|")
    for method in methods:
        lines.append(_compact_method_row(method))


def _compact_method_row(method: dict[str, Any]) -> str:
    method_name = _compact_method_name(method)
    signature = format_compact_signature(method)
    visibility = get_visibility_symbol(method.get("visibility", "public"))
    line_range = method.get("line_range", {})
    lines = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    complexity = method.get("complexity_score", method.get("complexity", 1))
    doc = _trim_doc(method.get("documentation", "-") or "-", 20)
    return (
        f"| {method_name} | {signature} | {visibility} | {lines} | "
        f"{complexity} | {doc} |"
    )


def _compact_method_name(method: dict[str, Any]) -> str:
    method_name = str(method.get("name", "Unknown"))
    parent_class = method.get("parent_class", "")
    if not parent_class:
        return method_name

    method_type = method.get("metadata", {}).get("method_type", "instance")
    prefix = "." if method_type == "class" else "#"
    return f"{parent_class}{prefix}{method_name}"


def _append_csv_fields(lines: list[str], fields: list[dict[str, Any]]) -> None:
    for field in fields:
        field_name = str(field.get("name", "Unknown"))
        parent = field.get("parent_class", "")
        full_name = f"{parent}::{field_name}" if parent else field_name
        field_type = str(field.get("variable_type", field.get("type", "None")))
        signature = f"{full_name}:{field_type}"
        visibility = str(field.get("visibility", "public"))
        line_range = field.get("line_range", {})
        field_lines = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        doc = field.get("documentation", "-") or "-"
        lines.append(f"Field,{full_name},{signature},{visibility},{field_lines},,{doc}")


def _append_csv_methods(lines: list[str], methods: list[dict[str, Any]]) -> None:
    for method in methods:
        lines.append(_csv_method_row(method))


def _csv_method_row(method: dict[str, Any]) -> str:
    method_name = str(method.get("name", "Unknown"))
    method_type = method.get("metadata", {}).get("method_type", "instance")
    full_name = _csv_method_name(
        method_name, method.get("parent_class", ""), method_type
    )
    return (
        f"{_csv_entry_type(method, method_name)},{full_name},"
        f"{_csv_signature(method, method_type)},"
        f"{method.get('visibility', 'public')},{_line_span(method)},"
        f"{method.get('complexity_score', method.get('complexity', 1))},"
        f"{method.get('documentation', '-') or '-'}"
    )


def _csv_entry_type(method: dict[str, Any], method_name: str) -> str:
    if method.get("is_constructor") or method_name == "initialize":
        return "Constructor"
    return "Method"


def _csv_signature(method: dict[str, Any], method_type: str) -> str:
    signature = format_signature(method)
    if method.get("is_static") or method_type == "class":
        return signature + " [static]"
    return signature


def _csv_method_name(method_name: str, parent: str, method_type: str) -> str:
    if not parent:
        return method_name
    prefix = "." if method_type == "class" else "#"
    return f"{parent}{prefix}{method_name}"


def _line_span(item: dict[str, Any]) -> str:
    line_range = item.get("line_range", {})
    return f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"


def _trim_doc(doc: Any, max_length: int) -> str:
    doc_text = str(doc)
    if doc_text and len(doc_text) > max_length:
        return doc_text[: max_length - 3] + "..."
    return doc_text
