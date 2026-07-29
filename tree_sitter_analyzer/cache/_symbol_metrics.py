"""Structural metrics attached to cached symbols."""

from __future__ import annotations

from typing import Any

from ._symbol_rules import _COMPLEXITY_NODE_TYPES


def _count_nodes(node: Any) -> int:
    """Count AST nodes iteratively to avoid recursion limits."""
    count = 0
    stack = [node]
    while stack:
        current = stack.pop()
        count += 1
        stack.extend(current.children)
    return count


def _count_decision_points(node: Any, language: str) -> dict[str, int]:
    lang = "typescript" if language.lower() in ("tsx", "jsx") else language.lower()
    types = _COMPLEXITY_NODE_TYPES.get(lang)
    if not types:
        return {}
    counts: dict[str, int] = {}
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in types:
            counts[current.type] = counts.get(current.type, 0) + 1
        stack.extend(current.children)
    return counts


def _annotate_canonical_complexity(
    symbols: list[dict[str, Any]], tree: Any, source_code: str, language: str
) -> None:
    """Add the plugin extractor's canonical complexity to cached symbols."""
    try:
        from ..plugins.manager import PluginManager

        plugin = PluginManager().get_plugin(language)
        if plugin is None:
            return
        elements = plugin.create_extractor().extract_functions(tree, source_code)
    except Exception:
        return

    complexity_by_line = {
        start: max(getattr(element, "complexity_score", 1) or 1, 1)
        for element in elements
        if (start := getattr(element, "start_line", None)) is not None
    }
    for symbol in symbols:
        line = symbol.get("line")
        if symbol.get("kind") in ("function", "method") and line in complexity_by_line:
            symbol["complexity"] = complexity_by_line[line]
