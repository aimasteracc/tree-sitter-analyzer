"""Go function and method extraction helpers."""

from collections.abc import Callable
from typing import Any

from ..models import Function
from ..utils import log_error
from ._go_common_helpers import (
    extract_docstring,
    extract_method_receiver,
    extract_parameters,
    extract_return_type,
    go_visibility,
)


def extract_go_function(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Function | None:
    """Extract Go function declaration."""
    try:
        name = _go_function_name(node, get_node_text)
        if not name:
            return None

        return _build_go_function(name, node, get_node_text, content_lines)
    except Exception as e:
        log_error(f"Error extracting Go function: {e}")
        return None


def extract_go_method(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Function | None:
    """Extract Go method declaration (function with receiver)."""
    try:
        name = _go_function_name(node, get_node_text)
        if not name:
            return None

        func = _build_go_function(name, node, get_node_text, content_lines)
        receiver, receiver_type = extract_method_receiver(node, get_node_text)
        func.receiver = receiver
        func.receiver_type = receiver_type
        func.is_method = True
        return func
    except Exception as e:
        log_error(f"Error extracting Go method: {e}")
        return None


def _go_function_name(node: Any, get_node_text: Callable[..., str]) -> str | None:
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    return get_node_text(name_node) or None


def _build_go_function(
    name: str,
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Function:
    visibility = go_visibility(name)
    return Function(
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=get_node_text(node),
        language="go",
        parameters=extract_parameters(node, get_node_text),
        return_type=extract_return_type(node, get_node_text),
        visibility=visibility,
        docstring=extract_docstring(node, content_lines),
        is_public=visibility == "public",
    )
