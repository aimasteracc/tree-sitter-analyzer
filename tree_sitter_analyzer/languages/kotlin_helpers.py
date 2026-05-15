"""Kotlin import, visibility, and utility helpers — extracted from kotlin_plugin.py."""

from collections.abc import Callable
from typing import Any

from ..models import Import
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
