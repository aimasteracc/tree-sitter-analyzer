"""Template extraction helpers for the C++ plugin."""

from collections.abc import Callable
from typing import Any

from ..models import Class, Function


def extract_template_function(
    node: Any,
    processed_nodes: set[int],
    extract_function: Callable[[Any], Function | None],
) -> Function | None:
    """Extract the function definition inside a template declaration."""
    child = _first_child_of_type(node, {"function_definition"})
    if child is None:
        return None

    processed_nodes.add(id(child))
    return _with_template_modifier(extract_function(child))


def extract_template_class(
    node: Any,
    processed_nodes: set[int],
    extract_class: Callable[[Any], Class | None],
    extract_struct: Callable[[Any], Class | None],
) -> Class | None:
    """Extract the class or struct definition inside a template declaration."""
    for child in node.children:
        extractor = _template_class_extractor(child.type, extract_class, extract_struct)
        if extractor is None:
            continue

        processed_nodes.add(id(child))
        return _with_template_modifier(extractor(child))

    return None


def _first_child_of_type(node: Any, node_types: set[str]) -> Any | None:
    for child in node.children:
        if child.type in node_types:
            return child
    return None


def _template_class_extractor(
    node_type: str,
    extract_class: Callable[[Any], Class | None],
    extract_struct: Callable[[Any], Class | None],
) -> Callable[[Any], Class | None] | None:
    if node_type == "class_specifier":
        return extract_class
    if node_type == "struct_specifier":
        return extract_struct
    return None


def _with_template_modifier(
    element: Class | Function | None,
) -> Class | Function | None:
    if element is None:
        return None
    element.modifiers = element.modifiers or []
    if "template" not in element.modifiers:
        element.modifiers.append("template")
    return element
