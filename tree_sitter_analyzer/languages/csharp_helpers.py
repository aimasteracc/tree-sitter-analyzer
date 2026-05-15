"""C# using, visibility, and utility helpers — extracted from csharp_plugin.py."""

from collections.abc import Callable, Iterator
from typing import Any

from ..models import Import
from ..utils import log_error


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


def extract_type_name(
    type_node: Any,
    get_node_text: Callable[..., str],
) -> str:
    """Extract type name from a type node."""
    if not type_node:
        return "void"
    return get_node_text(type_node)


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
        if child.type in decision_keywords:
            complexity += 1
    return complexity


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
