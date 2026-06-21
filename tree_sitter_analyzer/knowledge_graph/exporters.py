"""Export knowledge graph snapshots for browser and agent consumers."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from typing import Any

from .models import KnowledgeEdge, KnowledgeGraphSnapshot, KnowledgeNode

_LOD_KINDS: dict[str, set[str]] = {
    "package": {"package"},
    "file": {"package", "file", "markdown"},
    "symbol": {"package", "file", "markdown", "class", "function", "method"},
    "docs": {"file", "markdown"},
}


def to_graphology(
    snapshot: KnowledgeGraphSnapshot,
    *,
    lod: str = "file",
    focus: str | None = None,
    max_nodes: int = 10_000,
    max_edges: int = 50_000,
) -> dict[str, Any]:
    """Return Graphology JSON suitable for Sigma.js/Obsidian-like viewers."""
    nodes, edges, truncated = _select(snapshot, lod, focus, max_nodes, max_edges)
    positions = _positions(nodes)
    return {
        "options": {"type": "directed", "multi": True, "allowSelfLoops": True},
        "attributes": {
            "name": "TSA knowledge graph",
            "schema": "tsa.graphology.v1",
            "lod": lod,
            "focus": focus or "",
            "truncated": truncated,
        },
        "nodes": [
            {
                "key": node.id,
                "attributes": {
                    "label": node.label,
                    "kind": node.kind,
                    "file_path": node.file_path,
                    "language": node.language,
                    "x": positions[node.id][0],
                    "y": positions[node.id][1],
                    "size": _node_size(node),
                    "color": _node_color(node.kind),
                    **node.metadata,
                },
            }
            for node in nodes
        ],
        "edges": [
            {
                "key": edge.id,
                "source": edge.source,
                "target": edge.target,
                "attributes": {
                    "kind": edge.kind,
                    "line": edge.line,
                    "provenance": edge.provenance,
                    **edge.metadata,
                },
            }
            for edge in edges
        ],
        "stats": {
            **snapshot.stats,
            "export_node_count": len(nodes),
            "export_edge_count": len(edges),
            "export_truncated": truncated,
        },
    }


def summarize(snapshot: KnowledgeGraphSnapshot) -> dict[str, Any]:
    """Compact summary for TOON/MCP agents."""
    return {
        "schema": "tsa.knowledge_graph.v1",
        "stats": snapshot.stats,
        "topology": {
            "node_kinds": snapshot.stats.get("node_kinds", {}),
            "edge_kinds": snapshot.stats.get("edge_kinds", {}),
        },
    }


def aggregate_package_graph(snapshot: KnowledgeGraphSnapshot) -> KnowledgeGraphSnapshot:
    """Aggregate file/symbol/doc edges to package-level dependencies."""
    package_by_file = _package_by_file(snapshot.nodes)
    package_nodes = {
        package: KnowledgeNode(
            id=package,
            kind="package",
            label=package.removeprefix("package:"),
        )
        for package in package_by_file.values()
    }
    edge_weights: dict[tuple[str, str, str], int] = defaultdict(int)
    for edge in snapshot.edges:
        src_file = _file_from_node_id(edge.source)
        dst_file = _file_from_node_id(edge.target)
        src_pkg = package_by_file.get(src_file)
        dst_pkg = package_by_file.get(dst_file)
        if not src_pkg or not dst_pkg or src_pkg == dst_pkg:
            continue
        edge_weights[(src_pkg, dst_pkg, edge.kind)] += 1
    package_edges = [
        KnowledgeEdge(
            id=_stable_edge_id(source, target, kind),
            source=source,
            target=target,
            kind=kind,
            provenance="package-aggregate",
            metadata={"weight": weight},
        )
        for (source, target, kind), weight in edge_weights.items()
    ]
    stats = {
        **snapshot.stats,
        "node_count": len(package_nodes),
        "edge_count": len(package_edges),
        "lod": "package",
    }
    return KnowledgeGraphSnapshot(
        nodes=sorted(package_nodes.values(), key=lambda n: n.id),
        edges=sorted(package_edges, key=lambda e: e.id),
        stats=stats,
    )


def _select(
    snapshot: KnowledgeGraphSnapshot,
    lod: str,
    focus: str | None,
    max_nodes: int,
    max_edges: int,
) -> tuple[list[KnowledgeNode], list[KnowledgeEdge], bool]:
    if lod == "package":
        snapshot = aggregate_package_graph(snapshot)
    allowed = _LOD_KINDS.get(lod, _LOD_KINDS["file"])
    node_by_id = {node.id: node for node in snapshot.nodes if node.kind in allowed}
    if focus:
        focused = {
            node_id
            for node_id, node in node_by_id.items()
            if focus in node_id or focus in node.label or focus in node.file_path
        }
        neighbours = set(focused)
        for edge in snapshot.edges:
            if edge.source in focused or edge.target in focused:
                neighbours.add(edge.source)
                neighbours.add(edge.target)
        node_by_id = {
            node_id: node_by_id[node_id] for node_id in neighbours & set(node_by_id)
        }
    nodes = sorted(node_by_id.values(), key=lambda n: n.id)[:max_nodes]
    kept = {node.id for node in nodes}
    edges = [
        edge for edge in snapshot.edges if edge.source in kept and edge.target in kept
    ][:max_edges]
    truncated = len(node_by_id) > len(nodes) or len(edges) >= max_edges
    return nodes, edges, truncated


def _positions(nodes: list[KnowledgeNode]) -> dict[str, tuple[float, float]]:
    total = len(nodes)
    if total == 0:
        return {}
    radius = max(80.0, total * 2.0)
    positions: dict[str, tuple[float, float]] = {}
    for i, node in enumerate(nodes):
        angle = (2.0 * math.pi * i) / total
        jitter = int(hashlib.sha256(node.id.encode("utf-8")).hexdigest()[:4], 16) % 23
        positions[node.id] = (
            round(math.cos(angle) * (radius + jitter), 3),
            round(math.sin(angle) * (radius + jitter), 3),
        )
    return positions


def _node_size(node: KnowledgeNode) -> int:
    return {
        "package": 9,
        "markdown": 7,
        "file": 6,
        "class": 5,
        "method": 4,
        "function": 4,
    }.get(node.kind, 3)


def _node_color(kind: str) -> str:
    return {
        "package": "#5B8DEF",
        "markdown": "#D97706",
        "file": "#10B981",
        "class": "#8B5CF6",
        "method": "#EF4444",
        "function": "#EF4444",
    }.get(kind, "#64748B")


def _package_by_file(nodes: list[KnowledgeNode]) -> dict[str, str]:
    result: dict[str, str] = {}
    files = [node for node in nodes if node.kind in {"file", "markdown"}]
    for file_node in files:
        directory = "/".join(file_node.file_path.split("/")[:-1]) or "<root>"
        package_id = "package:" + directory.replace("/", ".")
        result[file_node.file_path] = package_id
    return result


def _file_from_node_id(node_id: str) -> str:
    if node_id.startswith("file:"):
        return node_id.removeprefix("file:")
    if node_id.startswith("doc:"):
        return node_id.removeprefix("doc:")
    return node_id.split(":", 1)[0]


def _stable_edge_id(source: str, target: str, kind: str) -> str:
    digest = hashlib.sha256(f"{source}\0{target}\0{kind}".encode()).hexdigest()
    return "pkg-edge:" + digest[:16]
