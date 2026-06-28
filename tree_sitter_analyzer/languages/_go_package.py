"""Go package extraction helpers."""

from collections.abc import Callable
from typing import Any

from ..models import Package
from ..utils import log_error


def extract_go_package(
    node: Any,
    get_node_text: Callable[..., str],
) -> Package | None:
    """Extract Go package declaration."""
    try:
        name = _go_package_name(node, get_node_text)
        if not name:
            return None

        return Package(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=get_node_text(node),
            language="go",
        )
    except Exception as e:
        log_error(f"Error extracting Go package: {e}")
        return None


def _go_package_name(node: Any, get_node_text: Callable[..., str]) -> str | None:
    for child in node.children:
        if child.type == "package_identifier":
            return get_node_text(child)
    return None
