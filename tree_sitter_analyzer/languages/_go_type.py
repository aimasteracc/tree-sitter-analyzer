"""Go type extraction helpers."""

from collections.abc import Callable
from typing import Any

from ..models import Class
from ..utils import log_error
from ._go_common import extract_docstring, go_visibility

_GO_TYPE_NODE_TO_CLASS_TYPE = {
    "struct_type": "struct",
    "interface_type": "interface",
}


def extract_embedded_types(
    struct_node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract embedded types from struct."""
    return [
        type_text
        for field in _iter_struct_fields(struct_node)
        if (type_text := _extract_embedded_type(field, get_node_text))
    ]


def _iter_struct_fields(struct_node: Any) -> list[Any]:
    fields = []
    for child in struct_node.children:
        if child.type != "field_declaration_list":
            continue
        fields.extend(
            field for field in child.children if field.type == "field_declaration"
        )
    return fields


def _extract_embedded_type(
    field: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    type_text = None
    for child in field.children:
        if child.type == "field_identifier":
            return None
        if child.type in ("type_identifier", "qualified_type"):
            type_text = get_node_text(child)
    return type_text


def extract_go_type_spec(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Class | None:
    """Extract single Go type spec (struct, interface, type alias)."""
    try:
        name, type_node = _go_type_name_and_node(node, get_node_text)
        if not name:
            return None

        return _build_go_class(name, type_node, node, get_node_text, content_lines)
    except Exception as e:
        log_error(f"Error extracting Go type spec: {e}")
        return None


def _go_type_name_and_node(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str | None, Any | None]:
    name_node = node.child_by_field_name("name")
    type_node = node.child_by_field_name("type")
    if not name_node:
        return None, type_node
    return get_node_text(name_node) or None, type_node


def _build_go_class(
    name: str,
    type_node: Any | None,
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Class:
    return Class(
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=get_node_text(node),
        language="go",
        class_type=_go_class_type(type_node),
        visibility=go_visibility(name),
        docstring=extract_docstring(node, content_lines),
        interfaces=_go_struct_interfaces(type_node, get_node_text),
    )


def _go_class_type(type_node: Any | None) -> str:
    if not type_node:
        return "type"
    return _GO_TYPE_NODE_TO_CLASS_TYPE.get(type_node.type, "type_alias")


def _go_struct_interfaces(
    type_node: Any | None,
    get_node_text: Callable[..., str],
) -> list[str]:
    if not type_node:
        return []
    if type_node.type == "struct_type":
        return extract_embedded_types(type_node, get_node_text)
    if type_node.type == "interface_type":
        return _go_interface_embedded(type_node, get_node_text)
    return []


def _go_interface_embedded(
    interface_node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract embedded interface names from an interface_type node.

    ``type ReadWriter interface { Reader; Writer }`` emits ``type_elem``
    children whose single child is the embedded type identifier.  These are
    the interface embedding constraints (N5 in issue #538).
    """
    return [
        get_node_text(child)
        for child in interface_node.children
        if child.type == "type_elem" and get_node_text(child).strip()
    ]


def extract_type_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> list[Class]:
    """Extract type declaration (struct, interface, type alias)."""
    try:
        return [
            cls
            for spec in _iter_type_specs(node)
            if (cls := extract_go_type_spec(spec, get_node_text, content_lines))
        ]
    except Exception as e:
        log_error(f"Error extracting Go type declaration: {e}")
        return []


def _iter_type_specs(node: Any) -> list[Any]:
    return [
        child for child in node.children if child.type in ("type_spec", "type_alias")
    ]
