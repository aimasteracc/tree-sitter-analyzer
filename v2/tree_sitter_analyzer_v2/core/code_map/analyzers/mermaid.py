"""Mermaid graph visualization analyzer."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer_v2.core.code_map.types import SymbolInfo


def to_mermaid(
    module_dependencies: list[tuple[str, str]],
    symbols: list[SymbolInfo],
    kind: str = "dependencies",
) -> str:
    """Generate a Mermaid graph for module dependencies or class inheritance."""
    if kind == "inheritance":
        return _mermaid_inheritance(symbols)
    return _mermaid_dependencies(module_dependencies)


def _mermaid_dependencies(module_dependencies: list[tuple[str, str]]) -> str:
    lines: list[str] = ["graph LR"]
    seen_edges: set[tuple[str, str]] = set()

    for src, dst in module_dependencies:
        src_id = _mermaid_id(src)
        dst_id = _mermaid_id(dst)
        if src_id != dst_id and (src_id, dst_id) not in seen_edges:
            lines.append(f"    {src_id} --> {dst_id}")
            seen_edges.add((src_id, dst_id))

    if not seen_edges:
        lines.append("    NoEdges[No module dependencies found]")

    return "\n".join(lines)


def _mermaid_inheritance(symbols: list[SymbolInfo]) -> str:
    lines: list[str] = ["graph BT"]
    edges: set[tuple[str, str]] = set()

    for sym in symbols:
        if sym.kind == "class" and sym.bases:
            child_id = _mermaid_id(sym.name)
            for base in sym.bases:
                parent_id = _mermaid_id(base)
                if child_id != parent_id:
                    edges.add((child_id, parent_id))

    for child_id, parent_id in sorted(edges):
        lines.append(f"    {child_id} -->|extends| {parent_id}")

    if not edges:
        lines.append("    NoInheritance[No inheritance found]")

    return "\n".join(lines)


def _mermaid_id(path: str) -> str:
    """Sanitize a path/name into a valid Mermaid node ID."""
    result = path.replace("/", "_").replace("\\", "_").replace(".", "_")
    result = result.replace("-", "_").replace(" ", "_")
    if result and not result[0].isalpha():
        result = "N_" + result
    return result
