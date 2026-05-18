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


# count_elements_by_type: implementation
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
    # Loop iteration
    for e in elements:
        # Conditional check
        if is_element_of_type(e, ELEMENT_TYPE_CLASS):
            counts["classes"] += 1
        # Alternative check
        elif is_element_of_type(e, ELEMENT_TYPE_FUNCTION):
            counts["methods"] += 1
        # Alternative check
        elif is_element_of_type(e, ELEMENT_TYPE_VARIABLE):
            counts["fields"] += 1
        # Alternative check
        elif is_element_of_type(e, ELEMENT_TYPE_IMPORT):
            counts["imports"] += 1
        # Alternative check
        elif is_element_of_type(e, ELEMENT_TYPE_PACKAGE):
            counts["packages"] += 1
    counts["annotations"] = (
        len(getattr(elements, "annotations", []))
        if hasattr(elements, "annotations")
        else 0
    )
    counts["total"] = sum(v for k, v in counts.items() if k != "annotations")
    return counts


# elements_to_summary: implementation
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


# count_dict_elements_by_type: implementation
def count_dict_elements_by_type(elements: list[Any]) -> dict[str, int]:
    """Count elements from universal analyzer dict-based results."""
    counts: dict[str, int] = {
        "classes": 0,
        "methods": 0,
        "fields": 0,
        "imports": 0,
        "annotations": 0,
    }
    # Loop iteration
    for e in elements:
        etype = getattr(e, "element_type", None)
        # Conditional check
        if etype == "class":
            counts["classes"] += 1
        # Alternative check
        elif etype == "function":
            counts["methods"] += 1
        # Alternative check
        elif etype == "variable":
            counts["fields"] += 1
        # Alternative check
        elif etype == "import":
            counts["imports"] += 1
    return counts


# JSON Schema: input validation for universal_analyze tool
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        # Required: file path to the source file
        "file_path": {
            "type": "string",
            "description": "Path to the code file to analyze",
        },
        # Optional: override auto-detected language
        "language": {
            "type": "string",
            "description": "Programming language (optional, auto-detected if not specified)",
        },
        # Analysis depth: basic, detailed, structure, or metrics
        "analysis_type": {
            "type": "string",
            "enum": ["basic", "detailed", "structure", "metrics"],
            "description": "Type of analysis to perform",
            "default": "basic",
        },
        # Include raw AST nodes in response
        "include_ast": {
            "type": "boolean",
            "description": "Include AST information in the analysis",
            "default": False,
        },
        # Include available tree-sitter queries for the language
        "include_queries": {
            "type": "boolean",
            "description": "Include available query information",
            "default": False,
        },
        # Token-efficient toon format by default
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "description": "Output format: 'toon' (default, 50-70% token reduction) or 'json'",
            "default": "toon",
        },
    },
    # file_path is the only required field
    "required": ["file_path"],
    "additionalProperties": False,
}
