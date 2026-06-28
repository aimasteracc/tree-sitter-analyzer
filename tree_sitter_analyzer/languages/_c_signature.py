"""C function signature parsing helpers."""

from collections.abc import Callable
from typing import Any


def parse_function_signature(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> tuple[str, str, list[str], list[str]] | None:
    """Parse C function signature."""
    try:
        name: str | None = None
        return_type = "int"
        parameters: list[str] = []
        modifiers: list[str] = []

        for child in node.children:
            if child.type == "function_declarator":
                name, parameters = _function_declarator_info(
                    child, get_node_text, extract_params_fn
                )
            elif child.type == "pointer_declarator":
                pointer_name, pointer_parameters = _find_function_declarator(
                    child, get_node_text, extract_params_fn
                )
                name = pointer_name or name
                parameters = pointer_parameters or parameters
                return_type = _pointer_return_type(return_type)
            elif child.type in _RETURN_TYPE_NODES:
                return_type = get_node_text(child)
            elif child.type in _MODIFIER_NODES:
                _append_modifier(modifiers, child, get_node_text)

        if not name:
            return None

        return name, return_type, parameters, modifiers
    except Exception:
        return None


_RETURN_TYPE_NODES = frozenset(
    {
        "primitive_type",
        "type_identifier",
        "sized_type_specifier",
    }
)

_MODIFIER_NODES = frozenset({"storage_class_specifier", "type_qualifier"})


def _function_declarator_info(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> tuple[str | None, list[str]]:
    name: str | None = None
    parameters: list[str] = []
    for child in node.children:
        if child.type == "identifier":
            name = get_node_text(child)
        elif child.type == "parameter_list":
            parameters = extract_params_fn(child)
    return name, parameters


def _find_function_declarator(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> tuple[str | None, list[str]]:
    for child in node.children:
        if child.type == "function_declarator":
            return _function_declarator_info(child, get_node_text, extract_params_fn)
        if child.type == "pointer_declarator":
            name, parameters = _find_function_declarator(
                child, get_node_text, extract_params_fn
            )
            if name:
                return name, parameters
    return None, []


def _pointer_return_type(return_type: str) -> str:
    if return_type and "*" not in return_type:
        return return_type + "*"
    return return_type


def _append_modifier(
    modifiers: list[str], node: Any, get_node_text: Callable[..., str]
) -> None:
    modifier = get_node_text(node)
    if modifier:
        modifiers.append(modifier)
