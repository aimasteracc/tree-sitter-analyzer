"""Structural metrics attached to cached symbols."""

from __future__ import annotations

from functools import lru_cache
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


@lru_cache(maxsize=1)
def _shared_plugin_manager() -> Any:
    """返回进程级共享的 ``PluginManager``（#1562）。

    插件发现取决于安装环境而非被索引的文件。此前每个文件新建一个
    ``PluginManager``，每次都重扫 ``importlib.metadata.entry_points()``：
    在 920 个文件的顺序索引中这占了 584 s 中的 293 s（146,280 次元数据读取）。
    ``complexity_heatmap`` 曾因同一缺陷修复过一次。
    """
    from ..plugins.manager import PluginManager

    return PluginManager()


def _annotate_canonical_complexity(
    symbols: list[dict[str, Any]], tree: Any, source_code: str, language: str
) -> None:
    """Add the plugin extractor's canonical complexity to cached symbols."""
    try:
        plugin = _shared_plugin_manager().get_plugin(language)
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
