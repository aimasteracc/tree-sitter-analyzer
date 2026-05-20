"""C++ visibility and complexity helpers — extracted from cpp_plugin.py."""

from collections.abc import Callable
from typing import Any

from ._cpp_complexity_helpers import calculate_complexity
from ._cpp_element_helpers import (
    CppClassExtractionContext,
    CppFunctionExtractionContext,
    extract_cpp_class,
    extract_cpp_function,
)
from ._cpp_field_function_helpers import (
    CppFieldFunctionExtractionContext,
    extract_function_declaration,
    extract_function_from_field_declaration,
)
from ._cpp_import_namespace_helpers import (
    _extract_include_info,
    _extract_includes_fallback,
    _extract_namespace_info,
    extract_cpp_imports,
    extract_cpp_namespaces,
)
from ._cpp_signature_helpers import (
    extract_comment_for_line,
    extract_parameters,
    parse_function_signature,
)
from ._cpp_traversal_helpers import (
    CppTraversalState,
    traverse_and_extract_iterative,
)
from ._cpp_variable_helpers import (
    extract_base_classes,
    extract_cpp_field_declaration,
    extract_cpp_variable_declaration,
)

__all__ = [
    "CppClassExtractionContext",
    "CppFieldFunctionExtractionContext",
    "CppFunctionExtractionContext",
    "CppTraversalState",
    "_extract_include_info",
    "_extract_includes_fallback",
    "_extract_namespace_info",
    "calculate_complexity",
    "determine_visibility",
    "extract_base_classes",
    "extract_comment_for_line",
    "extract_cpp_class",
    "extract_cpp_field_declaration",
    "extract_cpp_function",
    "extract_cpp_imports",
    "extract_cpp_namespaces",
    "extract_cpp_variable_declaration",
    "extract_function_declaration",
    "extract_function_from_field_declaration",
    "extract_parameters",
    "get_access_specifier",
    "is_global_scope",
    "parse_function_signature",
    "traverse_and_extract_iterative",
]


def is_global_scope(node: Any) -> bool:
    """Check if a node is in global scope (not inside a class/struct/union)."""
    current = node.parent
    while current is not None:
        if current.type in (
            "class_specifier",
            "struct_specifier",
            "union_specifier",
        ):
            return False
        current = current.parent
    return True


def get_access_specifier(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Get the current access specifier for a class member."""
    parent = node.parent
    if not parent or parent.type != "field_declaration_list":
        return None

    siblings = list(parent.children)
    try:
        node_index = siblings.index(node)
    except ValueError:
        return None

    for i in range(node_index - 1, -1, -1):
        sibling = siblings[i]
        if sibling.type == "access_specifier":
            spec_text = get_node_text(sibling).strip().rstrip(":")
            if spec_text in ("public", "private", "protected"):
                return spec_text

    class_node = parent.parent
    if class_node:
        if class_node.type == "class_specifier":
            return "private"
        elif class_node.type in ("struct_specifier", "union_specifier"):
            return "public"

    return None


def determine_visibility(
    modifiers: list[str],
    is_global: bool = False,
    node: Any = None,
    get_node_text: Callable[..., str] | None = None,
) -> str:
    """Determine visibility from modifiers and context."""
    if "public" in modifiers:
        return "public"
    elif "private" in modifiers:
        return "private"
    elif "protected" in modifiers:
        return "protected"

    if "static" in modifiers and is_global:
        return "private"

    if node and not is_global and get_node_text:
        access_spec = get_access_specifier(node, get_node_text)
        if access_spec:
            return access_spec

    return "public" if is_global else "private"
