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
    """Extract Kotlin function parameters.

    r37dt (dogfood): flatten nesting 6 → 3 via ``_kotlin_parameter_pair``.
    """
    parameters: list[str] = []
    params_node = node.child_by_field_name("parameters")
    if params_node is None:
        return parameters
    for child in params_node.children:
        if child.type != "parameter":
            continue
        param_name, param_type = _kotlin_parameter_pair(child, get_node_text)
        if param_name:
            parameters.append(f"{param_name}: {param_type or 'Any'}")
    return parameters


def _kotlin_parameter_pair(
    parameter_node: Any, get_node_text: Callable[..., str]
) -> tuple[str, str]:
    """Return ``(name, type)`` from a Kotlin ``parameter`` AST node.

    Iterates the parameter node's children looking for a
    ``simple_identifier`` (name) and a type-like node (``user_type`` or
    any node whose ``type`` string contains ``"type"``). Empty strings
    default when either part is missing; caller fills ``"Any"`` for
    blank types.
    """
    param_name = ""
    param_type = ""
    for grandchild in parameter_node.children:
        if grandchild.type == "simple_identifier":
            param_name = get_node_text(grandchild)
        elif "type" in grandchild.type or grandchild.type == "user_type":
            param_type = get_node_text(grandchild)
    return param_name, param_type


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
_KOTLIN_CLASS_KIND_MODIFIERS = frozenset({"enum", "annotation", "data", "sealed"})


def _refine_kotlin_class_kind(node: Any, get_node_text: Callable[..., str]) -> str:
    """Return the declaration kind from the class_modifier, if any.

    ``enum class`` / ``annotation class`` / ``data class`` / ``sealed class``
    carry their kind as a ``class_modifier`` token under ``modifiers``.
    """
    for child in node.children:
        if child.type != "modifiers":
            continue
        for modifier in child.children:
            text = get_node_text(modifier)
            if text in _KOTLIN_CLASS_KIND_MODIFIERS:
                return str(text)
    return "class"


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
            # Theme-I (2026-06-10): class-kind fidelity. The grammar exposes
            # the declaration kind as a ``class_modifier`` inside ``modifiers``
            # ("enum class" / "annotation class" / "data class" /
            # "sealed class"); without this an agent could not tell a DTO from
            # an enum from an annotation in outlines. "inner" / "open" etc.
            # are nesting/inheritance modifiers, not kinds — left as "class".
            if kind == "class":
                kind = _refine_kotlin_class_kind(node, get_node_text)

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


def _extract_kotlin_property_name(
    node: Any,
    get_node_text: Callable[..., str],
) -> str:
    """Return the property name (val/var binding) for a Kotlin property node.

    r37ci (dogfood): extracted from ``extract_kotlin_property`` so the
    three lookup forms (``name`` field / ``variable_declaration`` /
    ``simple_identifier``) read as a flat chain.
    """
    name_node = node.child_by_field_name("name")
    if name_node:
        return str(get_node_text(name_node))
    for child in node.children:
        if child.type == "variable_declaration":
            for grandchild in child.children:
                if grandchild.type == "simple_identifier":
                    return str(get_node_text(grandchild))
        elif child.type == "simple_identifier":
            return str(get_node_text(child))
    return "unknown"


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

        # r37ci (dogfood): extracted to drop nesting from 7 to ≤3.
        name = _extract_kotlin_property_name(node, get_node_text)

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
