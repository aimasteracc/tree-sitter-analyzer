"""C++ class, field, and variable helpers."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..models import Variable
from ..utils import log_debug

_TYPE_NODES_CPP = frozenset(
    {
        "primitive_type",
        "sized_type_specifier",
        "type_identifier",
        "qualified_identifier",
        "template_type",
    }
)


@dataclass
class _VariableParts:
    type_name: str | None = None
    names: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)


_BASE_NAME_NODE_TYPES = ("type_identifier", "template_type", "qualified_identifier")


def extract_base_classes(node: Any, get_node_text: Callable[..., str]) -> list[str]:
    """Extract base class names from base_class_clause.

    Theme-C (2026-06-10): tree-sitter-cpp 0.23 puts the access_specifier /
    type_identifier tokens DIRECTLY under ``base_class_clause`` — there is
    no ``base_specifier`` wrapper, so the old wrapper-only loop matched
    nothing and ``class D : public B`` reported superclass=None for every
    C++ class. Accept both shapes (wrapper kept for older grammars).
    """
    base_classes: list[str] = []
    for child in node.children:
        if child.type == "base_specifier":
            base_classes.extend(_base_specifier_names(child, get_node_text))
        elif child.type in _BASE_NAME_NODE_TYPES:
            base_classes.append(get_node_text(child))
    return base_classes


def _base_specifier_names(node: Any, get_node_text: Callable[..., str]) -> list[str]:
    return [
        get_node_text(child)
        for child in node.children
        if child.type in _BASE_NAME_NODE_TYPES
    ]


def extract_cpp_field_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    is_global_fn: Callable[[Any], bool],
    determine_vis_fn: Callable[..., str],
) -> list[Variable]:
    """Extract C++ field declarations."""
    try:
        parts = _variable_parts(node, get_node_text, ("field_identifier", "identifier"))
        if not parts.type_name or not parts.names:
            return []

        return _build_variables(
            node, parts, get_node_text, is_global_fn, determine_vis_fn
        )
    except Exception as exc:
        log_debug(f"Failed to extract field info: {exc}")
        return []


def extract_cpp_variable_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    is_global_fn: Callable[[Any], bool],
    determine_vis_fn: Callable[..., str],
) -> list[Variable]:
    """Extract C++ variable declarations outside class member lists."""
    if node.parent and node.parent.type == "field_declaration_list":
        return []

    try:
        parts = _variable_parts(node, get_node_text, ("identifier",))
        if not parts.type_name or not parts.names:
            return []

        return _build_variables(
            node, parts, get_node_text, is_global_fn, determine_vis_fn
        )
    except Exception as exc:
        log_debug(f"Failed to extract variable declaration: {exc}")
        return []


def _variable_parts(
    node: Any,
    get_node_text: Callable[..., str],
    declarator_name_types: tuple[str, ...],
) -> _VariableParts:
    parts = _VariableParts()
    for child in node.children:
        _apply_variable_child(child, parts, get_node_text, declarator_name_types)
    return parts


def _apply_variable_child(
    child: Any,
    parts: _VariableParts,
    get_node_text: Callable[..., str],
    declarator_name_types: tuple[str, ...],
) -> None:
    if child.type in _TYPE_NODES_CPP:
        parts.type_name = get_node_text(child)
    elif child.type in ("storage_class_specifier", "type_qualifier"):
        _append_text_modifier(parts.modifiers, child, get_node_text)
    elif child.type in declarator_name_types:
        _append_nonempty_name(parts.names, child, get_node_text)
    elif child.type == "init_declarator":
        parts.names.extend(
            _init_declarator_names(child, get_node_text, declarator_name_types)
        )


def _append_text_modifier(
    modifiers: list[str], node: Any, get_node_text: Callable[..., str]
) -> None:
    modifier = get_node_text(node)
    if modifier:
        modifiers.append(modifier)


def _init_declarator_names(
    node: Any,
    get_node_text: Callable[..., str],
    declarator_name_types: tuple[str, ...],
) -> list[str]:
    names: list[str] = []
    for child in node.children:
        if child.type in declarator_name_types:
            _append_nonempty_name(names, child, get_node_text)
    return names


def _append_nonempty_name(
    names: list[str],
    node: Any,
    get_node_text: Callable[..., str],
) -> None:
    name = get_node_text(node)
    if name:
        names.append(name)


def _build_variables(
    node: Any,
    parts: _VariableParts,
    get_node_text: Callable[..., str],
    is_global_fn: Callable[[Any], bool],
    determine_vis_fn: Callable[..., str],
) -> list[Variable]:
    raw_text = get_node_text(node)
    is_global = is_global_fn(node)
    visibility = determine_vis_fn(parts.modifiers, is_global=is_global, node=node)
    return [
        Variable(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            language="cpp",
            variable_type=parts.type_name,
            modifiers=parts.modifiers,
            is_static="static" in parts.modifiers,
            is_constant="const" in parts.modifiers,
            visibility=visibility,
        )
        for name in parts.names
    ]
