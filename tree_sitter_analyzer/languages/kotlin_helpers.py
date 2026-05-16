"""Kotlin import, visibility, and utility helpers — extracted from kotlin_plugin.py."""

from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Import, Variable
from ..utils import log_error


def extract_import(node: Any, get_node_text: Callable[..., str]) -> Import | None:
    """Extract import header."""
    try:
        raw_text = get_node_text(node)
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        parts = raw_text.split()
        name = parts[1] if len(parts) > 1 else "unknown"

        return Import(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="kotlin",
            import_statement=raw_text,
        )
    except Exception as e:
        log_error(f"Error extracting Kotlin import: {e}")
        return None


def determine_visibility(modifiers_text: str) -> str:
    """Determine visibility from Kotlin modifiers text."""
    if "private" in modifiers_text:
        return "private"
    elif "protected" in modifiers_text:
        return "protected"
    elif "internal" in modifiers_text:
        return "internal"
    return "public"


def extract_kotlin_parameters(
    node: Any, get_node_text: Callable[..., str]
) -> list[str]:
    """Extract Kotlin function parameters."""
    parameters: list[str] = []
    params_node = node.child_by_field_name("parameters")
    if params_node:
        for child in params_node.children:
            if child.type == "parameter":
                param_name = ""
                param_type = ""
                for grandchild in child.children:
                    if grandchild.type == "simple_identifier":
                        param_name = get_node_text(grandchild)
                    elif "type" in grandchild.type or grandchild.type == "user_type":
                        param_type = get_node_text(grandchild)
                if param_name:
                    parameters.append(f"{param_name}: {param_type or 'Any'}")
    return parameters


def extract_kotlin_function(
    node: Any,
    get_node_text: Callable[..., str],
    current_package: str,
) -> Function | None:
    """Extract Kotlin function declaration."""
    try:
        name = "anonymous"
        name_node = node.child_by_field_name("name")
        if name_node:
            name = get_node_text(name_node)
        else:
            for child in node.children:
                if child.type == "simple_identifier":
                    name = get_node_text(child)
                    break

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        parameters = extract_kotlin_parameters(node, get_node_text)

        return_type = "Unit"
        for i, child in enumerate(node.children):
            if child.type == ":":
                if i + 1 < len(node.children):
                    return_type = get_node_text(node.children[i + 1])
                break

        visibility = "public"
        is_suspend = False
        modifiers_node = node.child_by_field_name("modifiers")
        if modifiers_node:
            mods = get_node_text(modifiers_node)
            visibility = determine_visibility(mods)
            is_suspend = "suspend" in mods

        raw_text = get_node_text(node)

        func = Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="kotlin",
            parameters=parameters,
            return_type=return_type,
            visibility=visibility,
        )
        func.is_suspend = is_suspend
        return func

    except Exception as e:
        log_error(f"Error extracting Kotlin function: {e}")
        return None


# Extract elements from AST: extract_kotlin_class_or_object
def extract_kotlin_class_or_object(
    node: Any,
    kind: str,
    get_node_text: Callable[..., str],
    current_package: str,
) -> Class | None:
    """Extract Kotlin class/object/interface declaration."""
    try:
        name = "anonymous"
        name_node = node.child_by_field_name("name")
        if name_node:
            name = get_node_text(name_node)
        else:
            for child in node.children:
                if child.type == "simple_identifier":
                    name = get_node_text(child)
                    break

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        visibility = "public"
        modifiers_node = node.child_by_field_name("modifiers")
        if modifiers_node:
            visibility = determine_visibility(get_node_text(modifiers_node))

        if kind == "class":
            for child in node.children:
                if child.type == "interface":
                    kind = "interface"
                    break
                elif child.type == "class":
                    break

        raw_text = get_node_text(node)

        return Class(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="kotlin",
            class_type=kind,
            visibility=visibility,
            package_name=current_package,
        )

    except Exception as e:
        log_error(f"Error extracting Kotlin class: {e}")
        return None


# Extract elements from AST: extract_kotlin_property
def extract_kotlin_property(
    node: Any,
    get_node_text: Callable[..., str],
) -> Variable | None:
    """Extract Kotlin property declaration."""
    try:
        is_val = False
        is_var = False
        text = get_node_text(node)
        if text.startswith("val "):
            is_val = True
        elif text.startswith("var "):
            is_var = True

        name = "unknown"

        name_node = node.child_by_field_name("name")
        if name_node:
            name = get_node_text(name_node)
        else:
            for child in node.children:
                if child.type == "variable_declaration":
                    for grandchild in child.children:
                        if grandchild.type == "simple_identifier":
                            name = get_node_text(grandchild)
                            break
                elif child.type == "simple_identifier":
                    name = get_node_text(child)
                    break

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        prop_type = "Inferred"

        visibility = "public"
        modifiers_node = node.child_by_field_name("modifiers")
        if modifiers_node:
            visibility = determine_visibility(get_node_text(modifiers_node))

        raw_text = get_node_text(node)

        var = Variable(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="kotlin",
            variable_type=prop_type,
            visibility=visibility,
        )
        var.is_val = is_val
        var.is_var = is_var

        return var

    except Exception as e:
        log_error(f"Error extracting Kotlin property: {e}")
        return None

