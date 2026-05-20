"""Element classification helpers for HTML formatters."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..models import CodeElement, MarkupElement, StyleElement


@dataclass
class ClassifiedHtmlElements:
    markup_elements: list[Any] = field(default_factory=list)
    style_elements: list[Any] = field(default_factory=list)
    other_elements: list[dict[str, Any]] = field(default_factory=list)


def classify_html_elements(
    elements: list[CodeElement],
    dict_to_markup: Callable[[dict[str, Any]], Any],
    dict_to_style: Callable[[dict[str, Any]], Any],
    element_to_dict: Callable[[CodeElement], dict[str, Any]],
) -> ClassifiedHtmlElements:
    groups = ClassifiedHtmlElements()
    for element in elements:
        _add_classified_element(
            element,
            groups,
            dict_to_markup,
            dict_to_style,
            element_to_dict,
        )
    return groups


def _add_classified_element(
    element: CodeElement,
    groups: ClassifiedHtmlElements,
    dict_to_markup: Callable[[dict[str, Any]], Any],
    dict_to_style: Callable[[dict[str, Any]], Any],
    element_to_dict_fn: Callable[[CodeElement], dict[str, Any]],
) -> None:
    if isinstance(element, MarkupElement):
        groups.markup_elements.append(element)
        return
    if isinstance(element, StyleElement):
        groups.style_elements.append(element)
        return
    if isinstance(element, dict):
        _add_classified_dict(element, groups, dict_to_markup, dict_to_style)
        return
    groups.other_elements.append(element_to_dict_fn(element))


def _add_classified_dict(
    element: dict[str, Any],
    groups: ClassifiedHtmlElements,
    dict_to_markup: Callable[[dict[str, Any]], Any],
    dict_to_style: Callable[[dict[str, Any]], Any],
) -> None:
    element_type = element.get("type", element.get("element_type", "unknown"))
    if "tag_name" in element or element_type in ["tag", "element", "markup"]:
        groups.markup_elements.append(dict_to_markup(element))
    elif "selector" in element or element_type in ["rule", "style"]:
        groups.style_elements.append(dict_to_style(element))
    else:
        groups.other_elements.append(element)
