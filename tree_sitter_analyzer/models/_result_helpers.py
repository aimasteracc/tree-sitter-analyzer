#!/usr/bin/env python3
"""
Private MCP serialisation and dict-conversion helpers for AnalysisResult.

These are internal to the models package. They are re-exported via
``models/__init__.py`` for any code that already imported them directly from
``tree_sitter_analyzer.models``.
"""

from collections.abc import Sequence
from typing import Any

from ..constants import (
    ELEMENT_TYPE_ANNOTATION,
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)


def _safe_get_attr(obj: Any, attr: str, default: Any = "") -> Any:
    """Read ``attr`` from an object or dict, falling back to ``default``.

    r37bo: extracted from ``to_mcp_format`` closure so the per-element
    helpers below can share one definition.
    """
    if hasattr(obj, attr):
        return getattr(obj, attr)
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return default


def _mcp_package_info(package: Any) -> dict[str, Any] | None:
    """Normalise the package field for MCP output."""
    if not package:
        return None
    if hasattr(package, "name"):
        return {"name": package.name}
    if isinstance(package, dict):
        return package
    return {"name": str(package)}


def _mcp_line_range(obj: Any) -> dict[str, int]:
    """Canonical ``{start, end}`` from any element-like object."""
    return {
        "start": _safe_get_attr(obj, "start_line", 0),
        "end": _safe_get_attr(obj, "end_line", 0),
    }


def _mcp_import_entries(elements: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": _safe_get_attr(imp, "name"),
            "is_static": _safe_get_attr(imp, "is_static", False),
            "is_wildcard": _safe_get_attr(imp, "is_wildcard", False),
            "line_range": _mcp_line_range(imp),
        }
        for imp in elements
        if is_element_of_type(imp, ELEMENT_TYPE_IMPORT)
    ]


def _mcp_class_entries(elements: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": _safe_get_attr(cls, "name"),
            "type": _safe_get_attr(cls, "class_type"),
            "package": _safe_get_attr(cls, "package_name"),
            "line_range": _mcp_line_range(cls),
        }
        for cls in elements
        if is_element_of_type(cls, ELEMENT_TYPE_CLASS)
    ]


def _mcp_method_entries(elements: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": _safe_get_attr(method, "name"),
            "return_type": _safe_get_attr(method, "return_type"),
            "parameters": _safe_get_attr(method, "parameters", []),
            "line_range": _mcp_line_range(method),
        }
        for method in elements
        if is_element_of_type(method, ELEMENT_TYPE_FUNCTION)
    ]


def _mcp_field_entries(elements: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": _safe_get_attr(field, "name"),
            "type": _safe_get_attr(field, "field_type"),
            "line_range": _mcp_line_range(field),
        }
        for field in elements
        if is_element_of_type(field, ELEMENT_TYPE_VARIABLE)
    ]


def _mcp_annotation_entries(elements: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": _safe_get_attr(ann, "name"),
            "line_range": _mcp_line_range(ann),
        }
        for ann in elements
        if is_element_of_type(ann, ELEMENT_TYPE_ANNOTATION)
    ]


def _mcp_metadata_block(
    elements: Sequence[Any],
    *,
    line_count: int,
    analysis_time: float,
    success: bool,
    error_message: str | None,
) -> dict[str, Any]:
    """Element-type counts + analysis flags — paired with ``to_mcp_format``."""
    return {
        "line_count": line_count,
        "class_count": sum(
            1 for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)
        ),
        "method_count": sum(
            1 for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
        ),
        "field_count": sum(
            1 for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
        ),
        "import_count": sum(
            1 for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)
        ),
        "annotation_count": sum(
            1 for e in elements if is_element_of_type(e, ELEMENT_TYPE_ANNOTATION)
        ),
        "analysis_time": analysis_time,
        "success": success,
        "error_message": error_message,
    }


def _group_elements_by_type(
    elements: Any,
) -> dict[str, list[Any]]:
    """Single-pass partition of ``elements`` by their ``element_type``.

    Returns a dict keyed by the canonical type constants (class /
    function / variable / import / package / annotation). Unknown
    element types are silently dropped (not added to any bucket).

    r37e7 (dogfood): lifted from ``AnalysisResult.to_dict`` to flatten
    the long_method warning.
    """
    from ..constants import (
        ELEMENT_TYPE_ANNOTATION,
        ELEMENT_TYPE_CLASS,
        ELEMENT_TYPE_FUNCTION,
        ELEMENT_TYPE_IMPORT,
        ELEMENT_TYPE_VARIABLE,
        get_element_type,
    )

    grouped: dict[str, list[Any]] = {
        ELEMENT_TYPE_CLASS: [],
        ELEMENT_TYPE_FUNCTION: [],
        ELEMENT_TYPE_VARIABLE: [],
        ELEMENT_TYPE_IMPORT: [],
        ELEMENT_TYPE_PACKAGE: [],
        ELEMENT_TYPE_ANNOTATION: [],
    }
    for e in elements:
        etype = get_element_type(e)
        if etype in grouped:
            grouped[etype].append(e)
    return grouped


def _to_dict_import_row(imp: Any) -> dict[str, Any]:
    """Build the legacy import dict row used by ``AnalysisResult.to_dict``."""
    return {
        "name": imp.name,
        "is_static": getattr(imp, "is_static", False),
        "is_wildcard": getattr(imp, "is_wildcard", False),
    }


def _to_dict_class_row(cls: Any) -> dict[str, Any]:
    """Build the legacy class dict row (name + type + package)."""
    return {
        "name": cls.name,
        "type": getattr(cls, "class_type", "class"),
        "package": getattr(cls, "package_name", None),
    }


def _to_dict_method_row(method: Any) -> dict[str, Any]:
    """Build the legacy method dict row (name + return_type + parameters)."""
    return {
        "name": method.name,
        "return_type": getattr(method, "return_type", None),
        "parameters": getattr(method, "parameters", []),
    }


def _to_dict_field_row(field: Any) -> dict[str, Any]:
    """Build the legacy field dict row (name + type)."""
    return {"name": field.name, "type": getattr(field, "field_type", None)}


def _to_dict_annotation_row(ann: Any) -> dict[str, Any]:
    """Build the legacy annotation dict row (name only; falls back to str)."""
    return {"name": getattr(ann, "name", str(ann))}


__all__ = [
    "_safe_get_attr",
    "_mcp_package_info",
    "_mcp_line_range",
    "_mcp_import_entries",
    "_mcp_class_entries",
    "_mcp_method_entries",
    "_mcp_field_entries",
    "_mcp_annotation_entries",
    "_mcp_metadata_block",
    "_group_elements_by_type",
    "_to_dict_import_row",
    "_to_dict_class_row",
    "_to_dict_method_row",
    "_to_dict_field_row",
    "_to_dict_annotation_row",
]
