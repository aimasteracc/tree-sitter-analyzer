"""Helpers for HTML JSON formatter output."""

from collections.abc import Callable
from typing import Any

from ..models import CodeElement, MarkupElement, StyleElement


def build_html_json_result(
    elements: list[CodeElement],
    markup_to_dict: Callable[[MarkupElement], dict[str, Any]],
    style_to_dict: Callable[[StyleElement], dict[str, Any]],
    element_to_dict_fn: Callable[[CodeElement], dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "html_analysis": {
            "total_elements": len(elements),
            "markup_elements": [],
            "style_elements": [],
            "other_elements": [],
        }
    }

    for element in elements:
        _append_json_element(
            element,
            result,
            markup_to_dict,
            style_to_dict,
            element_to_dict_fn,
        )

    return result


def _append_json_element(
    element: CodeElement,
    result: dict[str, Any],
    markup_to_dict: Callable[[MarkupElement], dict[str, Any]],
    style_to_dict: Callable[[StyleElement], dict[str, Any]],
    element_to_dict_fn: Callable[[CodeElement], dict[str, Any]],
) -> None:
    analysis = result["html_analysis"]
    if isinstance(element, MarkupElement):
        analysis["markup_elements"].append(markup_to_dict(element))
        return
    if isinstance(element, StyleElement):
        analysis["style_elements"].append(style_to_dict(element))
        return
    if isinstance(element, dict):
        _append_json_dict(element, analysis)
        return
    analysis["other_elements"].append(element_to_dict_fn(element))


def _append_json_dict(element: dict[str, Any], analysis: dict[str, Any]) -> None:
    element_type = element.get("element_type", element.get("type", "unknown"))
    if "tag_name" in element or element_type in ["tag", "element", "markup"]:
        analysis["markup_elements"].append(element)
    elif "selector" in element or element_type in ["rule", "style"]:
        analysis["style_elements"].append(element)
    else:
        analysis["other_elements"].append(element)
