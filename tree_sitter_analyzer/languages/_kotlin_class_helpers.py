"""Kotlin class, object, delegation, and property extraction."""

from collections.abc import Callable
from typing import Any

from ..models import Class, Variable
from ..utils import log_error
from ._kotlin_core_helpers import determine_visibility

_KOTLIN_CLASS_KIND_MODIFIERS = frozenset({"enum", "annotation", "data", "sealed"})
_KOTLIN_PROPERTY_VISIBILITY_MODIFIERS = frozenset(
    {"private", "protected", "internal", "public"}
)
_KOTLIN_PROPERTY_OTHER_MODIFIERS = frozenset(
    {"override", "lateinit", "const", "open", "abstract", "final", "suspend"}
)


def _refine_kotlin_class_kind(node: Any, get_node_text: Callable[..., str]) -> str:
    """Return a supported Kotlin class-kind modifier."""
    for child in node.children:
        if child.type != "modifiers":
            continue
        for modifier in child.children:
            text = get_node_text(modifier)
            if text in _KOTLIN_CLASS_KIND_MODIFIERS:
                return str(text)
    return "class"


def _constructor_supertype(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    supertype = next(
        (child for child in node.children if child.type == "user_type"),
        None,
    )
    return None if supertype is None else str(get_node_text(supertype))


def _delegation_specifier(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str | None, list[str]]:
    superclass: str | None = None
    interfaces: list[str] = []
    for child in node.children:
        if child.type == "constructor_invocation" and superclass is None:
            superclass = _constructor_supertype(child, get_node_text)
        elif child.type == "user_type":
            interfaces.append(str(get_node_text(child)))
    return superclass, interfaces


def _extract_kotlin_delegation(
    node: Any, get_node_text: Callable[..., str]
) -> tuple[str | None, list[str]]:
    """Return the first constructed superclass and all interface delegates."""
    superclass: str | None = None
    interfaces: list[str] = []
    delegates = next(
        (child for child in node.children if child.type == "delegation_specifiers"),
        None,
    )
    if delegates is None:
        return superclass, interfaces
    for specifier in delegates.children:
        if specifier.type != "delegation_specifier":
            continue
        candidate_superclass, candidate_interfaces = _delegation_specifier(
            specifier, get_node_text
        )
        if superclass is None and candidate_superclass is not None:
            superclass = candidate_superclass
        interfaces.extend(candidate_interfaces)
    return superclass, interfaces


def _kotlin_class_name(node: Any, get_node_text: Callable[..., str]) -> str:
    name_node = node.child_by_field_name("name")
    if name_node:
        return str(get_node_text(name_node))
    for child in node.children:
        if child.type == "simple_identifier":
            return str(get_node_text(child))
    return "anonymous"


def _kotlin_class_kind(
    node: Any,
    kind: str,
    get_node_text: Callable[..., str],
) -> str:
    if kind != "class":
        return kind
    for child in node.children:
        if child.type == "interface":
            return "interface"
        if child.type == "class":
            break
    return _refine_kotlin_class_kind(node, get_node_text)


def _kotlin_class_visibility(
    node: Any,
    get_node_text: Callable[..., str],
) -> str:
    modifiers_node = node.child_by_field_name("modifiers")
    return (
        determine_visibility(get_node_text(modifiers_node))
        if modifiers_node
        else "public"
    )


def extract_kotlin_class_or_object(
    node: Any,
    kind: str,
    get_node_text: Callable[..., str],
    current_package: str,
) -> Class | None:
    """Extract a Kotlin class, object, interface, or refined class kind."""
    try:
        superclass, interfaces = _extract_kotlin_delegation(node, get_node_text)
        return Class(
            name=_kotlin_class_name(node, get_node_text),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=get_node_text(node),
            language="kotlin",
            class_type=_kotlin_class_kind(node, kind, get_node_text),
            visibility=_kotlin_class_visibility(node, get_node_text),
            package_name=current_package,
            superclass=superclass,
            interfaces=interfaces,
        )
    except Exception as exc:
        log_error(f"Error extracting Kotlin class: {exc}")
        return None


def _identifier_child(node: Any) -> Any | None:
    return next(
        (
            child
            for child in node.children
            if child.type in ("simple_identifier", "identifier")
        ),
        None,
    )


def _extract_kotlin_property_name(
    node: Any,
    get_node_text: Callable[..., str],
) -> str:
    """Return a property binding from field, declaration, or direct child."""
    name_node = node.child_by_field_name("name")
    if name_node:
        return str(get_node_text(name_node))
    for child in node.children:
        candidate = (
            _identifier_child(child) if child.type == "variable_declaration" else child
        )
        if candidate is not None and candidate.type in (
            "simple_identifier",
            "identifier",
        ):
            return str(get_node_text(candidate))
    return "unknown"


def _extract_kotlin_property_modifiers(
    node: Any,
    get_node_text: Callable[..., str],
) -> tuple[str, list[str]]:
    """Return property visibility and supported non-visibility modifiers."""
    visibility = "public"
    modifiers: list[str] = []
    modifiers_node = next(
        (child for child in node.children if child.type == "modifiers"),
        None,
    )
    if modifiers_node is None:
        return visibility, modifiers
    for child in modifiers_node.children:
        keyword = get_node_text(child).strip()
        if keyword in _KOTLIN_PROPERTY_VISIBILITY_MODIFIERS:
            visibility = keyword
        if keyword in _KOTLIN_PROPERTY_OTHER_MODIFIERS:
            modifiers.append(keyword)
    return visibility, modifiers


def _kotlin_property_kind(node: Any) -> tuple[bool, bool]:
    for child in node.children:
        if child.type == "val":
            return True, False
        if child.type == "var":
            return False, True
    return False, False


def _kotlin_property_type(
    node: Any,
    get_node_text: Callable[..., str],
) -> str:
    declaration = next(
        (child for child in node.children if child.type == "variable_declaration"),
        None,
    )
    if declaration is None:
        return "Inferred"
    type_node = next(
        (
            child
            for child in declaration.children
            if "type" in child.type or child.type == "user_type"
        ),
        None,
    )
    return "Inferred" if type_node is None else str(get_node_text(type_node))


def extract_kotlin_property(
    node: Any,
    get_node_text: Callable[..., str],
) -> Variable | None:
    """Extract a Kotlin property and its val/var/const semantics."""
    try:
        is_val, is_var = _kotlin_property_kind(node)
        visibility, modifiers = _extract_kotlin_property_modifiers(node, get_node_text)
        variable = Variable(
            name=_extract_kotlin_property_name(node, get_node_text),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=get_node_text(node),
            language="kotlin",
            variable_type=_kotlin_property_type(node, get_node_text),
            visibility=visibility,
            modifiers=modifiers,
        )
        variable.is_val = is_val
        variable.is_var = is_var
        if "const" in modifiers:
            variable.is_static = True
            variable.is_readonly = True
        return variable
    except Exception as exc:
        log_error(f"Error extracting Kotlin property: {exc}")
        return None
