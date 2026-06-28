"""Parameter extraction helpers for the TypeScript extractor."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    import tree_sitter


TextExtractor: TypeAlias = Callable[["tree_sitter.Node"], str]


def extract_parameters_with_types(
    params_node: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> list[str]:
    """Extract function parameters with TypeScript type annotations."""
    parameters = []

    for child in params_node.children:
        parameter = _parameter_text(child, get_node_text)
        if parameter is not None:
            parameters.append(parameter)

    return parameters


def _parameter_text(
    child: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> str | None:
    if child.type == "identifier":
        return get_node_text(child)
    if child.type in ["required_parameter", "optional_parameter", "rest_parameter"]:
        return get_node_text(child)
    if child.type in ["object_pattern", "array_pattern"]:
        return get_node_text(child)
    return None
