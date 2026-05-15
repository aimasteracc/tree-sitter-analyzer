"""PHP use, visibility, and utility helpers — extracted from php_plugin.py."""

from collections.abc import Callable
from typing import Any

from ..models import Import
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
