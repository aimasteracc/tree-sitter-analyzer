"""Class extraction helpers for the JavaScript extractor."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from ...models import Class
from ...utils import log_debug
from ..shared.traversal import node_range

if TYPE_CHECKING:
    import tree_sitter


TextExtractor: TypeAlias = Callable[["tree_sitter.Node"], str]
JsdocExtractor: TypeAlias = Callable[[int], str | None]
ComponentPredicate: TypeAlias = Callable[["tree_sitter.Node", str], bool]
ExportPredicate: TypeAlias = Callable[[str], bool]


@dataclass
class _ClassParts:
    name: str | None = None
    superclass: str | None = None


def extract_class(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_jsdoc: JsdocExtractor,
    is_react_component: ComponentPredicate,
    is_exported_class: ExportPredicate,
    framework_type: str,
) -> Class | None:
    """Extract class information with detailed metadata."""
    try:
        start_line, end_line = node_range(node)
        parts = _parse_class_parts(node, get_node_text)
        if not parts.name:
            return None

        return Class(
            name=parts.name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="javascript",
            class_type="class",
            superclass=parts.superclass,
            docstring=extract_jsdoc(start_line),
            is_react_component=is_react_component(node, parts.name),
            framework_type=framework_type,
            is_exported=is_exported_class(parts.name),
        )
    except Exception as e:
        log_debug(f"Failed to extract class info: {e}")
        return None


def _parse_class_parts(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> _ClassParts:
    parts = _ClassParts()
    for child in node.children:
        if child.type == "identifier":
            parts.name = child.text.decode("utf8") if child.text else None
        elif child.type == "class_heritage":
            parts.superclass = _class_superclass(get_node_text(child))
    return parts


def _class_superclass(heritage_text: str) -> str | None:
    match = re.search(r"extends\s+([\w.]+)", heritage_text)
    if match:
        return match.group(1)
    return None
