"""Structural extractor helpers for analyze_scale — Phase 3 REQ-CLEAN-004.

Extracted from analyze_scale_helpers.py.
"""

from __future__ import annotations

from typing import Any

from ....constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)

# Output size caps
METHODS_OUTPUT_CAP = 50
HOTSPOTS_OUTPUT_CAP = 50

# Complexity threshold for hotspot reporting
_COMPLEXITY_HOTSPOT_THRESHOLD = 8


def extract_structural_overview(
    analysis_result: Any,
    *,
    method_cap: int = METHODS_OUTPUT_CAP,
    hotspot_cap: int = HOTSPOTS_OUTPUT_CAP,
) -> dict[str, Any]:
    """Extract structural overview with position information for LLM guidance.

    r37bd (dogfood): tool flagged this at 112 lines. Split into 4
    per-element-type extractors that each return a list of dicts.
    Behaviour preserved (complexity_score >= 8 hotspot threshold,
    same shape for each element category).
    """
    elements = analysis_result.elements
    overview: dict[str, Any] = {
        "classes": _extract_class_infos(elements),
        "methods": [],  # filled below alongside complexity_hotspots
        "fields": _extract_field_infos(elements),
        "imports": _extract_import_infos(elements),
        "complexity_hotspots": [],
    }
    all_methods, hotspots = _extract_method_infos(elements)
    _apply_hotspot_cap(overview, hotspots, hotspot_cap)
    total_methods = len(all_methods)
    overview["total_methods"] = total_methods
    if total_methods > method_cap:
        overview["methods"] = all_methods[:method_cap]
        overview["methods_truncated"] = True
    else:
        overview["methods"] = all_methods
    return overview


def _extract_class_infos(elements: list[Any]) -> list[dict[str, Any]]:
    """Class element → dict with position + inheritance + annotations."""
    classes = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_CLASS)]
    return [
        {
            "name": cls.name,
            "type": cls.class_type,
            "start_line": cls.start_line,
            "end_line": cls.end_line,
            "line_span": cls.end_line - cls.start_line + 1,
            "visibility": cls.visibility,
            "extends": cls.extends_class,
            "implements": cls.implements_interfaces,
            "annotations": [ann.name for ann in cls.annotations],
        }
        for cls in classes
    ]


def _extract_method_infos(
    elements: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Method element → (method_infos, complexity_hotspots) with threshold ≥8."""
    method_infos: list[dict[str, Any]] = []
    hotspots: list[dict[str, Any]] = []
    for method in (e for e in elements if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)):
        method_infos.append(
            {
                "name": method.name,
                "start_line": method.start_line,
                "end_line": method.end_line,
                "line_span": method.end_line - method.start_line + 1,
                "visibility": method.visibility,
                "return_type": method.return_type,
                "parameter_count": len(method.parameters),
                "complexity": method.complexity_score,
                "is_constructor": method.is_constructor,
                "is_static": method.is_static,
                "annotations": [ann.name for ann in method.annotations],
            }
        )
        if method.complexity_score >= _COMPLEXITY_HOTSPOT_THRESHOLD:
            hotspots.append(
                {
                    "type": "method",
                    "name": method.name,
                    "complexity": method.complexity_score,
                    "start_line": method.start_line,
                    "end_line": method.end_line,
                }
            )
    return method_infos, hotspots


def _apply_hotspot_cap(
    overview: dict[str, Any], hotspots: list[dict[str, Any]], hotspot_cap: int
) -> None:
    """Cap hotspot payloads and expose metadata only when truncation occurs."""
    total_hotspots = len(hotspots)
    if total_hotspots > hotspot_cap:
        overview["complexity_hotspots"] = hotspots[:hotspot_cap]
        overview["total_complexity_hotspots"] = total_hotspots
        overview["complexity_hotspots_truncated"] = True
    else:
        overview["complexity_hotspots"] = hotspots


def _extract_field_infos(elements: list[Any]) -> list[dict[str, Any]]:
    """Field element → dict with type + modifiers + position."""
    fields = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)]
    return [
        {
            "name": field.name,
            "type": field.field_type,
            "start_line": field.start_line,
            "end_line": field.end_line,
            "visibility": field.visibility,
            "is_static": field.is_static,
            "is_final": field.is_final,
            "annotations": [ann.name for ann in field.annotations],
        }
        for field in fields
    ]


def _extract_import_infos(elements: list[Any]) -> list[dict[str, Any]]:
    """Import element → dict with statement + static/wildcard flags."""
    imports = [e for e in elements if is_element_of_type(e, ELEMENT_TYPE_IMPORT)]
    return [
        {
            "name": imp.imported_name,
            "statement": imp.import_statement,
            "line": imp.line_number,
            "is_static": imp.is_static,
            "is_wildcard": imp.is_wildcard,
        }
        for imp in imports
    ]


# r37bd: complexity threshold for hotspot reporting — extracted from the
# inline ``>= 8`` literal so tests can pin it as a single source of truth.
_COMPLEXITY_HOTSPOT_THRESHOLD = 8


def _make_hotspot_entry(
    name: str, complexity: Any, start_line: int, end_line: int
) -> dict[str, Any]:
    """Build a complexity hotspot dict for a method element."""
    return {
        "type": "method",
        "name": name,
        "complexity": complexity,
        "start_line": start_line,
        "end_line": end_line,
    }


# Universal extraction for non-Java/Python languages using tree-sitter
def extract_structural_overview_universal(
    analysis_result: Any,
    *,
    method_cap: int = METHODS_OUTPUT_CAP,
    hotspot_cap: int = HOTSPOTS_OUTPUT_CAP,
) -> dict[str, Any]:
    """Extract structural overview from universal analysis result (non-Java languages).

    Bug #755: the methods list is capped at ``method_cap`` entries (default
    ``METHODS_OUTPUT_CAP`` = 50) to prevent multi-MB output for large files.
    When the cap fires, two extra fields appear:
      - ``total_methods``: the full method count (always present)
      - ``methods_truncated``: True (only when the list was cut)
    """
    # Initialize empty overview containers
    overview: dict[str, Any] = {
        "classes": [],
        "methods": [],
        "fields": [],
        "imports": [],
        "complexity_hotspots": [],
    }
    # Extract structural overview from tree-sitter elements

    # Guard against empty or invalid analysis results
    if not analysis_result or not hasattr(analysis_result, "elements"):
        overview["total_methods"] = 0
        return overview

    # Pre-bind lists to avoid deep subscript chains inside the loop
    _classes = overview["classes"]
    _all_methods: list[dict[str, Any]] = []
    _fields = overview["fields"]
    _imports = overview["imports"]
    _hotspots: list[dict[str, Any]] = []

    # Classify each element by its type and extract metadata
    for e in analysis_result.elements:
        etype = getattr(e, "element_type", "")
        name = getattr(e, "name", "unnamed")
        start_line = getattr(e, "start_line", 0)
        end_line = getattr(e, "end_line", 0)
        _line_span = end_line - start_line + 1
        _complexity_score = getattr(e, "complexity_score", 0)

        if etype == "class":
            _classes.append(
                {
                    "name": name,
                    "type": etype,
                    "start_line": start_line,
                    "end_line": end_line,
                    "line_span": _line_span,
                }
            )
        elif etype in ("function", "method"):
            method_info = {
                "name": name,
                "start_line": start_line,
                "end_line": end_line,
                "line_span": _line_span,
                "complexity": _complexity_score,
            }
            _all_methods.append(method_info)
            _entry = _make_hotspot_entry(name, _complexity_score, start_line, end_line)
            if _complexity_score and _complexity_score >= _COMPLEXITY_HOTSPOT_THRESHOLD:
                _hotspots.append(_entry)
        elif etype == "variable":
            _fields.append(
                {"name": name, "start_line": start_line, "end_line": end_line}
            )
        elif etype == "import":
            _imports.append({"name": name, "line": start_line})

    # Apply output cap (Bug #755)
    total_methods = len(_all_methods)
    overview["total_methods"] = total_methods
    if total_methods > method_cap:
        overview["methods"] = _all_methods[:method_cap]
        overview["methods_truncated"] = True
    else:
        overview["methods"] = _all_methods
    _apply_hotspot_cap(overview, _hotspots, hotspot_cap)

    return overview


# AI-oriented suggestions based on file analysis
# r37bd: per-language tree-sitter query priorities — extracted from the
# 65-line inline dict that drove a chunk of the long_method smell. New
# languages add a single dict entry; the guidance generator stays small.
_LANG_QUERIES: dict[str, list[str]] = {
    "java": ["methods", "classes", "imports", "spring_service", "jpa_entity"],
    "python": ["functions", "classes", "imports", "decorator", "async_patterns"],
    "javascript": ["functions", "classes", "imports", "export", "react_component"],
    "typescript": ["functions", "interfaces", "type_aliases", "enums", "decorators"],
    "go": ["function", "struct", "interface", "goroutine", "channel_send"],
    "rust": ["fn", "struct", "enum", "trait", "impl"],
    "c": ["function", "struct", "enum", "include", "typedef"],
    "cpp": ["class", "function", "namespace", "template", "include"],
    "kotlin": [
        "function",
        "class",
        "data_class",
        "object",
        "annotation",
        "companion_object",
        "sealed_class",
        "suspend_function",
        "extension_function",
        "when_expression",
    ],
    "csharp": ["class", "method", "property", "interface", "attribute"],
    "ruby": [
        "methods",
        "classes",
        "imports",
        "attr",
        "mixin",
        "inheritance",
        "block",
        "rescue",
        "yield",
    ],
    "php": [
        "methods",
        "classes",
        "imports",
        "namespace",
        "interface",
        "trait",
        "enum",
        "closure",
        "inheritance",
    ],
    "sql": ["functions", "table", "view", "trigger"],
    "html": ["element", "attribute", "form"],
    "css": ["selector", "property", "at_rule"],
    "yaml": ["key", "document", "anchor"],
    "markdown": ["headers", "code_blocks", "tables"],
}

_PRIORITY_QUERIES = frozenset(
    {
        "classes",
        "methods",
        "functions",
        "imports",
        "variables",
        "interface",
        "trait",
        "namespace",
        "decorator",
    }
)

_REQUIRED_OVERVIEW_FIELDS = (
    "complexity_hotspots",
    "classes",
    "methods",
    "fields",
    "imports",
)
