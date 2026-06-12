"""Signature and class parsing helpers for the Python language extractor."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_PARAMETER_NODE_TYPES = frozenset(
    {
        "identifier",
        "typed_parameter",
        "default_parameter",
        "typed_default_parameter",
        "list_splat_pattern",
        "dictionary_splat_pattern",
    }
)
_INVALID_RETURN_TYPE_MARKERS = ("def ", "class ", "import ")


def _decode_optional_text(node: Any) -> str | None:
    node_text = node.text
    return node_text.decode("utf8") if node_text else None


def _normalize_decorator_text(decorator_text: str) -> str:
    if decorator_text.startswith("@"):
        return decorator_text[1:].strip()
    return decorator_text


def _strip_docstring_quotes(docstring: str) -> str:
    """Remove Python string delimiters from a docstring literal."""
    if docstring.startswith('"""') or docstring.startswith("'''"):
        return docstring[3:-3].strip()
    if docstring.startswith('"') or docstring.startswith("'"):
        return docstring[1:-1].strip()
    return docstring


def _class_body_assignment_node(node: Any) -> Any | None:
    """Return the assignment represented directly by a class-body child."""
    if node.type == "assignment":
        return node
    if node.type != "expression_statement":
        return None
    return next((child for child in node.children if child.type == "assignment"), None)


def _extract_class_decorators(
    parent: Any, get_node_text: Callable[[Any], str]
) -> list[str]:
    decorators = []
    if not parent:
        return decorators

    for sibling in parent.children:
        if sibling.type != "decorated_definition":
            continue
        for child in sibling.children:
            if child.type == "decorator":
                decorators.append(_normalize_decorator_text(get_node_text(child)))
    return decorators


def _extract_class_name_and_superclasses(node: Any) -> tuple[str | None, list[str]]:
    class_name = None
    superclasses = []

    for child in node.children:
        if child.type == "identifier":
            class_name = _decode_optional_text(child)
        elif child.type == "argument_list":
            superclasses.extend(_extract_superclass_names(child))

    return class_name, superclasses


def _extract_superclass_names(argument_list_node: Any) -> list[str]:
    if not argument_list_node.children:
        return []

    superclasses = []
    for child in argument_list_node.children:
        if child.type != "identifier":
            continue
        superclass_name = _decode_optional_text(child)
        if superclass_name:
            superclasses.append(superclass_name)
    return superclasses


def _return_type_from_signature_text(node_text: str) -> str | None:
    if "->" not in node_text:
        return None

    parts = node_text.split("->")
    if len(parts) <= 1:
        return None

    return_type = parts[1].split(":")[0].strip().replace("\n", " ").strip()
    if _is_usable_return_type(return_type, reject_statement_fragments=True):
        return return_type
    return None


def _is_usable_return_type(
    return_type: str | None, *, reject_statement_fragments: bool
) -> bool:
    if not return_type or return_type.startswith("@") or return_type == "dataclass":
        return False
    if reject_statement_fragments and any(
        marker in return_type for marker in _INVALID_RETURN_TYPE_MARKERS
    ):
        return False
    return True


def _extract_decorated_function_decorators(
    parent: Any, get_node_text: Callable[[Any], str]
) -> list[str]:
    if not parent or parent.type != "decorated_definition":
        return []
    return [
        _normalize_decorator_text(get_node_text(child))
        for child in parent.children
        if child.type == "decorator"
    ]


def _parse_function_signature_children(
    node: Any,
    get_node_text: Callable[[Any], str],
    extract_parameters: Callable[[Any], list[str]],
    return_type: str | None,
) -> tuple[str, list[str], str | None]:
    name = None
    parameters = []

    for child in node.children:
        if child.type == "identifier":
            name = _decode_optional_text(child)
        elif child.type == "parameters":
            parameters = extract_parameters(child)
        else:
            return_type = _return_type_from_type_child(
                child, get_node_text, return_type
            )

    return name or "", parameters, return_type


def _return_type_from_type_child(
    child: Any, get_node_text: Callable[[Any], str], current_return_type: str | None
) -> str | None:
    if current_return_type or child.type != "type":
        return current_return_type

    type_text = get_node_text(child)
    if _is_usable_return_type(type_text, reject_statement_fragments=False):
        return type_text
    return current_return_type
