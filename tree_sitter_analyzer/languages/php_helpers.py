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
    # r37cn (dogfood): extracted to flatten nesting from 8 to ≤3.
    for child in node.children:
        if child.type == "attribute_list":
            _collect_php_attribute_list(child, get_node_text, attributes)
    attribute_cache[cache_key] = attributes
    return attributes


def _collect_php_attribute_list(
    attribute_list_node: Any,
    get_node_text: Callable[..., str],
    attributes: list[dict[str, Any]],
) -> None:
    """Walk one ``attribute_list`` node, appending each attribute name.

    r37cn: extracted from ``extract_php_attributes`` so the 4-level for/if
    chain (attribute_list → attribute_group → attribute → name) reads as
    two focused helpers.
    """
    for attr_group in attribute_list_node.children:
        if attr_group.type != "attribute_group":
            continue
        for attr in attr_group.children:
            if attr.type != "attribute":
                continue
            name_node = attr.child_by_field_name("name")
            if name_node is None:
                continue
            attributes.append({"name": get_node_text(name_node), "arguments": []})


# Extract elements from AST: extract_use_statement
def extract_use_statement(
    node: Any,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract use statement elements.

    r37co (dogfood): extracted per-clause logic to flatten nesting 7 → 3.
    """
    imports: list[Import] = []
    try:
        for child in node.children:
            if child.type != "namespace_use_clause":
                continue
            imp = _build_use_clause_import(node, child, get_node_text)
            if imp is not None:
                imports.append(imp)
    except Exception as e:
        log_error(f"Error extracting use statement: {e}")
    return imports


def _build_use_clause_import(
    use_node: Any,
    clause_node: Any,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Build one ``Import`` from a ``namespace_use_clause`` node."""
    name_node = clause_node.child_by_field_name("name")
    if not name_node:
        return None
    alias_node = clause_node.child_by_field_name("alias")
    alias = get_node_text(alias_node) if alias_node else None
    return Import(
        name=get_node_text(name_node),
        start_line=use_node.start_point[0] + 1,
        end_line=use_node.end_point[0] + 1,
        alias=alias,
        is_wildcard=False,
    )


# Extract elements from AST: extract_php_class_element
def _collect_php_class_bases(
    node: Any, get_node_text: Callable[..., str]
) -> tuple[list[str], list[str]]:
    """Return ``(base_classes, interfaces)`` from a PHP class declaration.

    ``base_clause`` carries the parent class via its ``type`` field;
    ``class_interface_clause`` lists implementations as ``name`` children.
    Mixed lists are flattened — caller decides what to do with empties.

    r37dt (dogfood): lifted from ``extract_php_class_element`` to flatten
    the 4-level for/elif/for/if chain (nesting 6 → 3).
    """
    base_classes: list[str] = []
    interfaces: list[str] = []
    for child in node.children:
        if child.type == "base_clause":
            # Theme-C (2026-06-10): tree-sitter-php 0.24 exposes the parent
            # as plain ``name`` / ``qualified_name`` children (no ``type``
            # field) — the old field lookup returned None and ``extends``
            # was silently lost. Keep the field lookup as a fast path for
            # older grammars, fall back to child iteration.
            base_node = child.child_by_field_name("type")
            if base_node:
                base_classes.append(get_node_text(base_node))
            else:
                for name_node in child.children:
                    if name_node.type in ("name", "qualified_name"):
                        base_classes.append(get_node_text(name_node))
        elif child.type == "class_interface_clause":
            for interface_node in child.children:
                if interface_node.type in ("name", "qualified_name"):
                    interfaces.append(get_node_text(interface_node))
    return base_classes, interfaces


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

        # r37dt (dogfood): flatten nesting 6 → 3 via _collect_php_class_bases.
        base_classes, interfaces = _collect_php_class_bases(node, get_node_text)
        # Theme-C review fix (2026-06-10): ``interface I extends A, B`` puts
        # ALL parents in base_clause — for an interface they are parent
        # interfaces, not a single superclass; routing only [0] to superclass
        # silently dropped the rest. Classes keep first-as-superclass (PHP
        # classes are single-inheritance; extras would be a parse anomaly and
        # are preserved in interfaces rather than dropped).
        if node.type == "interface_declaration":
            interfaces = base_classes + interfaces
            base_classes = []
        elif len(base_classes) > 1:
            interfaces = base_classes[1:] + interfaces
            base_classes = base_classes[:1]

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
                if param.type in (
                    "simple_parameter",
                    "property_promotion_parameter",
                    "variadic_parameter",  # Theme E (2026-06-10): ...$arg
                ):
                    parameters.append(get_node_text(param))

        return_type = "void"
        return_type_node = node.child_by_field_name("return_type")
        if return_type_node:
            return_type = get_node_text(return_type_node)

        return Function(
            name=name,  # bare name — owner lives in receiver_type (#535)
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
            receiver_type=parent_class if parent_class else None,
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
                if param.type in (
                    "simple_parameter",
                    "variadic_parameter",  # Theme E (2026-06-10): ...$arg
                ):
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
        type_node = node.child_by_field_name("type")
        var_type = get_node_text(type_node) if type_node else "mixed"

        # r37cp (dogfood): extracted to flatten nesting 7 → 3.
        for child in node.children:
            if child.type != "property_element":
                continue
            var = _build_php_property_variable(
                node,
                child,
                parent_class,
                get_node_text,
                modifiers,
                visibility,
                var_type,
            )
            if var is not None:
                variables.append(var)
    except Exception as e:
        log_error(f"Error extracting property elements: {e}")
    return variables


def _build_php_property_variable(
    property_node: Any,
    element_node: Any,
    parent_class: str,
    get_node_text: Callable[..., str],
    modifiers: list[str],
    visibility: str,
    var_type: str,
) -> Variable | None:
    """Build a ``Variable`` from one ``property_element`` AST child."""
    name_node = element_node.child_by_field_name("name")
    if name_node is None:
        return None
    name = get_node_text(name_node).lstrip("$")
    # bare name — owner travels in receiver_type (#535, Codex P2: without it
    # multi-class files collide on field names in structured output)
    return Variable(
        name=name,
        start_line=property_node.start_point[0] + 1,
        end_line=property_node.end_point[0] + 1,
        visibility=visibility,
        is_static="static" in modifiers,
        is_constant=False,
        is_final=False,
        is_readonly="readonly" in modifiers,
        variable_type=var_type,
        modifiers=modifiers,
        receiver_type=parent_class or None,
    )


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
        # r37cq (dogfood): extracted to flatten nesting 7 → 3.
        for child in node.children:
            if child.type != "const_element":
                continue
            var = _build_php_constant_variable(
                node, child, parent_class, get_node_text, modifiers, visibility
            )
            if var is not None:
                variables.append(var)
    except Exception as e:
        log_error(f"Error extracting constant elements: {e}")
    return variables


def _build_php_constant_variable(
    const_node: Any,
    element_node: Any,
    parent_class: str,
    get_node_text: Callable[..., str],
    modifiers: list[str],
    visibility: str,
) -> Variable | None:
    """Build a ``Variable`` from one ``const_element`` AST child."""
    name_node = element_node.child_by_field_name("name")
    if name_node is None:
        return None
    name = get_node_text(name_node)
    # bare name — owner travels in receiver_type (#535, Codex P2)
    return Variable(
        name=name,
        start_line=const_node.start_point[0] + 1,
        end_line=const_node.end_point[0] + 1,
        visibility=visibility,
        is_static=True,
        is_constant=True,
        is_final=True,
        variable_type="const",
        modifiers=modifiers,
        receiver_type=parent_class or None,
    )
