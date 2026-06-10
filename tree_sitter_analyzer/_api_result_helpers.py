"""Result-shaping helpers for the public API facade."""

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


def element_to_dict(
    elem: Any, all_elements: Sequence[Any] | None = None
) -> dict[str, Any]:
    """Convert an analysis element to the stable API dict representation."""
    result: dict[str, Any] = {
        "name": elem.name,
        "type": type(elem).__name__.lower(),
        "start_line": elem.start_line,
        "end_line": elem.end_line,
        "raw_text": elem.raw_text,
        "language": elem.language,
    }
    for field in _OPTIONAL_ELEM_FIELDS:
        if hasattr(elem, field):
            result[field] = getattr(elem, field)

    if result.get("is_method") and result["type"] == "function" and all_elements:
        result["class_name"] = find_class_name(elem, all_elements)

    return result


def find_class_name(elem: Any, elements: Sequence[Any]) -> str | None:
    """Find the containing class name for a method element."""
    for other in elements:
        if (
            type(other).__name__.lower() == "class"
            and hasattr(other, "start_line")
            and hasattr(other, "end_line")
            and other.start_line <= elem.start_line <= other.end_line
        ):
            return other.name
    return None


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
            element_to_dict(elem, analysis_result.elements)
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
