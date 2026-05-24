"""Shared output helpers for the C/C++ table formatter."""

from collections.abc import Callable
from typing import Any


def format_cpp_full_table(formatter: Any, data: dict[str, Any]) -> str:
    """Full table format for C/C++."""
    lines = []
    package_name = (data.get("package") or {}).get("name", "unknown")
    file_name = _file_name(data.get("file_path", "Unknown"))

    lines.append(f"# {file_name}")
    lines.append("")

    _append_namespace_section(lines, data, package_name)
    _append_imports_section(lines, data)

    classes = data.get("classes", [])
    if len(classes) > 0:
        _append_classes_section(formatter, lines, data, classes)

    _append_global_functions(formatter, lines, data, classes)
    _append_global_variables(formatter, lines, data, classes)
    _trim_trailing_blank_lines(lines)
    return "\n".join(lines)


def format_cpp_class_details(
    formatter: Any, class_info: dict[str, Any], data: dict[str, Any]
) -> list[str]:
    """Format details for a single C/C++ class."""
    lines = []
    name = str(class_info.get("name", "Unknown"))
    line_range = class_info.get("line_range", {})
    lines.append(f"## {name} ({_line_range_text(line_range)})")

    class_methods = _members_in_range(data.get("methods", []), line_range)
    class_fields = _members_in_range(data.get("fields", []), line_range)
    _append_class_fields(formatter, lines, class_fields)
    _append_class_methods(formatter, lines, class_methods)
    return lines


def format_cpp_compact_table(formatter: Any, data: dict[str, Any]) -> str:
    """Compact table format for C/C++."""
    lines = []
    file_name = _file_name(data.get("file_path", "Unknown"))
    lines.append(f"# {file_name}")
    lines.append("")

    _append_compact_info(lines, data)
    _append_compact_methods(formatter, lines, data.get("methods", []))
    _trim_trailing_blank_lines(lines)
    return "\n".join(lines)


def create_cpp_compact_signature(
    shorten_type: Callable[[Any], str], method: dict[str, Any]
) -> str:
    """Create compact C/C++ method signature."""
    param_types = [
        shorten_type(_compact_param_type(param))
        for param in method.get("parameters", [])
    ]
    params_str = ",".join(param_types)
    return_type = shorten_type(method.get("return_type", "void"))
    return f"({params_str}):{return_type}"


def shorten_cpp_type(type_name: Any) -> str:
    """Shorten type name for C/C++ compact display."""
    if type_name is None:
        return "void"

    type_text = str(type_name).strip()
    if any(marker in type_text for marker in ["*", "&", "["]):
        return type_text

    type_text = (
        type_text.replace("const ", "")
        .replace("volatile ", "")
        .replace("static ", "")
        .strip()
    )
    type_map = {
        "int": "i",
        "double": "d",
        "float": "f",
        "char": "c",
        "long": "l",
        "short": "s",
        "bool": "b",
        "void": "void",
        "size_t": "size_t",
        "string": "str",
    }
    return type_map.get(type_text, type_text)


def _append_namespace_section(
    lines: list[str], data: dict[str, Any], package_name: Any
) -> None:
    packages = data.get("packages", [])
    if packages:
        lines.append("## Namespaces")
        for pkg in packages:
            lines.append(
                f"- `{pkg.get('name')}` ({_line_range_text(pkg.get('line_range', {}))})"
            )
        lines.append("")
    elif package_name and package_name != "unknown":
        lines.append("## Package")
        lines.append(f"`{package_name}`")
        lines.append("")


def _append_imports_section(lines: list[str], data: dict[str, Any]) -> None:
    imports = data.get("imports", [])
    if not imports:
        return

    lines.append("## Imports")
    lines.append(f"```{data.get('language', 'cpp')}")
    for imp in imports:
        stmt = str(imp.get("statement", "")).strip()
        if stmt:
            lines.append(stmt)
    lines.append("```")
    lines.append("")


def _append_classes_section(
    formatter: Any,
    lines: list[str],
    data: dict[str, Any],
    classes: list[dict[str, Any]],
) -> None:
    lines.append("## Classes Overview")
    lines.append("| Class | Type | Visibility | Lines | Methods | Fields |")
    lines.append("|-------|------|------------|-------|---------|--------|")

    for class_info in classes:
        lines.append(_format_class_overview_row(data, class_info))
    lines.append("")

    for class_info in classes:
        lines.extend(formatter._format_class_details(class_info, data))


def _format_class_overview_row(data: dict[str, Any], class_info: dict[str, Any]) -> str:
    line_range = class_info.get("line_range", {})
    class_methods = _members_in_range(data.get("methods", []), line_range)
    class_fields = _members_in_range(data.get("fields", []), line_range)
    return (
        f"| {str(class_info.get('name', 'Unknown'))} | "
        f"{str(class_info.get('type', 'class'))} | "
        f"{str(class_info.get('visibility', 'public'))} | "
        f"{_line_range_text(line_range)} | {len(class_methods)} | "
        f"{len(class_fields)} |"
    )


def _append_global_functions(
    formatter: Any,
    lines: list[str],
    data: dict[str, Any],
    classes: list[dict[str, Any]],
) -> None:
    global_methods = _members_outside_classes(data.get("methods", []), classes)
    if not global_methods:
        return

    lines.append("## Global Functions")
    lines.append("| Method | Signature | Vis | Lines | Cols | Cx | Doc |")
    lines.append("|--------|-----------|-----|-------|------|----|----|")
    for method in global_methods:
        lines.append(formatter._format_method_row(method))
    lines.append("")


def _append_global_variables(
    formatter: Any,
    lines: list[str],
    data: dict[str, Any],
    classes: list[dict[str, Any]],
) -> None:
    global_fields = _members_outside_classes(data.get("fields", []), classes)
    if not global_fields:
        return

    lines.append("## Global Variables")
    lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
    lines.append("|------|------|-----|-----------|------|-----|")
    for field in global_fields:
        lines.append(_format_field_row(formatter, field, escape_doc=True))
    lines.append("")


def _append_class_fields(
    formatter: Any, lines: list[str], class_fields: list[dict[str, Any]]
) -> None:
    if not class_fields:
        return

    lines.append("### Fields")
    lines.append("| Name | Type | Vis | Modifiers | Line | Doc |")
    lines.append("|------|------|-----|-----------|------|-----|")
    for field in class_fields:
        lines.append(_format_field_row(formatter, field, escape_doc=False))
    lines.append("")


def _append_class_methods(
    formatter: Any, lines: list[str], class_methods: list[dict[str, Any]]
) -> None:
    if not class_methods:
        return

    public_methods = [
        method
        for method in class_methods
        if "public" in method.get("modifiers", [])
        or method.get("visibility") == "public"
    ]
    private_methods = [
        method
        for method in class_methods
        if "private" in method.get("modifiers", [])
        or method.get("visibility") == "private"
    ]
    other_methods = [
        method
        for method in class_methods
        if method not in public_methods and method not in private_methods
    ]

    _append_method_group(formatter, lines, "### Public Methods", public_methods)
    _append_method_group(formatter, lines, "### Private Methods", private_methods)
    _append_method_group(formatter, lines, "### Methods", other_methods)


def _append_method_group(
    formatter: Any,
    lines: list[str],
    title: str,
    methods: list[dict[str, Any]],
) -> None:
    if not methods:
        return

    lines.append(title)
    lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
    lines.append("|--------|-----------|-----|-------|----|----|")
    for method in methods:
        lines.append(formatter._format_method_row(method))
    lines.append("")


def _append_compact_info(lines: list[str], data: dict[str, Any]) -> None:
    stats = data.get("statistics") or {}
    package_name = (data.get("package") or {}).get("name", "unknown")
    language = data.get("language", "").lower()

    lines.append("## Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    if language in ("cpp", "c++") or (package_name and package_name != "unknown"):
        lines.append(f"| Package | {package_name} |")
    lines.append(f"| Methods | {stats.get('method_count', 0)} |")
    lines.append(f"| Fields | {stats.get('field_count', 0)} |")
    lines.append("")


def _append_compact_methods(
    formatter: Any, lines: list[str], methods: list[dict[str, Any]]
) -> None:
    if not methods:
        return

    lines.append("## Methods")
    lines.append("| Method | Sig | V | L | Cx | Doc |")
    lines.append("|--------|-----|---|---|----|----|")
    for method in methods:
        lines.append(_format_compact_method_row(formatter, method))
    lines.append("")


def _format_compact_method_row(formatter: Any, method: dict[str, Any]) -> str:
    doc = formatter._clean_csv_text(
        formatter._extract_doc_summary(str(method.get("javadoc", "")))
    )
    return (
        f"| {str(method.get('name', ''))} | "
        f"{formatter._create_compact_signature(method)} | "
        f"{formatter._convert_visibility(str(method.get('visibility', '')))} | "
        f"{_line_range_text(method.get('line_range', {}))} | "
        f"{method.get('complexity_score', 0)} | {doc} |"
    )


def _format_field_row(
    formatter: Any, field: dict[str, Any], *, escape_doc: bool
) -> str:
    doc = str(field.get("javadoc", "")) or "-"
    if escape_doc:
        doc = doc.replace("\n", " ").replace("|", "\\|")[:50]
    return (
        f"| {str(field.get('name', ''))} | {str(field.get('type', ''))} | "
        f"{formatter._convert_visibility(str(field.get('visibility', '')))} | "
        f"{','.join([str(modifier) for modifier in field.get('modifiers', [])])} | "
        f"{field.get('line_range', {}).get('start', 0)} | {doc} |"
    )


def _members_in_range(
    items: list[dict[str, Any]], line_range: dict[str, Any]
) -> list[dict[str, Any]]:
    start = line_range.get("start", 0)
    end = line_range.get("end", 0)
    return [
        item
        for item in items
        if start <= item.get("line_range", {}).get("start", 0) <= end
    ]


def _members_outside_classes(
    items: list[dict[str, Any]], classes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [item for item in items if not _is_inside_class(item, classes)]


def _is_inside_class(item: dict[str, Any], classes: list[dict[str, Any]]) -> bool:
    item_start = item.get("line_range", {}).get("start", 0)
    return any(
        class_info.get("line_range", {}).get("start", 0)
        <= item_start
        <= class_info.get("line_range", {}).get("end", 0)
        for class_info in classes
    )


def _compact_param_type(param: Any) -> Any:
    if isinstance(param, dict):
        return _compact_param_type_from_dict(param)
    if isinstance(param, str):
        return _compact_param_type_from_string(param)
    return "Any"


def _compact_param_type_from_dict(param: dict[str, Any]) -> Any:
    type_str = param.get("type", "Any")
    name_str = param.get("name", "")
    if "[]" in name_str:
        type_str += "[]"
    if name_str.startswith("*") and not type_str.endswith("*"):
        type_str += "*"
    return type_str


def _compact_param_type_from_string(param: str) -> str:
    if ":" in param:
        return param.split(":", 1)[1].strip()

    tokens = param.strip().split()
    if len(tokens) < 2:
        return tokens[0] if tokens else "Any"

    type_str = " ".join(tokens[:-1])
    name_part = tokens[-1]
    if "[]" in name_part:
        type_str += "[]"
    if name_part.startswith("*") and not type_str.endswith("*"):
        type_str += "*"
    return type_str


def _line_range_text(line_range: dict[str, Any]) -> str:
    return f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"


def _file_name(file_path: Any) -> str:
    return file_path.split("/")[-1].split("\\")[-1]


def _trim_trailing_blank_lines(lines: list[str]) -> None:
    while lines and lines[-1] == "":
        lines.pop()
