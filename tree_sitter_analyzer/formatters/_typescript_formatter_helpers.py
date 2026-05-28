"""Shared helpers for TypeScript formatter output."""

from typing import Any


def typescript_title(data: dict[str, Any], *, strip_declaration_suffix: bool) -> str:
    """Return the primary TypeScript title for a formatted result."""
    classes = data.get("classes", [])
    if classes:
        return str(classes[0].get("name", "Unknown"))

    file_path = data.get("file_path", "Unknown")
    file_name = str(file_path).split("/")[-1].split("\\")[-1]
    title = file_name.replace(".ts", "").replace(".tsx", "")
    if strip_declaration_suffix:
        title = title.replace(".d.ts", "")
    return title


def line_range_text(line_range: dict[str, int]) -> str:
    """Format a line-range mapping as start-end text."""
    return f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"


def get_class_methods(
    methods: list[dict[str, Any]], line_range: dict[str, int]
) -> list[dict[str, Any]]:
    """Get methods within a class range."""
    return _members_in_range(methods, line_range)


def get_class_fields(
    fields: list[dict[str, Any]], line_range: dict[str, int]
) -> list[dict[str, Any]]:
    """Get fields within a class range."""
    return _members_in_range(fields, line_range)


def field_type(field: dict[str, Any]) -> str:
    """Return the best TypeScript field type text available."""
    return str(
        field.get("type", "")
        or field.get("field_type", "")
        or field.get("variable_type", "")
    )


def format_typescript_modifiers(element: dict[str, Any]) -> str:
    """Format TypeScript element modifiers."""
    modifiers = []
    if element.get("is_static"):
        modifiers.append("static")
    if element.get("is_readonly"):
        modifiers.append("readonly")
    if element.get("is_abstract"):
        modifiers.append("abstract")
    return " ".join(modifiers)


def create_full_signature(method: dict[str, Any]) -> str:
    """Create full TypeScript method signature."""
    params_str = ", ".join(
        _full_parameter_text(param) for param in method.get("parameters", [])
    )
    return_type = str(method.get("return_type", "any"))
    return f"({params_str}):{return_type}"


def create_compact_signature(method: dict[str, Any]) -> str:
    """Create compact TypeScript method signature."""
    param_types = []
    for param in method.get("parameters", []):
        if isinstance(param, dict):
            param_types.append(str(param.get("type", "any")))
        else:
            param_types.append(str(param))

    params_str = ",".join(param_types)
    return_type = str(method.get("return_type", "any"))
    return f"({params_str}):{return_type}"


def create_csv_signature(method: dict[str, Any]) -> str:
    """Create CSV TypeScript method signature with full parameter details."""
    return create_full_signature(method)


def format_method_row(formatter: Any, method: dict[str, Any]) -> str:
    """Format a TypeScript method table row."""
    name = str(method.get("name", ""))
    signature = create_full_signature(method)
    visibility = formatter.convert_visibility(str(method.get("visibility", "public")))
    line_range = method.get("line_range", {})
    complexity = method.get("complexity_score", 0)
    doc = _doc_summary(formatter, method)

    return (
        f"| {name} | {signature} | {visibility} | {line_range_text(line_range)} | "
        f"{complexity} | {doc} |"
    )


def grouped_class_methods(
    methods: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group methods into constructor, public, protected, and private buckets."""
    grouped = {
        "constructors": [],
        "public": [],
        "protected": [],
        "private": [],
    }
    for method in methods:
        if method.get("is_constructor", False):
            grouped["constructors"].append(method)
            continue

        visibility = str(method.get("visibility", "public")).lower()
        if visibility == "private":
            grouped["private"].append(method)
        elif visibility == "protected":
            grouped["protected"].append(method)
        else:
            grouped["public"].append(method)
    return grouped


def trim_trailing_blank_lines(lines: list[str]) -> None:
    """Remove trailing blank lines in-place."""
    while lines and lines[-1] == "":
        lines.pop()


def doc_summary(formatter: Any, element: dict[str, Any]) -> str:
    """Return a formatter-compatible documentation summary."""
    return _doc_summary(formatter, element)


def _members_in_range(
    members: list[dict[str, Any]], line_range: dict[str, int]
) -> list[dict[str, Any]]:
    start = line_range.get("start", 0)
    end = line_range.get("end", 0)
    return [
        member
        for member in members
        if start <= (member.get("line_range") or {}).get("start", 0) <= end
    ]


def _full_parameter_text(param: Any) -> str:
    if not isinstance(param, dict):
        return str(param)

    param_name = str(param.get("name", ""))
    param_type = str(param.get("type", "any"))
    modifiers = param.get("modifiers", [])
    modifier_text = " ".join(str(modifier) for modifier in modifiers)
    prefix = f"{modifier_text} " if modifier_text else ""
    return f"{prefix}{param_name}:{param_type}"


def _doc_summary(formatter: Any, element: dict[str, Any]) -> str:
    return (
        formatter.extract_doc_summary(
            str(element.get("javadoc", "") or element.get("doc", ""))
        )
        or "-"
    )
