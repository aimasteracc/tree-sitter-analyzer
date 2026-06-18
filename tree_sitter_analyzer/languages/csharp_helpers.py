"""C# using, visibility, and utility helpers — extracted from csharp_plugin.py."""

from collections.abc import Callable, Iterator
from typing import Any

from ..models import Class, Function, Import, Variable
from ..utils import log_error

_OWNING_TYPE_NODES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "struct_declaration",
        "record_declaration",
        "enum_declaration",
    }
)


def find_owning_class_name(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Walk up node.parent to find the enclosing class/interface/struct/record.

    Returns the bare type name, or None when the member is at module scope.
    """
    parent = getattr(node, "parent", None)
    while parent is not None:
        if parent.type in _OWNING_TYPE_NODES:
            name_node = parent.child_by_field_name("name")
            if name_node:
                return get_node_text(name_node)
        parent = getattr(parent, "parent", None)
    return None


def determine_visibility(modifiers: list[str]) -> str:
    """Determine visibility from C# modifiers."""
    if "public" in modifiers:
        return "public"
    elif "private" in modifiers:
        return "private"
    elif "protected" in modifiers:
        return "protected"
    elif "internal" in modifiers:
        return "internal"
    return "private"


# Extract elements from AST: extract_parameters
def extract_parameters(
    params_node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract method parameters."""
    if not params_node:
        return []
    parameters: list[str] = []
    for child in params_node.children:
        if child.type == "parameter":
            parameters.append(get_node_text(child))
    return parameters


# Extract elements from AST: extract_type_name
def extract_type_name(
    type_node: Any,
    get_node_text: Callable[..., str],
) -> str:
    """Extract type name from a type node."""
    if not type_node:
        return "void"
    return get_node_text(type_node)


# Extract elements from AST: extract_modifiers
def extract_modifiers(
    node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract modifiers from a declaration node."""
    modifiers: list[str] = []
    for child in node.children:
        if child.type == "modifier":
            modifiers.append(get_node_text(child))
    return modifiers


def calculate_complexity(node: Any, traverse_fn: Callable[..., Iterator]) -> int:
    """Calculate cyclomatic complexity."""
    complexity = 1
    decision_keywords = {
        "if_statement",
        "switch_statement",
        "for_statement",
        "foreach_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
        "conditional_expression",
    }
    for child in traverse_fn(node):
        child_type = child.type
        if child_type in decision_keywords:
            complexity += 1
        elif child_type in ("&&", "||"):
            # Short-circuit boolean operators each add a decision point, but
            # only as logical operators (operands of a binary_expression),
            # matching the Go/Rust/Swift convention.
            parent = getattr(child, "parent", None)
            if (
                parent is not None
                and getattr(parent, "type", None) == "binary_expression"
            ):
                complexity += 1
    return complexity


# Extract elements from AST: extract_attributes
def extract_attributes(
    node: Any,
    get_node_text: Callable[..., str],
    attribute_cache: dict[tuple[int, int], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Extract attributes (annotations) from a node's direct children.

    In the tree-sitter-c-sharp grammar, attribute_list nodes appear as the
    first children of declaration nodes (class_declaration, method_declaration,
    etc.), not as prev_sibling nodes. Walking prev_sibling finds nothing.
    """
    cache_key = (node.start_byte, node.end_byte)
    if cache_key in attribute_cache:
        return attribute_cache[cache_key]

    attributes: list[dict[str, Any]] = []
    for child in node.children:
        if child.type != "attribute_list":
            break  # attribute_lists come first; stop on first non-attribute child
        attr_list_text = get_node_text(child)
        for attr_node in child.children:
            if attr_node.type != "attribute":
                continue
            attr_name = None
            for sub in attr_node.children:
                if sub.type in ("identifier", "qualified_name", "generic_name"):
                    attr_name = get_node_text(sub)
                    break
            if attr_name:
                attributes.append(
                    {
                        "name": attr_name,
                        "line": child.start_point[0] + 1,
                        "text": attr_list_text,
                    }
                )

    attribute_cache[cache_key] = attributes
    return attributes


# Extract elements from AST: extract_using_directive
def extract_using_directive(
    node: Any,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Extract a using directive."""
    try:
        name_node = node.child_by_field_name("name")
        if not name_node:
            for child in node.children:
                if child.type in ("qualified_name", "identifier", "name_equals"):
                    name_node = child
                    break

        if not name_node:
            return None

        import_name = get_node_text(name_node)

        is_static = False
        for child in node.children:
            if child.type == "static" or get_node_text(child) == "static":
                is_static = True
                break

        raw_text = get_node_text(node)

        return Import(
            name=import_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            language="csharp",
            module_name=import_name,
            is_static=is_static,
            import_statement=raw_text,
        )
    except Exception as e:
        log_error(f"Error extracting using directive: {e}")
        return None


_CLASS_TYPE_MAP = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "record_declaration": "record",
    "enum_declaration": "enum",
    "struct_declaration": "struct",
}

_BASE_TYPE_NODES = frozenset(["type_identifier", "generic_name", "qualified_name"])

_ACCESS_MODIFIERS = ("public", "private", "protected", "internal")


def _apply_interface_implicit_public(
    node: Any, modifiers: list[str], visibility: str
) -> str:
    """C# interface members without an explicit access modifier are public.

    Applies to methods, properties and events alike (#536, Codex P2 on the
    method-only first cut). Parent chain:
    ``<member>_declaration → declaration_list → interface_declaration``.
    """
    if visibility != "private" or any(m in modifiers for m in _ACCESS_MODIFIERS):
        return visibility
    parent = getattr(node, "parent", None)
    grandparent = getattr(parent, "parent", None) if parent is not None else None
    if getattr(grandparent, "type", None) == "interface_declaration":
        return "public"
    return visibility


# Extract elements from AST: extract_class_declaration
def extract_class_declaration(
    node: Any,
    current_namespace: str,
    get_node_text: Callable[..., str],
    extract_modifiers_fn: Callable[[Any], list[str]],
    extract_attributes_fn: Callable[[Any], list[dict[str, Any]]],
) -> Class | None:
    """Extract a single class declaration."""
    try:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        class_name = get_node_text(name_node)
        modifiers = extract_modifiers_fn(node)
        visibility = determine_visibility(modifiers)
        attributes = extract_attributes_fn(node)

        base_list_node = node.child_by_field_name("bases")
        superclass = None
        interfaces: list[str] = []

        if base_list_node:
            base_items = [
                get_node_text(child)
                for child in base_list_node.children
                if child.type in _BASE_TYPE_NODES
            ]
            if base_items:
                if node.type == "interface_declaration":
                    interfaces = base_items
                else:
                    superclass = base_items[0]
                    interfaces = base_items[1:] if len(base_items) > 1 else []

        full_name = (
            f"{current_namespace}.{class_name}" if current_namespace else class_name
        )

        raw_text = get_node_text(node)
        class_type = _CLASS_TYPE_MAP.get(node.type, "class")

        return Class(
            name=class_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            full_qualified_name=full_name,
            superclass=superclass,
            interfaces=interfaces,
            modifiers=modifiers,
            visibility=visibility,
            annotations=attributes,
            class_type=class_type,
        )
    except Exception as e:
        log_error(f"Error extracting class declaration: {e}")
        return None


# Extract elements from AST: extract_method_declaration
def extract_method_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    extract_modifiers_fn: Callable[[Any], list[str]],
    extract_attributes_fn: Callable[[Any], list[dict[str, Any]]],
    extract_type_fn: Callable[[Any], str],
    extract_params_fn: Callable[[Any], list[str]],
    calc_complexity_fn: Callable[[Any], int],
) -> Function | None:
    """Extract a method declaration."""
    try:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        method_name = get_node_text(name_node)
        modifiers = extract_modifiers_fn(node)
        visibility = _apply_interface_implicit_public(
            node, modifiers, determine_visibility(modifiers)
        )
        is_async = "async" in modifiers
        attributes = extract_attributes_fn(node)

        # tree-sitter-c-sharp uses the field name "returns" for the return type of
        # a method_declaration (not "type" — that is used by property_declaration).
        type_node = node.child_by_field_name("returns")
        return_type = extract_type_fn(type_node)

        params_node = node.child_by_field_name("parameters")
        parameters = extract_params_fn(params_node)

        raw_text = get_node_text(node)
        complexity_score = calc_complexity_fn(node)

        return Function(
            name=method_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            parameters=parameters,
            return_type=return_type,
            modifiers=modifiers,
            visibility=visibility,
            is_async=is_async,
            annotations=attributes,
            complexity_score=complexity_score,
        )
    except Exception as e:
        log_error(f"Error extracting method: {e}")
        return None


# Extract elements from AST: extract_constructor_declaration
def extract_constructor_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    extract_modifiers_fn: Callable[[Any], list[str]],
    extract_attributes_fn: Callable[[Any], list[dict[str, Any]]],
    extract_params_fn: Callable[[Any], list[str]],
) -> Function | None:
    """Extract a constructor declaration."""
    try:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        constructor_name = get_node_text(name_node)
        modifiers = extract_modifiers_fn(node)
        visibility = determine_visibility(modifiers)
        attributes = extract_attributes_fn(node)

        params_node = node.child_by_field_name("parameters")
        parameters = extract_params_fn(params_node)

        raw_text = get_node_text(node)

        return Function(
            name=constructor_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            parameters=parameters,
            return_type="void",
            modifiers=modifiers,
            visibility=visibility,
            is_constructor=True,
            annotations=attributes,
        )
    except Exception as e:
        log_error(f"Error extracting constructor: {e}")
        return None


# Extract elements from AST: extract_property_declaration
def extract_property_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    extract_modifiers_fn: Callable[[Any], list[str]],
    extract_attributes_fn: Callable[[Any], list[dict[str, Any]]],
    extract_type_fn: Callable[[Any], str],
) -> Function | None:
    """Extract a property declaration."""
    # Error handling block
    try:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        property_name = get_node_text(name_node)
        modifiers = extract_modifiers_fn(node)
        visibility = _apply_interface_implicit_public(
            node, modifiers, determine_visibility(modifiers)
        )
        attributes = extract_attributes_fn(node)

        type_node = node.child_by_field_name("type")
        property_type = extract_type_fn(type_node)

        raw_text = get_node_text(node)

        return Function(
            name=property_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            parameters=[],
            return_type=property_type,
            modifiers=modifiers,
            visibility=visibility,
            is_property=True,
            annotations=attributes,
        )
    except Exception as e:
        log_error(f"Error extracting property: {e}")
        return None


def _find_variable_declaration(node: Any) -> Any | None:
    for child in node.children:
        if child.type == "variable_declaration":
            return child
    return None


def _iter_variable_declarators(variable_declaration: Any | None) -> Iterator[Any]:
    if variable_declaration is None:
        return
    for declarator in variable_declaration.children:
        if declarator.type == "variable_declarator":
            yield declarator


def _extract_declarator_name(
    declarator: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    name_node = declarator.child_by_field_name("name")
    if not name_node:
        return None
    return get_node_text(name_node)


# Extract elements from AST: extract_field_declaration
def extract_field_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    extract_modifiers_fn: Callable[[Any], list[str]],
    extract_attributes_fn: Callable[[Any], list[dict[str, Any]]],
    extract_type_fn: Callable[[Any], str],
) -> list[Variable]:
    """Extract field declarations."""
    variables: list[Variable] = []

    # Error handling block
    try:
        modifiers = extract_modifiers_fn(node)
        visibility = determine_visibility(modifiers)
        is_constant = "const" in modifiers
        attributes = extract_attributes_fn(node)
        variable_declaration = _find_variable_declaration(node)
        type_node = (
            variable_declaration.child_by_field_name("type")
            if variable_declaration
            else None
        )
        field_type = extract_type_fn(type_node)
        raw_text = get_node_text(node)

        for declarator in _iter_variable_declarators(variable_declaration):
            field_name = _extract_declarator_name(declarator, get_node_text)
            if field_name is None:
                continue
            variables.append(
                Variable(
                    name=field_name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    raw_text=raw_text,
                    variable_type=field_type,
                    modifiers=modifiers,
                    visibility=visibility,
                    is_constant=is_constant,
                    annotations=attributes,
                )
            )
    except Exception as e:
        log_error(f"Error extracting field: {e}")

    return variables


# Extract elements from AST: extract_event_declaration
def extract_event_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    extract_modifiers_fn: Callable[[Any], list[str]],
    extract_attributes_fn: Callable[[Any], list[dict[str, Any]]],
    extract_type_fn: Callable[[Any], str],
) -> list[Variable]:
    """Extract event field declarations."""
    variables: list[Variable] = []

    # Error handling block
    try:
        modifiers = extract_modifiers_fn(node)
        modifiers.append("event")
        visibility = _apply_interface_implicit_public(
            node, modifiers, determine_visibility(modifiers)
        )
        attributes = extract_attributes_fn(node)
        variable_declaration = _find_variable_declaration(node)
        type_node = (
            variable_declaration.child_by_field_name("type")
            if variable_declaration
            else None
        )
        event_type = extract_type_fn(type_node)
        raw_text = get_node_text(node)

        for declarator in _iter_variable_declarators(variable_declaration):
            event_name = _extract_declarator_name(declarator, get_node_text)
            if event_name is None:
                continue
            variables.append(
                Variable(
                    name=event_name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    raw_text=raw_text,
                    variable_type=event_type,
                    modifiers=modifiers,
                    visibility=visibility,
                    annotations=attributes,
                )
            )
    except Exception as e:
        log_error(f"Error extracting event: {e}")

    return variables
