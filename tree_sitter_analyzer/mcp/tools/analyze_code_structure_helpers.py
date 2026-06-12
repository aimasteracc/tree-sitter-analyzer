#!/usr/bin/env python3
"""
Shared helpers for analyze_code_structure_tool.

Extracted from the monolithic tool file so other MCP tools (notably
``universal_analyze``) can reuse the same per-element converters and emit the
same structure shape.
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

# --- default element-detail extractors --------------------------------
# These live here (not on the tool class) so both ``analyze_code_structure``
# and ``universal_analyze`` produce identical per-element dicts.


def get_method_modifiers(method: Any) -> list[str]:
    """Extract method modifiers (static, final, abstract)."""
    mods: list[str] = []
    if getattr(method, "is_static", False):
        mods.append("static")
    if getattr(method, "is_final", False):
        mods.append("final")
    if getattr(method, "is_abstract", False):
        mods.append("abstract")
    return mods


def get_field_modifiers(field: Any) -> list[str]:
    """Extract field modifiers (visibility, static, final)."""
    mods: list[str] = []
    visibility = getattr(field, "visibility", "private")
    if visibility and visibility != "package":
        mods.append(visibility)
    if getattr(field, "is_static", False):
        mods.append("static")
    if getattr(field, "is_final", False):
        mods.append("final")
    return mods


def convert_parameters(parameters: Any) -> list[dict[str, str]]:
    """Convert method parameters to dict format."""
    result: list[dict[str, str]] = []
    for param in parameters:
        if isinstance(param, dict):
            result.append(
                {
                    "name": param.get("name", "param"),
                    "type": param.get("type", "Object"),
                }
            )
        else:
            result.append(
                {
                    "name": getattr(param, "name", "param"),
                    "type": getattr(param, "param_type", "Object"),
                }
            )
    return result


def get_method_parameters(method: Any) -> list[dict[str, str]]:
    """Extract method parameters with types."""
    parameters = getattr(method, "parameters", [])
    if parameters and isinstance(parameters[0], str):
        result: list[dict[str, str]] = []
        for param_str in parameters:
            entry = _parse_string_parameter(param_str)
            if entry:
                result.append(entry)
        return result
    return convert_parameters(parameters)


def _parse_string_parameter(param_str: str) -> dict[str, str] | None:
    """Parse one string-form parameter into ``{name, type[, default]}``.

    Handles the default-valued forms #533 introduced (Codex P2 on #581):
    ``limit = 10`` and ``breed: str = "Mixed"`` must not be whitespace-split
    into ``{"name": "10", "type": "limit ="}``.
    """
    text = param_str.strip()
    if not text:
        return None
    default: str | None = None
    if "=" in text:
        head, default = (s.strip() for s in text.split("=", 1))
    else:
        head = text
    if ":" in head:
        name, ptype = (s.strip() for s in head.split(":", 1))
    else:
        parts = head.split()
        if len(parts) >= 2:
            name, ptype = parts[-1], " ".join(parts[:-1])
        elif len(parts) == 1:
            # bare name (JS) — or bare type for legacy `Type` strings; the
            # default-bearing form is always a name.
            if default is not None:
                name, ptype = parts[0], "Any"
            else:
                name, ptype = "param", parts[0]
        else:
            return None
    entry: dict[str, str] = {"name": name, "type": ptype}
    if default is not None:
        entry["default"] = default
    return entry


# JSON Schema: input validation for analyze_code_structure tool
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        # Required: file path to analyze
        "file_path": {"type": "string"},
        # Structure-table style: full | compact | csv. NOT the response
        # envelope — that is ``output_format`` (json|toon) below. The
        # response echoes this as ``table_format`` (and ``format_type``
        # as a deprecated alias kept for one release).
        "format_type": {
            "type": "string",
            "enum": ["full", "compact", "csv"],
            "default": "full",
            "description": (
                "Structure-table style (full|compact|csv). Distinct from "
                "output_format which controls json|toon envelope."
            ),
        },
        "language": {"type": "string"},
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
            "description": "Response envelope format (json or toon).",
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


def convert_analysis_result_to_structure_dict(result: Any) -> dict[str, Any]:
    """Convert an :class:`AnalysisResult` to the rich structure dict.

    Thin wrapper around :func:`convert_analysis_result_to_dict` that wires up
    the default per-element extractors so both ``analyze_code_structure`` and
    ``universal_analyze`` emit the same per-element detail without passing
    helper callables.
    """
    return convert_analysis_result_to_dict(
        result,
        get_method_parameters,
        get_method_modifiers,
        get_field_modifiers,
    )


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


def extract_metadata(structure_dict: dict[str, Any]) -> dict[str, Any]:
    """Extract response metadata from the structure statistics block."""
    stats = structure_dict.get("statistics", {})

    def safe_int(value: Any) -> int:
        return value if isinstance(value, int) else 0

    return {
        "classes_count": safe_int(stats.get("class_count", 0)),
        "methods_count": safe_int(stats.get("method_count", 0)),
        "fields_count": safe_int(stats.get("field_count", 0)),
        "total_lines": safe_int(stats.get("total_lines", 0)),
    }


# _convert_class: implementation
def _resolve_class_extends(cls: Any) -> str | None:
    """Return the superclass name, checking both plugin spelling conventions.

    Java plugin sets ``extends_class``; JS/TS/Python/Ruby/PHP/C++/C#/Go
    plugins set ``superclass``.  Issue #530.
    """
    for attr in ("extends_class", "superclass"):
        v = getattr(cls, attr, None)
        # Strings only — Mock auto-attributes must not leak reprs (#560).
        if isinstance(v, str) and v:
            return v
    return None


def _resolve_class_implements(cls: Any) -> list[str]:
    """Return implemented interfaces, checking both plugin spelling conventions.

    Java/Rust plugins set ``implements_interfaces``; TS/Python/PHP/C++/C#/Go
    plugins set ``interfaces``.  Issue #530.
    """
    for attr in ("implements_interfaces", "interfaces"):
        v = getattr(cls, attr, None)
        if isinstance(v, (list, tuple)) and v:
            return [str(item) for item in v]
    return []


def _convert_class(cls: Any) -> dict[str, Any]:
    return {
        "name": getattr(cls, "name", "unknown"),
        "line_range": {
            "start": getattr(cls, "start_line", 0),
            "end": getattr(cls, "end_line", 0),
        },
        "type": getattr(cls, "class_type", "class"),
        "visibility": getattr(cls, "visibility", "public"),
        "extends": _resolve_class_extends(cls),
        "implements": _resolve_class_implements(cls),
        "annotations": getattr(cls, "annotations", []),
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
        "annotations": getattr(method, "annotations", []),
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
        "annotations": getattr(field, "annotations", []),
    }


# _convert_import: implementation
def _convert_import(imp: Any) -> dict[str, Any]:
    # ``raw_text`` and ``module_name`` are required so the formatter can
    # reconstruct ``from X import Y`` lines; without them the formatter falls
    # back to ``import {name}`` and silently drops the ``from`` prefix.
    return {
        "name": getattr(imp, "name", "unknown"),
        "statement": getattr(imp, "import_statement", getattr(imp, "name", "")),
        "raw_text": getattr(imp, "raw_text", ""),
        "module_name": getattr(imp, "module_name", ""),
        "is_static": getattr(imp, "is_static", False),
        "is_wildcard": getattr(imp, "is_wildcard", False),
    }
