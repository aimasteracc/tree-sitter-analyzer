"""C# using, visibility, and utility helpers — extracted from csharp_plugin.py."""

from collections.abc import Callable, Iterator
from typing import Any

from ..models import Class, Function, Import, Variable
from ..utils import log_error


# Process: determine_visibility
# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
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


# Process: calculate_complexity
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
        if child.type in decision_keywords:
            complexity += 1
    return complexity


# Extract elements from AST: extract_attributes
def extract_attributes(
    node: Any,
    get_node_text: Callable[..., str],
    attribute_cache: dict[tuple[int, int], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Extract attributes (annotations) from a node."""
    cache_key = (node.start_byte, node.end_byte)
    if cache_key in attribute_cache:
        return attribute_cache[cache_key]

    attributes: list[dict[str, Any]] = []
    prev_sibling = node.prev_sibling
    while prev_sibling:
        if prev_sibling.type == "attribute_list":
            attr_text = get_node_text(prev_sibling)
            attributes.append(
                {
                    "name": attr_text.strip("[]"),
                    "line": prev_sibling.start_point[0] + 1,
                    "text": attr_text,
                }
            )
        elif prev_sibling.type not in ("comment", "line_comment", "block_comment"):
            break
        prev_sibling = prev_sibling.prev_sibling

    attributes.reverse()
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
        # Check: not name_node
        if not name_node:
            # Return result
            return None

        method_name = get_node_text(name_node)
        modifiers = extract_modifiers_fn(node)
        visibility = determine_visibility(modifiers)
        is_async = "async" in modifiers
        attributes = extract_attributes_fn(node)

        type_node = node.child_by_field_name("type")
        return_type = extract_type_fn(type_node)

        params_node = node.child_by_field_name("parameters")
        parameters = extract_params_fn(params_node)

        raw_text = get_node_text(node)
        complexity_score = calc_complexity_fn(node)

        # Return result
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
        # Return result
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
        # Check: not name_node
        if not name_node:
            # Return result
            return None

        constructor_name = get_node_text(name_node)
        modifiers = extract_modifiers_fn(node)
        visibility = determine_visibility(modifiers)
        attributes = extract_attributes_fn(node)

        params_node = node.child_by_field_name("parameters")
        parameters = extract_params_fn(params_node)

        raw_text = get_node_text(node)

        # Return result
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
        # Return result
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
    try:
        name_node = node.child_by_field_name("name")
        # Check: not name_node
        if not name_node:
            # Return result
            return None

        property_name = get_node_text(name_node)
        modifiers = extract_modifiers_fn(node)
        visibility = determine_visibility(modifiers)
        attributes = extract_attributes_fn(node)

        type_node = node.child_by_field_name("type")
        property_type = extract_type_fn(type_node)

        raw_text = get_node_text(node)

        # Return result
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
        # Return result
        return None


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

    try:
        modifiers = extract_modifiers_fn(node)
        visibility = determine_visibility(modifiers)
        is_constant = "const" in modifiers
        attributes = extract_attributes_fn(node)

        type_node = None
        # Iterate over child
        for child in node.children:
            # Check: child.type == "variable_declaration"
            if child.type == "variable_declaration":
                type_node = child.child_by_field_name("type")
                break

        field_type = extract_type_fn(type_node)

        # Iterate over child
        for child in node.children:
            # Check: child.type == "variable_declaration"
            if child.type == "variable_declaration":
                # Iterate over declarator
                for declarator in child.children:
                    # Check: declarator.type == "variable_declarator"
                    if declarator.type == "variable_declarator":
                        name_node = declarator.child_by_field_name("name")
                        # Check: name_node
                        if name_node:
                            field_name = get_node_text(name_node)
                            raw_text = get_node_text(node)

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

    # Return result
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

    try:
        modifiers = extract_modifiers_fn(node)
        modifiers.append("event")
        visibility = determine_visibility(modifiers)
        attributes = extract_attributes_fn(node)

        type_node = None
        # Iterate over child
        for child in node.children:
            # Check: child.type == "variable_declaration"
            if child.type == "variable_declaration":
                type_node = child.child_by_field_name("type")
                break

        event_type = extract_type_fn(type_node)

        # Iterate over child
        for child in node.children:
            # Check: child.type == "variable_declaration"
            if child.type == "variable_declaration":
                # Iterate over declarator
                for declarator in child.children:
                    # Check: declarator.type == "variable_declarator"
                    if declarator.type == "variable_declarator":
                        name_node = declarator.child_by_field_name("name")
                        # Check: name_node
                        if name_node:
                            event_name = get_node_text(name_node)
                            raw_text = get_node_text(node)

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

    # Return result
    return variables



