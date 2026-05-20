"""Helper functions for the C# table formatter."""

from collections.abc import Callable
from typing import Any

ClassMemberSelector = Callable[
    [list[dict[str, Any]], dict[str, int]], list[dict[str, Any]]
]
ModifierFormatter = Callable[[dict[str, Any]], str]
VisibilityConverter = Callable[[str], str]
MethodRowFormatter = Callable[[dict[str, Any]], str]
NamespaceExtractor = Callable[[dict[str, Any]], str]
SignatureCreator = Callable[[dict[str, Any]], str]


def format_csharp_full_table(
    data: dict[str, Any],
    get_class_methods: ClassMemberSelector,
    get_class_fields: ClassMemberSelector,
    format_modifiers: ModifierFormatter,
    convert_visibility: VisibilityConverter,
    format_method_row: MethodRowFormatter,
) -> str:
    """Format full C# output while keeping section builders isolated."""
    lines: list[str] = []

    _append_file_header(lines, data)
    _append_imports(lines, data.get("imports", []))

    classes = data.get("classes", [])
    methods = data.get("methods", [])
    fields = data.get("fields", [])

    _append_classes_overview(
        lines, classes, methods, fields, get_class_methods, get_class_fields
    )
    _append_class_sections(
        lines,
        classes,
        methods,
        fields,
        get_class_methods,
        get_class_fields,
        format_modifiers,
        convert_visibility,
        format_method_row,
    )

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def format_csharp_compact_table(
    data: dict[str, Any],
    extract_namespace: NamespaceExtractor,
    create_compact_signature: SignatureCreator,
    convert_visibility: VisibilityConverter,
) -> str:
    """Format compact C# output."""
    lines: list[str] = []

    _append_file_header(lines, data)
    _append_compact_info(lines, data, extract_namespace)
    _append_compact_methods(
        lines, data.get("methods", []), create_compact_signature, convert_visibility
    )

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def format_csharp_csv(
    data: dict[str, Any],
    create_full_signature: SignatureCreator,
) -> str:
    """Format CSV C# output."""
    lines = ["Type,Name,Signature,Visibility,Lines,Complexity,Doc"]

    _append_csv_fields(lines, data.get("fields", []))
    _append_csv_methods(lines, data.get("methods", []), create_full_signature)

    lines.append("")
    return "\n".join(lines)


def _append_file_header(lines: list[str], data: dict[str, Any]) -> None:
    file_path = data.get("file_path", "Unknown")
    file_name = str(file_path).split("/")[-1].split("\\")[-1]
    lines.append(f"# {file_name}")
    lines.append("")


def _append_imports(lines: list[str], imports: list[dict[str, Any]]) -> None:
    if not imports:
        return

    lines.append("## Imports")
    lines.append("```csharp")
    for imp in imports:
        import_text = imp.get("raw_text", "").strip()
        if import_text:
            lines.append(import_text)
    lines.append("```")
    lines.append("")


def _append_compact_info(
    lines: list[str],
    data: dict[str, Any],
    extract_namespace: NamespaceExtractor,
) -> None:
    lines.append("## Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")

    stats = data.get("statistics") or {}
    lines.append(f"| Package | {extract_namespace(data)} |")
    lines.append(f"| Methods | {stats.get('method_count', 0)} |")
    lines.append(f"| Fields | {stats.get('field_count', 0)} |")
    lines.append("")


def _append_compact_methods(
    lines: list[str],
    methods: list[dict[str, Any]],
    create_compact_signature: SignatureCreator,
    convert_visibility: VisibilityConverter,
) -> None:
    if not methods:
        return

    lines.append("## Methods")
    lines.append("| Method | Sig | V | L | Cx | Doc |")
    lines.append("|--------|-----|---|---|----|----|")

    for method in methods:
        name = str(method.get("name", ""))
        signature = create_compact_signature(method)
        visibility = convert_visibility(str(method.get("visibility", "public")))
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = method.get("complexity_score", 1)
        lines.append(
            f"| {name} | {signature} | {visibility} | {lines_str} | {complexity} | - |"
        )
    lines.append("")


def _append_csv_fields(lines: list[str], fields: list[dict[str, Any]]) -> None:
    for field in fields:
        name = str(field.get("name", ""))
        field_type = str(
            field.get("type", "")
            or field.get("field_type", "")
            or field.get("variable_type", "")
        )
        signature = f"{name}:{field_type}" if field_type else name
        visibility = str(field.get("visibility", "private"))
        line_range = field.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        lines.append(f"Field,{name},{signature},{visibility},{lines_str},,-")


def _append_csv_methods(
    lines: list[str],
    methods: list[dict[str, Any]],
    create_full_signature: SignatureCreator,
) -> None:
    for method in methods:
        name = str(method.get("name", ""))
        method_type = "Constructor" if method.get("is_constructor", False) else "Method"
        signature = create_full_signature(method)
        visibility = str(method.get("visibility", "public"))
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        complexity = method.get("complexity_score", 1)

        if method.get("is_static"):
            signature = f"{signature} [static]"
        if "," in signature:
            signature = f'"{signature}"'

        lines.append(
            f"{method_type},{name},{signature},{visibility},{lines_str},{complexity},-"
        )


def _append_classes_overview(
    lines: list[str],
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    get_class_methods: ClassMemberSelector,
    get_class_fields: ClassMemberSelector,
) -> None:
    if not classes:
        return

    lines.append("## Classes Overview")
    lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
    lines.append("|-------|------|------------|-------|---------|--------|")

    for class_info in classes:
        name = str(class_info.get("name", "Unknown"))
        class_type = str(class_info.get("class_type", class_info.get("type", "class")))
        visibility = str(class_info.get("visibility", "public"))
        line_range = class_info.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        class_methods = get_class_methods(methods, line_range)
        class_fields = get_class_fields(fields, line_range)

        lines.append(
            f"| {name} | {class_type} | {visibility} | {lines_str} | "
            f"{len(class_methods)} | {len(class_fields)} |"
        )
    lines.append("")


def _append_class_sections(
    lines: list[str],
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    get_class_methods: ClassMemberSelector,
    get_class_fields: ClassMemberSelector,
    format_modifiers: ModifierFormatter,
    convert_visibility: VisibilityConverter,
    format_method_row: MethodRowFormatter,
) -> None:
    for class_info in classes:
        line_range = class_info.get("line_range", {})
        class_methods = get_class_methods(methods, line_range)
        class_fields = get_class_fields(fields, line_range)

        _append_class_heading(lines, class_info, line_range)
        _append_class_fields(lines, class_fields, format_modifiers, convert_visibility)
        _append_class_methods(lines, class_methods, format_method_row)


def _append_class_heading(
    lines: list[str], class_info: dict[str, Any], line_range: dict[str, int]
) -> None:
    class_name = str(class_info.get("name", "Unknown"))
    lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
    lines.append(f"## {class_name} ({lines_str})")


def _append_class_fields(
    lines: list[str],
    class_fields: list[dict[str, Any]],
    format_modifiers: ModifierFormatter,
    convert_visibility: VisibilityConverter,
) -> None:
    if not class_fields:
        return

    lines.append("### Fields")
    lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
    lines.append("|------|------|-----|-----------|------|-----|")

    for field in class_fields:
        name = str(field.get("name", ""))
        field_type = str(
            field.get("type", "")
            or field.get("field_type", "")
            or field.get("variable_type", "")
        )
        visibility = convert_visibility(str(field.get("visibility", "private")))
        modifiers = format_modifiers(field)
        field_line = field.get("line_range", {}).get("start", 0)
        lines.append(
            f"| {name} | {field_type} | {visibility} | {modifiers} | {field_line} | - |"
        )
    lines.append("")


def _append_class_methods(
    lines: list[str],
    class_methods: list[dict[str, Any]],
    format_method_row: MethodRowFormatter,
) -> None:
    method_groups = _group_methods_by_visibility(class_methods)
    _append_method_group(
        lines,
        "Constructors",
        "Constructor",
        method_groups["constructors"],
        format_method_row,
    )
    _append_method_group(
        lines, "Public Methods", "Method", method_groups["public"], format_method_row
    )
    _append_method_group(
        lines,
        "Protected Methods",
        "Method",
        method_groups["protected"],
        format_method_row,
    )
    _append_method_group(
        lines, "Private Methods", "Method", method_groups["private"], format_method_row
    )


def _group_methods_by_visibility(
    class_methods: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {
        "constructors": [],
        "public": [],
        "protected": [],
        "private": [],
    }

    for method in class_methods:
        if method.get("is_constructor", False):
            groups["constructors"].append(method)
            continue

        visibility = str(method.get("visibility", "public")).lower()
        if visibility in groups:
            groups[visibility].append(method)

    return groups


def _append_method_group(
    lines: list[str],
    title: str,
    first_column: str,
    methods: list[dict[str, Any]],
    format_method_row: MethodRowFormatter,
) -> None:
    if not methods:
        return

    lines.append(f"### {title}")
    lines.append(f"| {first_column} | Signature | Vis | Lines | Cx | Doc |")
    first_separator = "-------------" if first_column == "Constructor" else "--------"
    lines.append(f"|{first_separator}|-----------|-----|-------|----|----|")
    for method in methods:
        lines.append(format_method_row(method))
    lines.append("")
