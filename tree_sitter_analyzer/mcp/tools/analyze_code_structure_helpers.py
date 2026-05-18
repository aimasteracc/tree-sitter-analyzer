#!/usr/bin/env python3
"""
Shared helpers for analyze_code_structure_tool.

Extracted from the monolithic tool file to reduce duplication.
"""

from typing import Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)

# JSON Schema: input validation for analyze_code_structure tool
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        # Required: file path to analyze
        "file_path": {"type": "string"},
        # Output format: full, compact, or csv
        "format_type": {
            "type": "string",
            "enum": ["full", "compact", "csv"],
            "default": "full",
        },
        "language": {"type": "string"},
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
        "output_file": {
            "type": "string",
            "description": "Optional base filename for saving formatted output",
        },
        "suppress_output": {
            "type": "boolean",
            "default": False,
            "description": "If true with output_file, suppress table_output in response to save tokens",
        },
    },
    # file_path is the only required field
    "required": ["file_path"],
    "additionalProperties": False,
}


# convert_analysis_result_to_dict: implementation
def convert_analysis_result_to_dict(
    result: Any,
    get_method_parameters: Any,
    get_method_modifiers: Any,
    get_field_modifiers: Any,
) -> dict[str, Any]:
    """Convert AnalysisResult to dictionary format expected by TableFormatter."""
    classes = [e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)]
    methods = [
        e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
    ]
    fields = [
        e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
    ]
    imports = [e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)]
    packages = [
        e for e in result.elements if is_element_of_type(e, ELEMENT_TYPE_PACKAGE)
    ]

    package_info = {"name": packages[0].name} if packages else None

    return {
        "success": True,
        "file_path": result.file_path,
        "language": result.language,
        "package": package_info,
        "classes": [_convert_class(cls) for cls in classes],
        "methods": [
            _convert_method(m, get_method_parameters, get_method_modifiers)
            for m in methods
        ],
        "fields": [_convert_field(f, get_field_modifiers) for f in fields],
        "imports": [_convert_import(imp) for imp in imports],
        "statistics": {
            "class_count": len(classes),
            "method_count": len(methods),
            "field_count": len(fields),
            "import_count": len(imports),
            "total_lines": result.line_count,
        },
    }


# _convert_class: implementation
def _convert_class(cls: Any) -> dict[str, Any]:
    return {
        "name": getattr(cls, "name", "unknown"),
        "line_range": {
            "start": getattr(cls, "start_line", 0),
            "end": getattr(cls, "end_line", 0),
        },
        "type": getattr(cls, "class_type", "class"),
        "visibility": "public",
        "extends": getattr(cls, "extends_class", None),
        "implements": getattr(cls, "implements_interfaces", []),
        "annotations": [],
    }


# _convert_method: implementation
def _convert_method(method: Any, get_params: Any, get_mods: Any) -> dict[str, Any]:
    return {
        "name": getattr(method, "name", "unknown"),
        "line_range": {
            "start": getattr(method, "start_line", 0),
            "end": getattr(method, "end_line", 0),
        },
        "return_type": getattr(method, "return_type", "void"),
        "parameters": get_params(method),
        "visibility": getattr(method, "visibility", "public"),
        "is_static": getattr(method, "is_static", False),
        "is_constructor": getattr(method, "is_constructor", False),
        "complexity_score": getattr(method, "complexity_score", 0),
        "modifiers": get_mods(method),
        "annotations": [],
    }


# _convert_field: implementation
def _convert_field(field: Any, get_mods: Any) -> dict[str, Any]:
    return {
        "name": getattr(field, "name", "unknown"),
        "type": getattr(field, "field_type", "Object"),
        "line_range": {
            "start": getattr(field, "start_line", 0),
            "end": getattr(field, "end_line", 0),
        },
        "visibility": getattr(field, "visibility", "private"),
        "modifiers": get_mods(field),
        "annotations": [],
    }


# _convert_import: implementation
def _convert_import(imp: Any) -> dict[str, Any]:
    return {
        "name": getattr(imp, "name", "unknown"),
        "statement": getattr(imp, "import_statement", getattr(imp, "name", "")),
        "is_static": getattr(imp, "is_static", False),
        "is_wildcard": getattr(imp, "is_wildcard", False),
    }
