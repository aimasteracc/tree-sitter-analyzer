"""C macro extraction helpers."""

from collections.abc import Callable
from typing import Any

from ..models import Function
from ..utils import log_debug


def extract_macro_function(
    node: Any,
    get_node_text: Callable[..., str],
) -> Function | None:
    """Extract macro function definition."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        name, params = _macro_function_parts(node, get_node_text)

        if not name:
            return None

        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="c",
            parameters=params,
            return_type="macro",
            modifiers=["macro"],
            visibility="public",
            complexity_score=1,
        )
    except Exception as e:
        log_debug(f"Failed to extract macro function: {e}")
        return None


def _macro_function_parts(
    node: Any, get_node_text: Callable[..., str]
) -> tuple[str | None, list[str]]:
    name: str | None = None
    params: list[str] = []

    for child in node.children:
        if child.type == "identifier":
            name = get_node_text(child)
        elif child.type == "preproc_params":
            _append_macro_params(params, child, get_node_text)

    return name, params


def _append_macro_params(
    params: list[str], node: Any, get_node_text: Callable[..., str]
) -> None:
    for child in node.children:
        if child.type == "identifier":
            params.append(get_node_text(child))
        elif child.type == "variadic_parameter":
            params.append("...")
