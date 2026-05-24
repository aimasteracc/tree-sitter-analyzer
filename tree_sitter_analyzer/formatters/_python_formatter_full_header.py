"""Header and metadata sections for Python full formatter output."""

from typing import Any


def append_header(
    lines: list[str], data: dict[str, Any], functions: list[dict[str, Any]]
) -> None:
    file_path = data.get("file_path", "Unknown")
    if file_path is None:
        file_path = "Unknown"
    file_name = str(file_path).split("/")[-1].split("\\")[-1]
    module_name = file_name.replace(".py", "").replace(".pyw", "").replace(".pyi", "")

    if "__init__.py" in file_name:
        lines.append(f"# Package: {module_name}")
    elif _is_script(functions):
        lines.append(f"# Script: {module_name}")
    else:
        lines.append(f"# Module: {module_name}")
    lines.append("")


def _is_script(functions: list[dict[str, Any]]) -> bool:
    return any(
        "if __name__ == '__main__'" in func.get("raw_text", "") for func in functions
    )


def append_module_docstring(
    lines: list[str], formatter: Any, data: dict[str, Any]
) -> None:
    module_docstring = formatter._extract_module_docstring(data)
    if module_docstring:
        lines.append("## Description")
        lines.append(f'"{module_docstring}"')
        lines.append("")


def append_package_info(lines: list[str], data: dict[str, Any]) -> None:
    package_info = data.get("package") or {}
    package_name = package_info.get("name", "unknown")
    if package_name and package_name != "unknown":
        lines.append("## Package")
        lines.append(f"`{package_name}`")
        lines.append("")


def append_imports(lines: list[str], imports: list[dict[str, Any]]) -> None:
    if not imports:
        return

    lines.append("## Imports")
    lines.append("```python")
    for imp in imports:
        lines.append(_import_statement(imp))
    lines.append("```")
    lines.append("")


def _import_statement(imp: dict[str, Any]) -> str:
    import_statement = imp.get("raw_text", "")
    if import_statement:
        return str(import_statement)

    module_name = imp.get("module_name", "")
    name = imp.get("name", "")
    if module_name:
        return f"from {module_name} import {name}"
    return f"import {name}"
