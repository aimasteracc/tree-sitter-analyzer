"""Inheritance chain tracing analyzer."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer_v2.core.code_map.types import InheritanceChain, SymbolInfo


def trace_inheritance(
    symbols: list[SymbolInfo],
    class_name: str,
) -> InheritanceChain:
    """Trace the full inheritance chain for a class."""
    from tree_sitter_analyzer_v2.core.code_map.types import InheritanceChain

    target = next(
        (s for s in symbols if s.name == class_name and s.kind == "class"),
        None,
    )
    if not target:
        return InheritanceChain(target=None)

    class_by_name: dict[str, SymbolInfo] = {}
    children_map: dict[str, list[SymbolInfo]] = {}

    for s in symbols:
        if s.kind == "class":
            if s.name not in class_by_name:
                class_by_name[s.name] = s
            for base_name in s.bases:
                children_map.setdefault(base_name, []).append(s)

    # Ancestors (BFS upward with deque for O(1) popleft)
    ancestors: list[SymbolInfo] = []
    visited: set[str] = {class_name}
    queue: deque[str] = deque(target.bases)
    while queue:
        parent_name = queue.popleft()
        if parent_name in visited:
            continue
        visited.add(parent_name)
        parent_sym = class_by_name.get(parent_name)
        if parent_sym:
            ancestors.append(parent_sym)
            queue.extend(b for b in parent_sym.bases if b not in visited)

    # Descendants (BFS downward with deque for O(1) popleft)
    descendants: list[SymbolInfo] = []
    visited_down: set[str] = {class_name}
    child_queue: deque[SymbolInfo] = deque(children_map.get(class_name, []))
    while child_queue:
        child = child_queue.popleft()
        if child.name in visited_down:
            continue
        visited_down.add(child.name)
        descendants.append(child)
        child_queue.extend(
            c for c in children_map.get(child.name, []) if c.name not in visited_down
        )

    return InheritanceChain(target=target, ancestors=ancestors, descendants=descendants)


def find_implementations(symbols: list[SymbolInfo], interface_name: str) -> list[SymbolInfo]:
    """Find all classes that extend/implement a class or interface."""
    chain = trace_inheritance(symbols, interface_name)
    return chain.descendants
