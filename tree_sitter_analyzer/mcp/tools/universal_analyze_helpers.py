#!/usr/bin/env python3
"""
Shared helpers for universal_analyze tool.

Extracted from the monolithic tool file to reduce duplication.
"""

from __future__ import annotations

from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)


def count_elements_by_type(elements: list[Any]) -> dict[str, int]:
    """Count elements by their type."""
    counts: dict[str, int] = {
        "classes": 0,
        "methods": 0,
        "fields": 0,
        "imports": 0,
        "annotations": 0,
        "packages": 0,
    }
    for e in elements:
        if is_element_of_type(e, ELEMENT_TYPE_CLASS):
            counts["classes"] += 1
        elif is_element_of_type(e, ELEMENT_TYPE_FUNCTION):
            counts["methods"] += 1
        elif is_element_of_type(e, ELEMENT_TYPE_VARIABLE):
            counts["fields"] += 1
        elif is_element_of_type(e, ELEMENT_TYPE_IMPORT):
            counts["imports"] += 1
        elif is_element_of_type(e, ELEMENT_TYPE_PACKAGE):
            counts["packages"] += 1
    counts["annotations"] = (
        len(getattr(elements, "annotations", []))
        if hasattr(elements, "annotations")
        else 0
    )
    counts["total"] = sum(v for k, v in counts.items() if k != "annotations")
    return counts


def elements_to_summary(elements: list[Any], element_type: str) -> list[dict[str, Any]]:
    """Convert elements of a given type to summary items."""
    return [
        (
            e.to_summary_item()
            if hasattr(e, "to_summary_item")
            else {"name": getattr(e, "name", "unknown")}
        )
        for e in elements
        if is_element_of_type(e, element_type)
    ]


def count_dict_elements_by_type(elements: list[Any]) -> dict[str, int]:
    """Count elements from universal analyzer dict-based results."""
    counts: dict[str, int] = {
        "classes": 0,
        "methods": 0,
        "fields": 0,
        "imports": 0,
        "annotations": 0,
    }
    for e in elements:
        etype = getattr(e, "element_type", None)
        if etype == "class":
            counts["classes"] += 1
        elif etype == "function":
            counts["methods"] += 1
        elif etype == "variable":
            counts["fields"] += 1
        elif etype == "import":
            counts["imports"] += 1
    return counts


TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "Path to the code file to analyze",
        },
        "language": {
            "type": "string",
            "description": "Programming language (optional, auto-detected if not specified)",
        },
        "analysis_type": {
            "type": "string",
            "enum": ["basic", "detailed", "structure", "metrics"],
            "description": "Type of analysis to perform",
            "default": "basic",
        },
        "include_ast": {
            "type": "boolean",
            "description": "Include AST information in the analysis",
            "default": False,
        },
        "include_queries": {
            "type": "boolean",
            "description": "Include available query information",
            "default": False,
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "description": "Output format: 'toon' (default, 50-70% token reduction) or 'json'",
            "default": "toon",
        },
    },
    "required": ["file_path"],
    "additionalProperties": False,
}
