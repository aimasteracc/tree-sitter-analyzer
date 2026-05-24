"""Full table output for the Python formatter."""

from typing import Any

from ._python_formatter_full_classes import append_class_sections, append_classes
from ._python_formatter_full_functions import append_module_functions, trim_blank_tail
from ._python_formatter_full_header import (
    append_header,
    append_imports,
    append_module_docstring,
    append_package_info,
)


def format_python_full_table(formatter: Any, data: dict[str, Any]) -> str:
    """Full table format for Python"""
    if data is None:
        raise TypeError("Cannot format None data")

    if not isinstance(data, dict):
        raise TypeError(f"Expected dict, got {type(data)}")

    lines: list[str] = []
    classes = data.get("classes", [])
    functions = data.get("functions", [])
    methods = data.get("methods", []) or functions

    append_header(lines, data, functions)
    append_module_docstring(lines, formatter, data)
    append_package_info(lines, data)
    append_imports(lines, data.get("imports", []))
    append_classes(lines, data, classes)
    append_class_sections(lines, formatter, classes, methods)
    append_module_functions(lines, formatter, classes, methods)
    trim_blank_tail(lines)

    return "\n".join(lines)
