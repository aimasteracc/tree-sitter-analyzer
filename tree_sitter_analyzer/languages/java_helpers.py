"""Java import, package, and utility helpers — extracted from java_plugin.py."""

import re
from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Variable
from ..utils import log_debug, log_error, log_warning
from ._java_ast import (
    calculate_complexity,
    extract_modifiers,
    parse_field_declaration,
    parse_method_signature,
)
from ._java_element import (
    extract_java_class as _extract_java_class_impl,
)
from ._java_element import (
    extract_java_field as _extract_java_field_impl,
)
from ._java_element import (
    extract_java_method as _extract_java_method_impl,
)
from ._java_element import (
    extract_javadoc_for_line as _extract_javadoc_for_line_impl,
)
from ._java_import import (
    _extract_import_info,
    _extract_imports_fallback,
    _extract_package_element,
    _extract_package_name,
    extract_java_imports,
    extract_java_packages,
)
from ._java_traversal import (
    _process_field_batch,
)
from ._java_traversal import (
    java_traverse_and_extract as _java_traverse_and_extract_impl,
)

__all__ = [
    "_extract_import_info",
    "_extract_imports_fallback",
    "_extract_package_element",
    "_extract_package_name",
    "_process_field_batch",
    "calculate_complexity",
    "determine_visibility",
    "extract_annotation",
    "extract_class_name",
    "extract_java_class",
    "extract_java_field",
    "extract_java_imports",
    "extract_java_method",
    "extract_java_packages",
    "extract_javadoc_for_line",
    "extract_modifiers",
    "find_parent_class",
    "is_nested_class",
    "java_traverse_and_extract",
    "parse_field_declaration",
    "parse_method_signature",
]

_CLASS_DECLARATION_NODES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
    }
)


def determine_visibility(modifiers: list[str]) -> str:
    """Determine visibility from Java modifiers."""
    if "public" in modifiers:
        return "public"
    elif "private" in modifiers:
        return "private"
    elif "protected" in modifiers:
        return "protected"
    return "package"


def is_nested_class(node: Any) -> bool:
    """Check if a node is inside a class/interface/enum declaration."""
    return _find_parent_class_node(node) is not None


# Search for patterns or elements: find_parent_class
def find_parent_class(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Find parent class name for nested classes."""
    parent = _find_parent_class_node(node)
    if not parent:
        return None
    return _first_child_text(parent, {"identifier"}, get_node_text)


def _find_parent_class_node(node: Any) -> Any | None:
    parent = node.parent
    while parent:
        if parent.type in _CLASS_DECLARATION_NODES:
            return parent
        parent = parent.parent
    return None


# Extract elements from AST: extract_class_name
def extract_class_name(
    node: Any,
    get_node_text: Callable[..., str],
) -> str | None:
    """Extract class name from a class declaration node."""
    try:
        return _first_child_text(node, {"identifier"}, get_node_text)
    except Exception as e:
        log_debug(f"Failed to extract class name: {e}")
    return None


def _first_child_text(
    node: Any,
    child_types: frozenset[str] | set[str],
    get_node_text: Callable[..., str],
) -> str | None:
    for child in node.children:
        if child.type in child_types:
            return get_node_text(child)
    return None


# Extract elements from AST: extract_annotation
def extract_annotation(
    node: Any,
    get_node_text: Callable[..., str],
) -> dict[str, Any] | None:
    """Extract annotation information from annotation node."""
    try:
        annotation_text = get_node_text(node)
        start_line = node.start_point[0] + 1

        annotation_name = None
        for child in node.children:
            if child.type == "identifier":
                annotation_name = get_node_text(child)
                break

        if not annotation_name:
            match = re.search(r"@(\w+)", annotation_text)
            if match:
                annotation_name = match.group(1)

        if annotation_name:
            return {
                "name": annotation_name,
                "line": start_line,
                "text": annotation_text,
                "type": "annotation",
            }
    except Exception as e:
        log_debug(f"Failed to extract annotation: {e}")

    return None


# Extract elements from AST: extract_javadoc_for_line
def extract_javadoc_for_line(line: int, content_lines: list[str]) -> str | None:
    """Extract JavaDoc comment for a specific line."""
    return _extract_javadoc_for_line_impl(
        line,
        content_lines,
        log_debug_func=log_debug,
    )


# Extract elements from AST: java_traverse_and_extract
def java_traverse_and_extract(
    root_node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    element_type: str,
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> None:
    """Iterative node traversal and extraction with batch field processing."""
    _java_traverse_and_extract_impl(
        root_node,
        extractors,
        results,
        element_type,
        processed_nodes,
        element_cache,
        log_warning_func=log_warning,
        log_debug_func=log_debug,
    )


# Extract elements from AST: extract_java_class
def extract_java_class(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    current_package: str,
    extract_modifiers: Callable,
    determine_visibility: Callable,
    find_annotations_for_line: Callable,
    is_nested_class: Callable,
    find_parent_class: Callable,
) -> Class | None:
    """Extract Java class/interface/enum information."""
    return _extract_java_class_impl(
        node,
        get_node_text,
        content_lines,
        current_package,
        extract_modifiers,
        determine_visibility,
        find_annotations_for_line,
        is_nested_class,
        find_parent_class,
        log_debug_func=log_debug,
        log_error_func=log_error,
    )


# Extract elements from AST: extract_java_method
def extract_java_method(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    parse_method_signature: Callable,
    determine_visibility: Callable,
    find_annotations_for_line: Callable,
    calculate_complexity: Callable,
    extract_javadoc: Callable,
) -> Function | None:
    """Extract Java method/constructor information."""
    return _extract_java_method_impl(
        node,
        get_node_text,
        content_lines,
        parse_method_signature,
        determine_visibility,
        find_annotations_for_line,
        calculate_complexity,
        extract_javadoc,
        log_debug_func=log_debug,
        log_error_func=log_error,
    )


# Extract elements from AST: extract_java_field
def extract_java_field(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    parse_field_declaration: Callable,
    determine_visibility: Callable,
    find_annotations_for_line: Callable,
    extract_javadoc: Callable,
) -> list[Variable]:
    """Extract Java field declarations."""
    return _extract_java_field_impl(
        node,
        get_node_text,
        content_lines,
        parse_field_declaration,
        determine_visibility,
        find_annotations_for_line,
        extract_javadoc,
        log_debug_func=log_debug,
        log_error_func=log_error,
    )
