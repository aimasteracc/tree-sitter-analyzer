"""Shared helpers for the legacy table formatter."""

from __future__ import annotations

import os
from typing import Any


def get_platform_newline() -> str:
    """Get platform-specific newline character."""
    return "\r\n" if os.name == "nt" else "\n"


def get_visibility_symbol(visibility: str) -> str:
    """Convert visibility to a legacy compact-table symbol."""
    symbols = {
        "public": "+",
        "private": "-",
        "protected": "#",
        "package": "~",
        "internal": "~",
    }
    return symbols.get(visibility.lower(), "+")


def create_full_signature(method: dict[str, Any]) -> str:
    """Create a complete legacy method signature."""
    params = method.get("parameters", [])
    param_strs = []
    for param in params:
        if isinstance(param, dict):
            param_type = str(param.get("type", "Object"))
            param_name = str(param.get("name", "param"))
            param_strs.append(f"{param_name}:{param_type}")
        elif isinstance(param, str):
            param_strs.append(param)
        else:
            param_strs.append(str(param))

    params_str = ",".join(param_strs)
    return_type = str(method.get("return_type", "void"))

    modifiers = []
    if method.get("is_static", False):
        modifiers.append("[static]")

    modifier_str = " ".join(modifiers)
    signature = f"({params_str}):{return_type}"

    if modifier_str:
        signature += f" {modifier_str}"

    return signature


def shorten_type(type_name: Any) -> str:
    """Shorten a type name using the legacy full-table mapping."""
    if type_name is None:
        return "O"

    if not isinstance(type_name, str):
        type_name = str(type_name)

    type_mapping = {
        "String": "S",
        "int": "i",
        "long": "l",
        "double": "d",
        "boolean": "b",
        "void": "void",
        "Object": "O",
        "Exception": "E",
        "SQLException": "SE",
        "IllegalArgumentException": "IAE",
        "RuntimeException": "RE",
    }

    if "Map<" in type_name:
        return str(
            type_name.replace("Map<", "M<")
            .replace("String", "S")
            .replace("Object", "O")
        )

    if "List<" in type_name:
        return str(type_name.replace("List<", "L<").replace("String", "S"))

    if "[]" in type_name:
        base_type = type_name.replace("[]", "")
        if base_type:
            return str(type_mapping.get(base_type, base_type[0].upper())) + "[]"
        return "O[]"

    return str(type_mapping.get(type_name, type_name))


def convert_visibility(visibility: str) -> str:
    """Convert visibility to a legacy full-table symbol."""
    mapping = {"public": "+", "private": "-", "protected": "#", "package": "~"}
    return mapping.get(visibility, visibility)


def extract_doc_summary(javadoc: str) -> str:
    """Extract the first JavaDoc sentence using legacy rules."""
    if not javadoc:
        return "-"

    clean_doc = javadoc.replace("/**", "").replace("*/", "").replace("*", "").strip()

    if clean_doc:
        sentences = clean_doc.split(".")
        if sentences:
            return sentences[0].strip()

    return "-"


def clean_csv_text(text: str) -> str:
    """Clean text for legacy CSV-compatible table cells."""
    if not text or text == "-":
        return "-"

    cleaned = " ".join(text.split())
    cleaned = cleaned.replace('"', '""')

    return cleaned
