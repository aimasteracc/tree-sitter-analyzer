"""PHP use, visibility, and utility helpers — extracted from php_plugin.py."""

from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Import, Variable
from ..utils import log_error


def determine_visibility(modifiers: list[str]) -> str:
    """Determine visibility from PHP modifiers."""
    if "public" in modifiers:
        return "public"
    elif "private" in modifiers:
        return "private"
    elif "protected" in modifiers:
        return "protected"
    return "public"


# Extract elements from AST: extract_modifiers
def extract_modifiers(
    node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract modifiers from a PHP declaration node."""
    modifiers: list[str] = []
    for child in node.children:
        if child.type in (
            "visibility_modifier",
            "static_modifier",
            "final_modifier",
            "abstract_modifier",
            "readonly_modifier",
        ):
            modifiers.append(get_node_text(child))
    return modifiers


# Extract elements from AST: extract_attributes
def extract_attributes(
    node: Any,
    get_node_text: Callable[..., str],
    attribute_cache: dict[tuple[int, int], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Extract PHP 8+ attributes from a node."""
    cache_key = (node.start_byte, node.end_byte)
    if cache_key in attribute_cache:
        return attribute_cache[cache_key]

    attributes: list[dict[str, Any]] = []
    for child in node.children:
        if child.type == "attribute_list":
            for attr_group in child.children:
                if attr_group.type == "attribute_group":
                    for attr in attr_group.children:
                        if attr.type == "attribute":
                            name_node = attr.child_by_field_name("name")
                            if name_node:
                                attr_name = get_node_text(name_node)
                                attributes.append({"name": attr_name, "arguments": []})

    attribute_cache[cache_key] = attributes
    return attributes


# Extract elements from AST: extract_use_statement
def extract_use_statement(
    node: Any,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract use statement elements."""
    imports: list[Import] = []
    try:
        for child in node.children:
            if child.type == "namespace_use_clause":
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")

                if name_node:
                    import_name = get_node_text(name_node)
                    alias = None
                    if alias_node:
                        alias = get_node_text(alias_node)

                    imports.append(
                        Import(
                            name=import_name,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            alias=alias,
                            is_wildcard=False,
                        )
                    )
    except Exception as e:
        log_error(f"Error extracting use statement: {e}")
    return imports


# Extract elements from AST: extract_php_class_element
def extract_php_class_element(
    node: Any,
    current_namespace: str,
    get_node_text: Callable[..., str],
    extract_modifiers_fn: Callable[[Any], list[str]],
    extract_attributes_fn: Callable[[Any], list[dict[str, Any]]],
) -> Class | None:
    """Extract a single PHP class, interface, trait, or enum element."""
    try:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = get_node_text(name_node)
        modifiers = extract_modifiers_fn(node)
        visibility = determine_visibility(modifiers)
        attributes = extract_attributes_fn(node)

        base_classes: list[str] = []
        interfaces: list[str] = []

        for child in node.children:
            if child.type == "base_clause":
                base_node = child.child_by_field_name("type")
                if base_node:
                    base_classes.append(get_node_text(base_node))
            elif child.type == "class_interface_clause":
                for interface_node in child.children:
                    if interface_node.type == "name":
                        interfaces.append(get_node_text(interface_node))

        full_name = f"{current_namespace}\\{name}" if current_namespace else name

        class_type = "class"
        if node.type == "interface_declaration":
            class_type = "interface"
        elif node.type == "trait_declaration":
            class_type = "trait"
        elif node.type == "enum_declaration":
            class_type = "enum"

        return Class(
            name=full_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            visibility=visibility,
            is_abstract="abstract" in modifiers,
            full_qualified_name=full_name,
            superclass=base_classes[0] if base_classes else None,
            interfaces=interfaces,
            modifiers=modifiers,
            annotations=[{"name": attr["name"]} for attr in attributes],
            class_type=class_type,
        )
    except Exception as e:
        log_error(f"Error extracting class element: {e}")
        return None


# Extract elements from AST: extract_php_method_element
def extract_php_method_element(
    node: Any,
    parent_class: str,
    get_node_text: Callable[..., str],
    extract_modifiers_fn: Callable[[Any], list[str]],
    extract_attributes_fn: Callable[[Any], list[dict[str, Any]]],
) -> Function | None:
    """Extract a PHP method element."""
    try:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = get_node_text(name_node)
        modifiers = extract_modifiers_fn(node)
        visibility = determine_visibility(modifiers)
        attributes = extract_attributes_fn(node)

        parameters: list[str] = []
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for param in params_node.children:
                if param.type in ("simple_parameter", "property_promotion_parameter"):
                    parameters.append(get_node_text(param))

        return_type = "void"
        return_type_node = node.child_by_field_name("return_type")
        if return_type_node:
            return_type = get_node_text(return_type_node)

        return Function(
            name=f"{parent_class}::{name}" if parent_class else name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            visibility=visibility,
            is_static="static" in modifiers,
            is_async=False,
            is_abstract="abstract" in modifiers,
            parameters=parameters,
            return_type=return_type,
            modifiers=modifiers,
            annotations=[{"name": attr["name"]} for attr in attributes],
        )
    except Exception as e:
        log_error(f"Error extracting method element: {e}")
        return None


# Extract elements from AST: extract_php_function_element
def extract_php_function_element(
    node: Any,
    current_namespace: str,
    get_node_text: Callable[..., str],
) -> Function | None:
    """Extract a PHP function element."""
    try:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = get_node_text(name_node)

        parameters: list[str] = []
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for param in params_node.children:
                if param.type == "simple_parameter":
                    parameters.append(get_node_text(param))

        return_type = "void"
        return_type_node = node.child_by_field_name("return_type")
        if return_type_node:
            return_type = get_node_text(return_type_node)

        full_name = f"{current_namespace}\\{name}" if current_namespace else name

        return Function(
            name=full_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            visibility="public",
            is_static=False,
            is_async=False,
            is_abstract=False,
            parameters=parameters,
            return_type=return_type,
            modifiers=[],
            annotations=[],
        )
    except Exception as e:
        log_error(f"Error extracting function element: {e}")
        return None


# Extract elements from AST: extract_php_property_elements
def extract_php_property_elements(
    node: Any,
    parent_class: str,
    get_node_text: Callable[..., str],
    extract_modifiers_fn: Callable[[Any], list[str]],
) -> list[Variable]:
    """Extract PHP property elements."""
    variables: list[Variable] = []
    try:
        modifiers = extract_modifiers_fn(node)
        visibility = determine_visibility(modifiers)

        var_type = "mixed"
        type_node = node.child_by_field_name("type")
        if type_node:
            var_type = get_node_text(type_node)

        # Iterate over child
        for child in node.children:
            if child.type == "property_element":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = get_node_text(name_node).lstrip("$")
                    full_name = f"{parent_class}::{name}" if parent_class else name

                    variables.append(
                        Variable(
                            name=full_name,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            visibility=visibility,
                            is_static="static" in modifiers,
                            is_constant=False,
                            is_final=False,
                            is_readonly="readonly" in modifiers,
                            variable_type=var_type,
                            modifiers=modifiers,
                        )
                    )
    except Exception as e:
        log_error(f"Error extracting property elements: {e}")
    return variables


# Extract elements from AST: extract_php_constant_elements
def extract_php_constant_elements(
    node: Any,
    parent_class: str,
    get_node_text: Callable[..., str],
    extract_modifiers_fn: Callable[[Any], list[str]],
) -> list[Variable]:
    """Extract PHP constant elements."""
    variables: list[Variable] = []
    try:
        modifiers = extract_modifiers_fn(node)
        visibility = determine_visibility(modifiers)

        # Iterate over child
        for child in node.children:
            if child.type == "const_element":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = get_node_text(name_node)
                    full_name = f"{parent_class}::{name}" if parent_class else name

                    variables.append(
                        Variable(
                            name=full_name,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            visibility=visibility,
                            is_static=True,
                            is_constant=True,
                            is_final=True,
                            variable_type="const",
                            modifiers=modifiers,
                        )
                    )
    except Exception as e:
        log_error(f"Error extracting constant elements: {e}")
    return variables
