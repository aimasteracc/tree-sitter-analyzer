"""C declaration extraction helpers."""

from collections.abc import Callable
from typing import Any

from ..models import Variable
from ..utils import log_debug

_TYPE_NODES_FIELD = frozenset(
    {
        "primitive_type",
        "type_identifier",
        "sized_type_specifier",
        "struct_specifier",
        "union_specifier",
        "enum_specifier",
    }
)

_TYPE_NODES_VAR = frozenset(
    {
        "primitive_type",
        "type_identifier",
        "sized_type_specifier",
        "struct_specifier",
        "union_specifier",
        "enum_specifier",
    }
)


def extract_field_declaration(
    node: Any, get_node_text: Callable[..., str]
) -> list[Variable]:
    """Extract struct/union field declarations."""
    try:
        start_line, end_line = _node_line_range(node)
        field_type, field_names, modifiers = _field_parts(node, get_node_text)
        if not field_type or not field_names:
            return []

        raw_text = get_node_text(node)
        return [
            _field_variable(
                field_name, start_line, end_line, raw_text, field_type, modifiers
            )
            for field_name in field_names
        ]
    except Exception as e:
        log_debug(f"Failed to extract field info: {e}")
        return []


def extract_variable_declaration(
    node: Any, get_node_text: Callable[..., str]
) -> list[Variable]:
    """Extract C variable declarations (not struct members)."""
    if node.parent and node.parent.type == "field_declaration_list":
        return []

    try:
        start_line, end_line = _node_line_range(node)
        var_type, var_names, modifiers = _variable_parts(node, get_node_text)
        if not var_type or not var_names:
            return []

        raw_text = get_node_text(node)
        visibility = "private" if "static" in modifiers else "public"
        return [
            _variable(
                var_name,
                start_line,
                end_line,
                raw_text,
                var_type,
                modifiers,
                visibility,
            )
            for var_name in var_names
        ]
    except Exception as e:
        log_debug(f"Failed to extract variable declaration: {e}")
        return []


def _node_line_range(node: Any) -> tuple[int, int]:
    return node.start_point[0] + 1, node.end_point[0] + 1


def _field_parts(
    node: Any, get_node_text: Callable[..., str]
) -> tuple[str | None, list[str], list[str]]:
    field_type: str | None = None
    field_names: list[str] = []
    modifiers: list[str] = []

    for child in node.children:
        if child.type in _TYPE_NODES_FIELD:
            field_type = get_node_text(child)
        elif child.type == "type_qualifier":
            _append_modifier(modifiers, child, get_node_text)
        elif child.type == "field_identifier":
            field_names.append(get_node_text(child))
        elif child.type == "array_declarator":
            field_type = _append_array_fields(
                child, field_names, field_type, get_node_text
            )
        elif child.type == "init_declarator":
            _append_initializer_fields(child, field_names, get_node_text)
        elif child.type == "pointer_declarator":
            field_type = _append_pointer_fields(
                child, field_names, field_type, get_node_text
            )

    return field_type, field_names, modifiers


def _variable_parts(
    node: Any, get_node_text: Callable[..., str]
) -> tuple[str | None, list[str], list[str]]:
    var_type: str | None = None
    var_names: list[str] = []
    modifiers: list[str] = []

    for child in node.children:
        if child.type in _TYPE_NODES_VAR:
            var_type = get_node_text(child)
        elif child.type in {"storage_class_specifier", "type_qualifier"}:
            _append_modifier(modifiers, child, get_node_text)
        elif child.type == "identifier":
            var_names.append(get_node_text(child))
        elif child.type == "init_declarator":
            _append_child_names(child, var_names, "identifier", get_node_text)
        elif child.type == "pointer_declarator":
            var_type = _append_pointer_variables(
                child, var_names, var_type, get_node_text
            )

    return var_type, var_names, modifiers


def _append_array_fields(
    node: Any,
    field_names: list[str],
    field_type: str | None,
    get_node_text: Callable[..., str],
) -> str:
    _append_child_names(node, field_names, "field_identifier", get_node_text)
    return field_type + "[]" if field_type else "[]"


def _append_initializer_fields(
    node: Any, field_names: list[str], get_node_text: Callable[..., str]
) -> None:
    for grandchild in node.children:
        if grandchild.type in {"field_identifier", "identifier"}:
            field_names.append(get_node_text(grandchild))


def _append_pointer_fields(
    node: Any,
    field_names: list[str],
    field_type: str | None,
    get_node_text: Callable[..., str],
) -> str | None:
    if _append_child_names(node, field_names, "field_identifier", get_node_text):
        return field_type + "*" if field_type else "*"
    return field_type


def _append_pointer_variables(
    node: Any,
    var_names: list[str],
    var_type: str | None,
    get_node_text: Callable[..., str],
) -> str | None:
    if _append_child_names(node, var_names, "identifier", get_node_text):
        return var_type + "*" if var_type else "*"
    return var_type


def _append_child_names(
    node: Any,
    names: list[str],
    node_type: str,
    get_node_text: Callable[..., str],
) -> bool:
    initial_len = len(names)
    for child in node.children:
        if child.type == node_type:
            names.append(get_node_text(child))
    return len(names) > initial_len


def _append_modifier(
    modifiers: list[str], node: Any, get_node_text: Callable[..., str]
) -> None:
    modifier = get_node_text(node)
    if modifier:
        modifiers.append(modifier)


def _field_variable(
    name: str,
    start_line: int,
    end_line: int,
    raw_text: str,
    field_type: str,
    modifiers: list[str],
) -> Variable:
    return Variable(
        name=name,
        start_line=start_line,
        end_line=end_line,
        raw_text=raw_text,
        language="c",
        variable_type=field_type,
        modifiers=modifiers,
        is_constant="const" in modifiers,
        visibility="public",
    )


def _variable(
    name: str,
    start_line: int,
    end_line: int,
    raw_text: str,
    var_type: str,
    modifiers: list[str],
    visibility: str,
) -> Variable:
    return Variable(
        name=name,
        start_line=start_line,
        end_line=end_line,
        raw_text=raw_text,
        language="c",
        variable_type=var_type,
        modifiers=modifiers,
        is_static="static" in modifiers,
        is_constant="const" in modifiers,
        visibility=visibility,
    )
