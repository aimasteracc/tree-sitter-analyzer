"""Go variable and constant extraction helpers."""

from collections.abc import Callable
from typing import Any

from ..models import Variable
from ..utils import log_error
from ._go_common import go_visibility

_GO_FIELD_TYPE_NODES = {
    "type_identifier",
    "pointer_type",
    "array_type",
    "slice_type",
    "map_type",
    "channel_type",
    "qualified_type",
    "interface_type",
    "struct_type",
    "func_type",
}

_GO_VAR_TYPE_NODES = {
    "type_identifier",
    "pointer_type",
    "array_type",
    "slice_type",
    "map_type",
    "channel_type",
    "qualified_type",
}


def extract_var_spec(
    node: Any,
    is_const: bool,
    get_node_text: Callable[..., str],
) -> list[Variable]:
    """Extract single var/const spec."""
    try:
        raw_text = get_node_text(node)
        names, var_type = _go_var_names_and_type(node, get_node_text)

        return [
            _build_go_variable(name, node, raw_text, var_type, is_const)
            for name in names
        ]
    except Exception as e:
        log_error(f"Error extracting Go var spec: {e}")
        return []


def _go_var_names_and_type(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[list[str], str]:
    names: list[str] = []
    var_type = ""

    for child in node.children:
        if child.type == "identifier":
            names.append(get_node_text(child))
            continue
        if child.type in _GO_VAR_TYPE_NODES:
            var_type = get_node_text(child)

    return names, var_type


def _build_go_variable(
    name: str,
    node: Any,
    raw_text: str,
    var_type: str,
    is_const: bool,
) -> Variable:
    visibility = go_visibility(name)
    return Variable(
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=raw_text,
        language="go",
        variable_type=var_type,
        visibility=visibility,
        is_constant=is_const,
    )


def extract_var_or_const(
    node: Any,
    is_const: bool,
    get_node_text: Callable[..., str],
) -> list[Variable]:
    """Extract var or const declaration."""
    try:
        return [
            variable
            for spec in _iter_var_const_specs(node)
            for variable in extract_var_spec(spec, is_const, get_node_text)
        ]
    except Exception as e:
        label = "const" if is_const else "var"
        log_error(f"Error extracting Go {label}: {e}")
        return []


def _iter_var_const_specs(node: Any) -> list[Any]:
    return [
        child for child in node.children if child.type in ("const_spec", "var_spec")
    ]


def extract_struct_fields(
    type_declaration_node: Any,
    get_node_text: Callable[..., str],
) -> list[Variable]:
    """Extract field declarations from a Go struct type_declaration node.

    Walks: type_declaration → type_spec → struct_type → field_declaration_list
    → field_declaration nodes, yielding one Variable per field with
    ``receiver_type`` set to the owning struct name.
    """
    results: list[Variable] = []
    try:
        for type_spec in type_declaration_node.children:
            if type_spec.type != "type_spec":
                continue
            name_node = type_spec.child_by_field_name("name")
            if name_node is None:
                continue
            struct_name = get_node_text(name_node)

            type_body = type_spec.child_by_field_name("type")
            if type_body is None or type_body.type != "struct_type":
                continue

            for child in type_body.children:
                if child.type != "field_declaration_list":
                    continue
                for field_node in child.children:
                    if field_node.type != "field_declaration":
                        continue
                    field_var = _extract_one_field(
                        field_node, struct_name, get_node_text
                    )
                    if field_var is not None:
                        results.append(field_var)
    except Exception as e:
        log_error(f"Error extracting Go struct fields: {e}")
    return results


def _extract_one_field(
    field_node: Any,
    struct_name: str,
    get_node_text: Callable[..., str],
) -> Variable | None:
    """Extract a single field_declaration into a Variable.

    Go grammar: field_declaration has named fields "name" (field_identifier)
    and "type" (any type node).  Embedded fields (anonymous fields) have no
    "name" child — skip them for now.
    """
    try:
        name_node = field_node.child_by_field_name("name")
        type_node = field_node.child_by_field_name("type")
        if name_node is None or type_node is None:
            return None

        name = get_node_text(name_node)
        field_type = get_node_text(type_node)
        raw_text = get_node_text(field_node)
        visibility = go_visibility(name)

        return Variable(
            name=name,
            start_line=field_node.start_point[0] + 1,
            end_line=field_node.end_point[0] + 1,
            raw_text=raw_text,
            language="go",
            variable_type=field_type,
            visibility=visibility,
            is_constant=False,
            receiver_type=struct_name,
        )
    except Exception as e:
        log_error(f"Error extracting Go field declaration: {e}")
        return None
