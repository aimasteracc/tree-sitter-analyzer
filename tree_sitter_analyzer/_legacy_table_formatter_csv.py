"""CSV helpers for the legacy table formatter."""

from __future__ import annotations

import csv
import io
from typing import Any


def format_csv(data: dict[str, Any]) -> str:
    """Format structure data as legacy CSV output."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    writer.writerow(
        [
            "Type",
            "Name",
            "ReturnType",
            "Parameters",
            "Access",
            "Static",
            "Final",
            "Line",
        ]
    )

    for cls in data.get("classes", []) or []:
        writer.writerow(
            [
                str(cls.get("type", "class")),
                str(cls.get("name", "Unknown")),
                "",
                "",
                str(cls.get("visibility", "public")),
                "false",
                "true" if "final" in cls.get("modifiers", []) else "false",
                cls.get("line_range", {}).get("start", 0),
            ]
        )

    for method in data.get("methods", []):
        _write_csv_method_row(writer, method)

    for field in data.get("fields", []):
        _write_csv_field_row(writer, field)

    csv_content = output.getvalue()
    csv_content = csv_content.replace("\r\n", "\n").replace("\r", "\n")
    csv_content = csv_content.rstrip("\n")
    output.close()
    return csv_content


def _write_csv_method_row(writer: Any, method: dict[str, Any]) -> None:
    """Write one legacy CSV method row."""
    modifiers = method.get("modifiers", [])
    is_static = "static" in modifiers or method.get("is_static", False)
    is_final = "final" in modifiers or method.get("is_final", False)

    writer.writerow(
        [
            "constructor" if method.get("is_constructor", False) else "method",
            str(method.get("name", "")),
            str(method.get("return_type", "void")),
            _csv_parameters(method.get("parameters", [])),
            str(method.get("visibility", "public")),
            "true" if is_static else "false",
            "true" if is_final else "false",
            method.get("line_range", {}).get("start", 0),
        ]
    )


def _write_csv_field_row(writer: Any, field: dict[str, Any]) -> None:
    """Write one legacy CSV field row."""
    modifiers = field.get("modifiers", [])
    is_static = "static" in modifiers or field.get("is_static", False)
    is_final = "final" in modifiers or field.get("is_final", False)

    writer.writerow(
        [
            "field",
            str(field.get("name", "")),
            str(field.get("type", "Object")),
            "",
            str(field.get("visibility", "private")),
            "true" if is_static else "false",
            "true" if is_final else "false",
            field.get("line_range", {}).get("start", 0),
        ]
    )


def _csv_parameters(params: list[Any]) -> str:
    """Format legacy CSV parameter strings."""
    return ";".join(_csv_parameter(param) for param in params)


def _csv_parameter(param: Any) -> str:
    """Format one legacy CSV parameter."""
    if isinstance(param, dict):
        param_type = str(param.get("type", "Object"))
        param_name = str(param.get("name", "param"))
        return f"{param_name}:{param_type}"

    if isinstance(param, str):
        parts = param.strip().split()
        if len(parts) >= 2:
            param_type = " ".join(parts[:-1])
            param_name = parts[-1]
            return f"{param_name}:{param_type}"
        return param

    return str(param)
