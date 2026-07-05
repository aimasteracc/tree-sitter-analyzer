"""Class membership helpers for the legacy table formatter."""

from __future__ import annotations

from typing import Any


def get_class_methods(
    data: dict[str, Any],
    class_line_range: dict[str, int],
) -> list[dict[str, Any]]:
    """Get methods for a class line range, excluding nested class members."""
    return _elements_in_class_range(
        data.get("methods", []),
        data.get("classes", []),
        class_line_range,
    )


def get_class_fields(
    data: dict[str, Any],
    class_line_range: dict[str, int],
) -> list[dict[str, Any]]:
    """Get fields for a class line range, excluding nested class members."""
    return _elements_in_class_range(
        data.get("fields", []),
        data.get("classes", []),
        class_line_range,
    )


def _elements_in_class_range(
    elements: list[dict[str, Any]],
    classes: list[dict[str, Any]],
    class_line_range: dict[str, int],
) -> list[dict[str, Any]]:
    """Return elements inside a class range and outside nested class ranges."""
    class_start = class_line_range.get("start", 0)
    class_end = class_line_range.get("end", 0)
    nested_class_ranges = _nested_class_ranges(classes, class_start, class_end)

    return [
        element
        for element in elements
        if _belongs_to_class(element, class_start, class_end, nested_class_ranges)
    ]


def _nested_class_ranges(
    classes: list[dict[str, Any]],
    class_start: int,
    class_end: int,
) -> list[tuple[int, int]]:
    """Return ranges for classes nested inside the provided class range."""
    ranges = []
    for cls in classes:
        cls_range = cls.get("line_range", {})
        cls_start = cls_range.get("start", 0)
        cls_end = cls_range.get("end", 0)
        if class_start < cls_start and cls_end < class_end:
            ranges.append((cls_start, cls_end))
    return ranges


def _belongs_to_class(
    element: dict[str, Any],
    class_start: int,
    class_end: int,
    nested_class_ranges: list[tuple[int, int]],
) -> bool:
    """Return whether an element belongs directly to a class range."""
    element_line = element.get("line_range", {}).get("start", 0)
    if not class_start <= element_line <= class_end:
        return False

    return not any(
        nested_start <= element_line <= nested_end
        for nested_start, nested_end in nested_class_ranges
    )
