#!/usr/bin/env python3
"""Shared execution helpers for CodeGraph visualization compatibility tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...call_graph import CachedCallGraph, CallGraph
from ...uml_export import UMLEdge, UMLExporter, render_flowchart_mermaid
from ..utils.auto_index_guard import ensure_indexed


def safe_node_id(name: str, file_path: str) -> str:
    """Build a Mermaid-safe node id for call-graph visualization nodes."""
    raw = f"{file_path}::{name}"
    return "".join(c if c.isalnum() or c == "_" else "_" for c in raw)


def short_label(name: str, file_path: str) -> str:
    """Build a compact label that preserves both file and function context."""
    parts = Path(file_path).parts
    short_file = parts[-1] if parts else file_path
    return f"{short_file}::{name}"


def render_call_flowchart(
    edges: list[tuple[str, str, str, str]],
    direction: str = "TD",
) -> str:
    """Render call-graph edge tuples as a Mermaid flowchart."""
    lines: list[str] = [f"flowchart {direction}"]

    node_ids = set()
    for src_id, _, dst_id, _ in edges:
        node_ids.add(src_id)
        node_ids.add(dst_id)

    if not node_ids:
        lines.append('    empty["No call edges found"]')
        return "\n".join(lines)

    id_to_label: dict[str, str] = {}
    for src_id, src_label, dst_id, dst_label in edges:
        id_to_label[src_id] = src_label
        id_to_label[dst_id] = dst_label

    seen_ids: set[str] = set()
    for nid, label in sorted(id_to_label.items()):
        if nid not in seen_ids:
            seen_ids.add(nid)
            escaped = label.replace('"', "'")
            lines.append(f'    {nid}["{escaped}"]')

    seen_edges: set[tuple[str, str]] = set()
    for src_id, _, dst_id, _ in edges:
        pair = (src_id, dst_id)
        if pair not in seen_edges:
            seen_edges.add(pair)
            lines.append(f"    {src_id} --> {dst_id}")

    return "\n".join(lines)


def query_flow_uml_facet(
    *,
    symbols: list[dict[str, Any]],
    current: list[dict[str, Any]],
    relationships: dict[str, dict[str, list[dict[str, Any]]]],
    direction: str,
    max_edges: int,
) -> dict[str, Any]:
    """Build the codegraph_query ``uml`` facet from chain state primitives."""
    mermaid_direction = (
        direction if direction in {"LR", "RL", "TB", "TD", "BT"} else "LR"
    )
    symbol_by_key = {_query_symbol_key(symbol): symbol for symbol in symbols}
    symbol_by_key.update({_query_symbol_key(symbol): symbol for symbol in current})
    edges: list[UMLEdge] = []
    nodes: set[str] = set()

    for source_key, entries in relationships.get("callees", {}).items():
        source_name = _query_display_name(symbol_by_key.get(source_key), source_key)
        nodes.add(source_name)
        for entry in entries:
            target_name = _query_display_name(entry, _query_symbol_key(entry))
            nodes.add(target_name)
            edges.append(UMLEdge(source_name, target_name, "calls"))

    for target_key, entries in relationships.get("callers", {}).items():
        target_name = _query_display_name(symbol_by_key.get(target_key), target_key)
        nodes.add(target_name)
        for entry in entries:
            source_name = _query_display_name(entry, _query_symbol_key(entry))
            nodes.add(source_name)
            edges.append(UMLEdge(source_name, target_name, "calls"))

    if not nodes:
        nodes.update(
            _query_display_name(symbol, _query_symbol_key(symbol))
            for symbol in current
            if _query_display_name(symbol, _query_symbol_key(symbol))
        )

    unique_edges = _dedupe_uml_edges(edges)
    truncated = len(unique_edges) > max_edges
    rendered_edges = unique_edges[:max_edges]
    rendered_nodes = sorted(nodes)
    return {
        "status": "included",
        "diagram_type": "query_flow",
        "mermaid_type": "flowchart",
        "node_count": len(rendered_nodes),
        "edge_count": len(rendered_edges),
        "truncated": truncated,
        "nodes": rendered_nodes,
        "edges": [edge.to_dict() for edge in rendered_edges],
        "mermaid": render_flowchart_mermaid(
            rendered_nodes,
            rendered_edges,
            mermaid_direction,
        ),
        "metadata": {
            "source": "codegraph_query",
            "direction": mermaid_direction,
        },
    }


def _query_symbol_key(symbol: dict[str, Any]) -> str:
    return f"{symbol.get('file', '')}:{symbol.get('line', 0)}:{symbol.get('name', '')}"


def _query_display_name(symbol: dict[str, Any] | None, fallback: str) -> str:
    if symbol:
        name = str(symbol.get("name") or "")
        if name:
            return name
    if ":" in fallback:
        return fallback.rsplit(":", 1)[-1]
    return fallback


def _dedupe_uml_edges(edges: list[UMLEdge]) -> list[UMLEdge]:
    unique: dict[tuple[str, str, str], UMLEdge] = {}
    for edge in edges:
        key = (edge.source, edge.target, edge.label)
        unique.setdefault(key, edge)
    return sorted(
        unique.values(), key=lambda edge: (edge.source, edge.target, edge.label)
    )


class CodeGraphVisualizationHub:
    """Shared cache/bootstrap layer for visualization-oriented MCP wrappers."""

    def __init__(self, project_root: str | None) -> None:
        self.project_root = project_root
        self._call_graph: CallGraph | None = None
        self._cache: Any | None = None

    def reset(self, project_root: str | None) -> None:
        self.project_root = project_root
        self._call_graph = None
        self._cache = None

    def cache(self) -> Any | None:
        if not self.project_root:
            return None
        if self._cache is None:
            self._cache = ensure_indexed(self.project_root)
        return self._cache

    def call_graph(self) -> CallGraph | None:
        if self._call_graph is not None:
            return self._call_graph
        if not self.project_root:
            return None
        cache = self.cache()
        if cache is not None:
            self._call_graph = CachedCallGraph(self.project_root, cache)
            return self._call_graph
        cg = CallGraph(self.project_root)
        cg.build()
        self._call_graph = cg
        return cg

    def uml_exporter(self) -> UMLExporter | None:
        if not self.project_root:
            return None
        return UMLExporter(self.project_root, self.cache())
