"""Result-shaping helpers for the public API facade."""

import dataclasses
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_OPTIONAL_ELEM_FIELDS = [
    "module_path",
    "module_name",
    "imported_names",
    "variable_type",
    "initializer",
    "is_constant",
    "parameters",
    "return_type",
    "is_async",
    "is_static",
    "is_constructor",
    "is_method",
    "is_abstract",
    "complexity_score",
    "superclass",
    # Theme-C (2026-06-10): implements/mixins were collected by plugins but
    # dropped here — agents never saw them.
    "interfaces",
    # Theme-A (2026-06-10): Go/Rust receiver binding — extractors filled
    # these but the allowlist dropped them; agents saw is_method=True with
    # no way to tell WHICH type owns the method.
    "receiver",
    "receiver_type",
    "class_type",
    "visibility",
    "modifiers",
]


def normalize_parameters(value: Any) -> Any:
    """Convert a parameters value to a JSON-safe representation.

    SQL plugin stores parameters as ``list[SQLParameter]`` (dataclasses).
    JSON cannot serialize dataclass instances; convert them to plain dicts
    so all output formats (JSON, TOON, text) stay consistent. Non-list and
    non-dataclass values are returned unchanged.
    """
    if isinstance(value, list):
        return [
            dataclasses.asdict(p)
            if dataclasses.is_dataclass(p) and not isinstance(p, type)
            else p
            for p in value
        ]
    return value


def element_to_dict(
    elem: Any,
    all_elements: Sequence[Any] | None = None,
    result_language: str | None = None,
) -> dict[str, Any]:
    """Convert an analysis element to the stable API dict representation.

    ``result_language`` is the analyzer-detected language for the whole file
    (``AnalysisResult.language``). When provided, it backfills an element's
    ``language`` field for elements whose own ``.language`` is empty or the
    sentinel ``"unknown"`` (#1019: some C#/PHP/Ruby/SQL element builders never
    set ``.language``, so it defaulted to ``"unknown"`` instead of the real
    analyzer language). The backfill fires ONLY for empty/``"unknown"`` values,
    so a legitimately-different embedded language is preserved — e.g. Markdown
    fenced code blocks always carry the embedded lang (``bash``/``json``/…) or
    ``"text"`` for un-tagged fences, never ``"unknown"``, so they are untouched.
    """
    python_type = type(elem).__name__.lower()
    # #795: Class objects carry a class_type that distinguishes enum/interface/type/namespace
    # from plain "class".  Surface that specificity in the output type field.
    if python_type == "class":
        output_type = getattr(elem, "class_type", "class") or "class"
    else:
        output_type = python_type
    elem_language = elem.language
    if result_language and (not elem_language or elem_language == "unknown"):
        elem_language = result_language
    result: dict[str, Any] = {
        "name": elem.name,
        "type": output_type,
        "start_line": elem.start_line,
        "end_line": elem.end_line,
        "raw_text": elem.raw_text,
        "language": elem_language,
    }
    for field in _OPTIONAL_ELEM_FIELDS:
        if hasattr(elem, field):
            value = getattr(elem, field)
            if field == "parameters":
                value = normalize_parameters(value)
            result[field] = value

    if result["type"] == "function" and all_elements:
        # A LOCAL function (innermost container is another function, e.g.
        # Kotlin `fun inner` inside a method) is deliberately unowned —
        # only class-owned methods get class_name (Codex P2 on #570).
        if not _contained_in_other_function(elem, all_elements):
            class_name = find_class_name(elem, all_elements)
            if class_name is not None:
                result["class_name"] = class_name

    return result


def _contained_in_other_function(elem: Any, elements: Sequence[Any]) -> bool:
    """True when another function's span strictly contains ``elem``'s."""
    for other in elements:
        if other is elem or type(other).__name__.lower() != "function":
            continue
        if not (hasattr(other, "start_line") and hasattr(other, "end_line")):
            continue
        if (
            other.start_line <= elem.start_line
            and elem.end_line <= other.end_line
            and (other.start_line, other.end_line) != (elem.start_line, elem.end_line)
        ):
            return True
    return False


def find_class_name(elem: Any, elements: Sequence[Any]) -> str | None:
    """Find the containing class name for a method element.

    When multiple classes contain the element's line range (e.g. an inner
    class nested inside an outer class, or a class inside a namespace), the
    INNERMOST class — the one with the smallest line span — wins.  This
    mirrors the single-ownership rule from #474/#484/#532.
    """
    best_name: str | None = None
    best_span: int | None = None
    for other in elements:
        if type(other).__name__.lower() != "class":
            continue
        if not (hasattr(other, "start_line") and hasattr(other, "end_line")):
            continue
        if other.start_line <= elem.start_line <= other.end_line:
            span = other.end_line - other.start_line
            if best_span is None or span < best_span:
                best_span = span
                best_name = other.name
    return best_name


def file_analysis_result(
    analysis_result: Any,
    file_path: str | Path,
    requested_language: str | None,
    *,
    include_elements: bool,
    include_queries: bool,
) -> dict[str, Any]:
    """Build the public API response for file analysis."""
    result = {
        "success": analysis_result.success,
        "file_info": {
            "path": str(file_path),
            "exists": True,
        },
        "language_info": {
            "language": analysis_result.language,
            "detected": requested_language is None,
        },
        "ast_info": {
            "node_count": analysis_result.node_count,
            "line_count": analysis_result.line_count,
        },
    }
    return _with_success_sections(
        result,
        analysis_result,
        include_elements=include_elements,
        include_queries=include_queries,
    )


def code_analysis_result(
    analysis_result: Any,
    requested_language: str,
    *,
    include_elements: bool,
    include_queries: bool,
) -> dict[str, Any]:
    """Build the public API response for source-string analysis."""
    result = {
        "success": analysis_result.success,
        "language_info": {
            "language": analysis_result.language,
            "detected": False,
        },
        "ast_info": {
            "node_count": analysis_result.node_count,
            "line_count": analysis_result.line_count,
        },
    }
    return _with_success_sections(
        result,
        analysis_result,
        include_elements=include_elements,
        include_queries=include_queries,
    )


def _with_success_sections(
    result: dict[str, Any],
    analysis_result: Any,
    *,
    include_elements: bool,
    include_queries: bool,
) -> dict[str, Any]:
    if not analysis_result.success:
        if analysis_result.error_message:
            result["error"] = analysis_result.error_message
        return result

    if include_elements and hasattr(analysis_result, "elements"):
        result["elements"] = [
            element_to_dict(
                elem,
                analysis_result.elements,
                result_language=analysis_result.language,
            )
            for elem in analysis_result.elements
        ]

    if include_queries and hasattr(analysis_result, "query_results"):
        result["query_results"] = analysis_result.query_results

    if not include_elements and "elements" in result:
        del result["elements"]
    if not include_queries and "query_results" in result:
        del result["query_results"]

    return result


def file_analysis_error(
    file_path: str | Path, language: str | None, error: Exception
) -> dict[str, Any]:
    """Build the public API error response for file analysis."""
    return {
        "success": False,
        "error": str(error),
        "file_info": {"path": str(file_path), "exists": False},
        "language_info": {"language": language or "unknown", "detected": False},
        "ast_info": {"node_count": 0, "line_count": 0},
    }


def code_analysis_error(language: str, error: Exception) -> dict[str, Any]:
    """Build the public API error response for source-string analysis."""
    return {
        "success": False,
        "error": str(error),
        "language_info": {"language": language or "unknown", "detected": False},
        "ast_info": {"node_count": 0, "line_count": 0},
    }
