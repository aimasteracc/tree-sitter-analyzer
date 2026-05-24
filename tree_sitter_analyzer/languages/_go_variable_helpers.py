"""Go variable and constant extraction helpers."""

from collections.abc import Callable
from typing import Any

from ..models import Variable
from ..utils import log_error
from ._go_common_helpers import go_visibility

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
