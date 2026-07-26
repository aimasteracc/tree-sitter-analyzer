"""Kotlin function and primary-constructor extraction."""

from collections.abc import Callable
from typing import Any

from ..models import Function
from ..utils import log_error
from ._kotlin_core_helpers import (
    _kotlin_expression_body_type,
    _kotlin_extension_receiver,
    _kotlin_owning_type,
    _kotlin_parameter_pair,
    calculate_kotlin_complexity,
    determine_visibility,
    extract_kotlin_parameters,
)


def _kotlin_function_name(node: Any, get_node_text: Callable[..., str]) -> str:
    name_node = node.child_by_field_name("name")
    if name_node:
        return str(get_node_text(name_node))
    for child in node.children:
        if child.type == "simple_identifier":
            return str(get_node_text(child))
    children = list(node.children)
    for index, child in enumerate(children[:-1]):
        if child.type == "." and children[index + 1].type == "identifier":
            return str(get_node_text(children[index + 1]))
    return "anonymous"


def _kotlin_function_return_type(
    node: Any,
    get_node_text: Callable[..., str],
) -> str:
    for index, child in enumerate(node.children):
        if child.type == ":" and index + 1 < len(node.children):
            return str(get_node_text(node.children[index + 1]))
    inferred = _kotlin_expression_body_type(node, get_node_text)
    return "Unit" if inferred is None else inferred


def _kotlin_function_modifiers(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str, bool]:
    modifiers_node = node.child_by_field_name("modifiers")
    if not modifiers_node:
        return "public", False
    modifiers = get_node_text(modifiers_node)
    return determine_visibility(modifiers), "suspend" in modifiers


def _apply_kotlin_function_receiver(
    function: Function,
    node: Any,
    get_node_text: Callable[..., str],
) -> None:
    extension_receiver = _kotlin_extension_receiver(node, get_node_text)
    if extension_receiver is not None:
        function.receiver_type = extension_receiver
        function.is_method = True
        return
    owner, is_companion = _kotlin_owning_type(node)
    if owner is None:
        return
    function.receiver_type = owner
    function.is_method = not is_companion
    if is_companion:
        function.is_static = True


def extract_kotlin_function(
    node: Any,
    get_node_text: Callable[..., str],
    current_package: str,
) -> Function | None:
    """Extract one Kotlin function without changing the historical model shape."""
    del current_package
    try:
        visibility, is_suspend = _kotlin_function_modifiers(node, get_node_text)
        function = Function(
            name=_kotlin_function_name(node, get_node_text),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=get_node_text(node),
            language="kotlin",
            parameters=extract_kotlin_parameters(node, get_node_text),
            return_type=_kotlin_function_return_type(node, get_node_text),
            visibility=visibility,
            complexity_score=calculate_kotlin_complexity(node),
        )
        function.is_suspend = is_suspend
        _apply_kotlin_function_receiver(function, node, get_node_text)
        return function
    except Exception as exc:
        log_error(f"Error extracting Kotlin function: {exc}")
        return None


def _kotlin_primary_ctor_class_name(
    node: Any, get_node_text: Callable[..., str]
) -> str:
    """Return the enclosing class identifier or ``anonymous``."""
    parent = node.parent
    if parent is None:
        return "anonymous"
    for child in parent.children:
        if child.type == "identifier":
            return str(get_node_text(child))
    return "anonymous"


def _kotlin_primary_constructor_parameters(
    node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    parameters: list[str] = []
    params_node = next(
        (child for child in node.children if child.type == "class_parameters"),
        None,
    )
    if params_node is None:
        return parameters
    for parameter in params_node.children:
        if parameter.type != "class_parameter":
            continue
        name, param_type = _kotlin_parameter_pair(parameter, get_node_text)
        if name:
            parameters.append(f"{name}: {param_type or 'Any'}")
    return parameters


def extract_kotlin_primary_constructor(
    node: Any,
    get_node_text: Callable[..., str],
    current_package: str,
) -> Function | None:
    """Extract a Kotlin primary constructor as a constructor Function."""
    del current_package
    try:
        return Function(
            name=_kotlin_primary_ctor_class_name(node, get_node_text),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=get_node_text(node),
            language="kotlin",
            parameters=_kotlin_primary_constructor_parameters(node, get_node_text),
            return_type=None,
            visibility="public",
            is_constructor=True,
            complexity_score=calculate_kotlin_complexity(node),
        )
    except Exception as exc:
        log_error(f"Error extracting Kotlin primary constructor: {exc}")
        return None
