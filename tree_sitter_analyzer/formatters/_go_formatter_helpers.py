"""Helper functions for the Go table formatter."""

from collections.abc import Callable
from typing import Any

DocExtractor = Callable[[str], str]
FunctionRowFormatter = Callable[[dict[str, Any]], str]
MethodRowFormatter = Callable[[dict[str, Any]], str]
PackageNameExtractor = Callable[[dict[str, Any]], str]
VisibilityResolver = Callable[[str], str]


def format_go_full_table(
    data: dict[str, Any],
    get_package_name: PackageNameExtractor,
    go_visibility: VisibilityResolver,
    extract_doc_summary: DocExtractor,
    format_func_row: FunctionRowFormatter,
    format_method_row: MethodRowFormatter,
) -> str:
    """Format full Go output while keeping section assembly isolated."""
    lines: list[str] = []
    package_name = get_package_name(data)

    _append_header(lines, data, package_name)
    _append_package_info(lines, data, package_name)
    _append_imports(lines, data.get("imports", []))
    _append_type_sections(
        lines, data.get("classes", []), go_visibility, extract_doc_summary
    )
    _append_function_sections(
        lines,
        data.get("functions", []) or data.get("methods", []),
        format_func_row,
        format_method_row,
    )
    _append_variable_sections(
        lines, data.get("variables", []) or data.get("fields", []), go_visibility
    )

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def _append_header(lines: list[str], data: dict[str, Any], package_name: str) -> None:
    file_name = str(data.get("file_path", "Unknown")).split("/")[-1].split("\\")[-1]
    if package_name:
        lines.append(f"# {package_name}/{file_name}")
    else:
        lines.append(f"# {file_name}")
    lines.append("")


def _append_package_info(
    lines: list[str], data: dict[str, Any], package_name: str
) -> None:
    lines.append("## Package Info")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| Package | {package_name or 'main'} |")

    stats = data.get("statistics") or {}
    lines.append(f"| Functions | {stats.get('function_count', 0)} |")
    lines.append(f"| Types | {stats.get('class_count', 0)} |")
    lines.append(f"| Variables | {stats.get('variable_count', 0)} |")
    lines.append("")


def _append_imports(lines: list[str], imports: list[dict[str, Any]]) -> None:
    if not imports:
        return

    lines.append("## Imports")
    lines.append("```go")
    for imp in imports:
        stmt = imp.get("import_statement", "") or imp.get("raw_text", "")
        if not stmt:
            continue

        stmt = stmt.strip()
        if not stmt.startswith("import"):
            stmt = f'import "{stmt}"'
        lines.append(stmt)
    lines.append("```")
    lines.append("")


def _append_type_sections(
    lines: list[str],
    classes: list[dict[str, Any]],
    go_visibility: VisibilityResolver,
    extract_doc_summary: DocExtractor,
) -> None:
    structs = [c for c in classes if c.get("type") == "struct"]
    interfaces = [c for c in classes if c.get("type") == "interface"]
    type_aliases = [c for c in classes if c.get("type") == "type_alias"]

    _append_structs(lines, structs, go_visibility, extract_doc_summary)
    _append_interfaces(lines, interfaces, go_visibility, extract_doc_summary)
    _append_type_aliases(lines, type_aliases, go_visibility)


def _append_structs(
    lines: list[str],
    structs: list[dict[str, Any]],
    go_visibility: VisibilityResolver,
    extract_doc_summary: DocExtractor,
) -> None:
    if not structs:
        return

    lines.append("## Structs")
    lines.append("| Name | Visibility | Lines | Embedded | Doc |")
    lines.append("|------|------------|-------|----------|-----|")
    for struct in structs:
        name = str(struct.get("name", ""))
        line_range = struct.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        embedded = ", ".join(str(i) for i in (struct.get("interfaces", []) or []))
        doc = extract_doc_summary(struct.get("docstring", "") or "")
        lines.append(
            f"| {name} | {go_visibility(name)} | {lines_str} | "
            f"{embedded or '-'} | {doc or '-'} |"
        )
    lines.append("")


def _append_interfaces(
    lines: list[str],
    interfaces: list[dict[str, Any]],
    go_visibility: VisibilityResolver,
    extract_doc_summary: DocExtractor,
) -> None:
    if not interfaces:
        return

    lines.append("## Interfaces")
    lines.append("| Name | Visibility | Lines | Doc |")
    lines.append("|------|------------|-------|-----|")
    for interface in interfaces:
        name = str(interface.get("name", ""))
        line_range = interface.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        doc = extract_doc_summary(interface.get("docstring", "") or "")
        lines.append(f"| {name} | {go_visibility(name)} | {lines_str} | {doc or '-'} |")
    lines.append("")


def _append_type_aliases(
    lines: list[str],
    type_aliases: list[dict[str, Any]],
    go_visibility: VisibilityResolver,
) -> None:
    if not type_aliases:
        return

    lines.append("## Type Aliases")
    lines.append("| Name | Visibility | Lines |")
    lines.append("|------|------------|-------|")
    for alias in type_aliases:
        name = str(alias.get("name", ""))
        line_range = alias.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        lines.append(f"| {name} | {go_visibility(name)} | {lines_str} |")
    lines.append("")


def _append_function_sections(
    lines: list[str],
    functions: list[dict[str, Any]],
    format_func_row: FunctionRowFormatter,
    format_method_row: MethodRowFormatter,
) -> None:
    funcs = [func for func in functions if not _is_go_method(func)]
    methods = [func for func in functions if _is_go_method(func)]

    _append_functions(lines, funcs, format_func_row)
    _append_methods(lines, methods, format_method_row)


def _is_go_method(func: dict[str, Any]) -> bool:
    return bool(getattr(func, "is_method", False) or func.get("is_method", False))


def _append_functions(
    lines: list[str],
    funcs: list[dict[str, Any]],
    format_func_row: FunctionRowFormatter,
) -> None:
    if not funcs:
        return

    lines.append("## Functions")
    lines.append("| Func | Signature | Vis | Lines | Doc |")
    lines.append("|------|-----------|-----|-------|-----|")
    for func in funcs:
        lines.append(format_func_row(func))
    lines.append("")


def _append_methods(
    lines: list[str],
    methods: list[dict[str, Any]],
    format_method_row: MethodRowFormatter,
) -> None:
    if not methods:
        return

    lines.append("## Methods")
    lines.append("| Receiver | Func | Signature | Vis | Lines | Doc |")
    lines.append("|----------|------|-----------|-----|-------|-----|")
    for method in methods:
        lines.append(format_method_row(method))
    lines.append("")


def _append_variable_sections(
    lines: list[str],
    variables: list[dict[str, Any]],
    go_visibility: VisibilityResolver,
) -> None:
    consts = [variable for variable in variables if variable.get("is_constant", False)]
    vars_list = [
        variable for variable in variables if not variable.get("is_constant", False)
    ]

    _append_variables(lines, "Constants", consts, go_visibility)
    _append_variables(lines, "Variables", vars_list, go_visibility)


def _append_variables(
    lines: list[str],
    title: str,
    variables: list[dict[str, Any]],
    go_visibility: VisibilityResolver,
) -> None:
    if not variables:
        return

    lines.append(f"## {title}")
    lines.append("| Name | Type | Vis | Line |")
    lines.append("|------|------|-----|------|")
    for variable in variables:
        name = str(variable.get("name", ""))
        var_type = variable.get("variable_type", "") or variable.get("type", "") or "-"
        line = variable.get("line_range", {}).get("start", 0)
        lines.append(f"| {name} | {var_type} | {go_visibility(name)} | {line} |")
    lines.append("")
