"""Query and element facade helpers for the public API."""

from pathlib import Path
from typing import Any

_MAIN_CAPTURE_TYPES = {"method", "class", "function", "interface", "field"}


def group_captures_by_main_node(
    captures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group flat query captures by their main nodes."""
    if not captures:
        return []

    sorted_captures = sorted(
        captures, key=lambda c: (c.get("start_byte", 0), -c.get("end_byte", 0))
    )
    results: list[dict[str, Any]] = []
    main_node_stack: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for capture in sorted_captures:
        _add_capture_to_group(capture, main_node_stack, results)

    return results


def _add_capture_to_group(
    capture: dict[str, Any],
    main_node_stack: list[tuple[dict[str, Any], dict[str, Any]]],
    results: list[dict[str, Any]],
) -> None:
    capture_name = capture.get("capture_name", "")
    end = capture.get("end_byte", 0)

    while main_node_stack and main_node_stack[-1][0].get("end_byte", 0) < end:
        main_node_stack.pop()

    if capture_name in _MAIN_CAPTURE_TYPES:
        _add_main_capture(capture, main_node_stack, results)
    elif main_node_stack:
        _add_child_capture(capture_name, capture, main_node_stack[-1][1])


def _add_main_capture(
    capture: dict[str, Any],
    main_node_stack: list[tuple[dict[str, Any], dict[str, Any]]],
    results: list[dict[str, Any]],
) -> None:
    start = capture.get("start_byte", 0)
    end = capture.get("end_byte", 0)
    grouped_captures = {capture.get("capture_name", ""): capture}
    result = {
        "captures": grouped_captures,
        "text": capture.get("text", ""),
        "start_line": capture.get("line_number", 0),
        "end_line": capture.get("line_number", 0) + capture.get("text", "").count("\n"),
        "start_byte": start,
        "end_byte": end,
        "node_type": capture.get("node_type", ""),
    }
    results.append(result)
    main_node_stack.append((capture, grouped_captures))


def _add_child_capture(
    capture_name: str,
    capture: dict[str, Any],
    parent_grouped: dict[str, Any],
) -> None:
    if capture_name not in parent_grouped:
        parent_grouped[capture_name] = capture
        return

    existing = parent_grouped[capture_name]
    if isinstance(existing, list):
        parent_grouped[capture_name] = [*existing, capture]
    else:
        parent_grouped[capture_name] = [existing, capture]


def query_captures_for_result(result: dict[str, Any], query_name: str) -> list[Any]:
    """Extract raw captures from the API query result shape."""
    query_result = result["query_results"].get(query_name, {})
    if isinstance(query_result, dict) and "captures" in query_result:
        return query_result["captures"]
    if isinstance(query_result, list):
        return query_result
    return []


def query_execution_result(
    result: dict[str, Any],
    query_name: str,
    file_path: str | Path,
) -> dict[str, Any]:
    """Build the public API response for a query facade call."""
    if not result["success"] or "query_results" not in result:
        return {
            "success": False,
            "query_name": query_name,
            "error": result.get("error", "Unknown error"),
            "file_path": str(file_path),
        }

    query_results = group_captures_by_main_node(
        query_captures_for_result(result, query_name)
    )
    return {
        "success": True,
        "query_name": query_name,
        "results": query_results,
        "count": len(query_results),
        "language": result.get("language_info", {}).get("language"),
        "file_path": str(file_path),
    }


# All type strings that are conceptually "a class" — PR #795 expanded the
# type field beyond the literal "class" string.  Callers that filter with
# element_types=["class"] must still receive these subtypes for backward
# compatibility (Codex P2 on PR #901).
_CLASS_FAMILY_TYPES = frozenset(
    {"class", "abstract_class", "interface", "enum", "namespace", "type"}
)


def filter_elements_by_type(
    elements: list[dict[str, Any]],
    element_types: list[str] | None,
) -> list[dict[str, Any]]:
    """Filter extracted elements by fuzzy type match.

    ``element_types=["class"]`` matches all class-family types
    (interface, enum, namespace, abstract_class, type) in addition to
    plain "class" for backward compatibility after PR #795.
    """
    if not element_types:
        return elements

    wants_class_family = any(t.lower() == "class" for t in element_types)

    return [
        element
        for element in elements
        if any(
            element_type.lower() in element.get("type", "").lower()
            for element_type in element_types
        )
        or (wants_class_family and element.get("type", "") in _CLASS_FAMILY_TYPES)
    ]
