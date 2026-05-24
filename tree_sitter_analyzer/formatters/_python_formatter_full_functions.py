"""Function sections for Python full formatter output."""

from typing import Any


def append_module_functions(
    lines: list[str],
    formatter: Any,
    classes: list[dict[str, Any]],
    methods: list[dict[str, Any]],
) -> None:
    module_functions = _module_functions(classes, methods)
    if not module_functions:
        return

    lines.append("## Module Functions")
    lines.append("| Method | Signature | Vis | Lines | Cx | Doc |")
    lines.append("|--------|-----------|-----|-------|----|----| ")

    for method in module_functions:
        lines.append(formatter._format_class_method_row(method))
    lines.append("")


def _module_functions(
    classes: list[dict[str, Any]], methods: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not classes:
        return [method for method in methods if method is not None]

    module_functions = []
    for method in methods:
        if method is None:
            continue
        if not _is_in_any_class(method, classes):
            module_functions.append(method)
    return module_functions


def _is_in_any_class(method: dict[str, Any], classes: list[dict[str, Any]]) -> bool:
    method_start = (method.get("line_range") or {}).get("start", 0)
    for class_info in classes:
        if class_info is None:
            continue
        class_range = class_info.get("line_range") or {}
        if class_range.get("start", 0) <= method_start <= class_range.get("end", 0):
            return True
    return False


def trim_blank_tail(lines: list[str]) -> None:
    while lines and lines[-1] == "":
        lines.pop()
