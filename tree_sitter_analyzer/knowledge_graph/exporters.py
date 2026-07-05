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
    "symbol": {
        "package",
        "file",
        "markdown",
        "class",
        "constant",
        "enum",
        "function",
        "interface",
        "method",
        "symbol",
    },
    "docs": {"file", "markdown"},
}
_CLASS_UML_RELATION_KINDS = {"extends", "implements", "references", "imports"}
_UML_DEFAULT_MAX_NODES = 200
_UML_DEFAULT_MAX_EDGES = 500


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


def to_mermaid_uml(
    snapshot: KnowledgeGraphSnapshot,
    *,
    diagram: str = "component",
    focus: str | None = None,
    max_nodes: int = _UML_DEFAULT_MAX_NODES,
    max_edges: int = _UML_DEFAULT_MAX_EDGES,
) -> dict[str, Any]:
    """Return a Mermaid UML-style diagram from a knowledge graph snapshot."""
    if diagram not in {"class", "package", "component", "sequence"}:
        raise ValueError("diagram must be one of: class, component, package, sequence")
    if diagram == "class":
        mermaid, node_count, edge_count, truncated = _class_diagram(
            snapshot, focus, max_nodes, max_edges
        )
    elif diagram == "sequence":
        mermaid, node_count, edge_count, truncated = _sequence_diagram(
            snapshot, focus, max_nodes, max_edges
        )
    else:
        lod = "package" if diagram == "package" else "file"
        nodes, edges, truncated = _select(snapshot, lod, focus, max_nodes, max_edges)
        mermaid = _flowchart_diagram(nodes, edges, diagram)
        node_count = len(nodes)
        edge_count = len(edges)
        return {
            "schema": "tsa.knowledge_graph.uml.v1",
            "syntax": "mermaid",
            "diagram": diagram,
            "mermaid": mermaid,
            "stats": {
                **snapshot.stats,
                "export_node_count": node_count,
                "export_edge_count": edge_count,
                "export_truncated": truncated,
            },
        }
    return {
        "schema": "tsa.knowledge_graph.uml.v1",
        "syntax": "mermaid",
        "diagram": diagram,
        "mermaid": mermaid,
        "stats": {
            **snapshot.stats,
            "export_node_count": node_count,
            "export_edge_count": edge_count,
            "export_truncated": truncated,
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


def _class_diagram(
    snapshot: KnowledgeGraphSnapshot,
    focus: str | None,
    max_nodes: int,
    max_edges: int,
) -> tuple[str, int, int, bool]:
    node_by_id = {node.id: node for node in snapshot.nodes if _is_class_uml_node(node)}
    if focus:
        focused = {
            node_id
            for node_id, node in node_by_id.items()
            if focus in node_id or focus in node.label or focus in node.file_path
        }
        expanded = set(focused)
        for edge in snapshot.edges:
            if edge.kind not in _CLASS_UML_RELATION_KINDS:
                continue
            if edge.source in focused or edge.target in focused:
                expanded.add(edge.source)
                expanded.add(edge.target)
        node_by_id = {
            node_id: node_by_id[node_id] for node_id in expanded & set(node_by_id)
        }
    all_nodes = sorted(node_by_id.values(), key=lambda n: n.id)
    nodes = all_nodes[:max_nodes]
    kept = {node.id for node in nodes}
    all_relation_edges = [
        edge
        for edge in snapshot.edges
        if edge.source in kept
        and edge.target in kept
        and edge.kind in _CLASS_UML_RELATION_KINDS
    ]
    relation_edges = all_relation_edges[:max_edges]
    class_ids = {node.id: _mermaid_class_id(node) for node in nodes}
    lines = ["classDiagram"]
    for node in nodes:
        class_id = class_ids[node.id]
        lines.append(f"  class {class_id}")
        if node.kind in {"interface", "enum"}:
            lines.append(f"  <<{node.kind}>> {class_id}")
    for edge in relation_edges:
        source = class_ids[edge.source]
        target = class_ids[edge.target]
        if edge.kind == "extends":
            lines.append(f"  {target} <|-- {source}")
        elif edge.kind == "implements":
            lines.append(f"  {target} <|.. {source}")
        else:
            lines.append(f"  {source} ..> {target} : {edge.kind}")
    truncated = len(all_nodes) > len(nodes) or len(all_relation_edges) > len(
        relation_edges
    )
    return "\n".join(lines), len(nodes), len(relation_edges), truncated


def _is_class_uml_node(node: KnowledgeNode) -> bool:
    return node.kind in {"class", "interface", "enum"} or node.id.startswith("class:")


def _mermaid_class_id(node: KnowledgeNode) -> str:
    label = node.label or node.id.removeprefix("class:") or node.id
    digest = hashlib.sha256(node.id.encode("utf-8")).hexdigest()[:8]
    stem = "".join(ch if ch.isalnum() else "_" for ch in label)[-48:].strip("_")
    return "n_" + (stem or "class") + "_" + digest


def _sequence_diagram(
    snapshot: KnowledgeGraphSnapshot,
    focus: str | None,
    max_nodes: int,
    max_edges: int,
) -> tuple[str, int, int, bool]:
    node_by_id = {
        node.id: node
        for node in snapshot.nodes
        if node.kind in {"class", "function", "interface", "method", "symbol", "file"}
    }
    call_edges = [edge for edge in snapshot.edges if edge.kind == "calls"]
    if focus:
        focused = {
            node_id
            for node_id, node in node_by_id.items()
            if focus in node_id or focus in node.label or focus in node.file_path
        }
        call_edges = [
            edge
            for edge in call_edges
            if edge.source in focused
            or edge.target in focused
            or focus in edge.source
            or focus in edge.target
        ]
    participants: dict[str, KnowledgeNode] = {}
    ordered_edges: list[KnowledgeEdge] = []
    for edge in sorted(call_edges, key=lambda e: (e.source, e.line or 0, e.target)):
        source = node_by_id.get(edge.source)
        target = node_by_id.get(edge.target)
        if source is None or target is None:
            continue
        missing = [node for node in (source, target) if node.id not in participants]
        if len(participants) + len(missing) > max_nodes:
            break
        for node in missing:
            participants[node.id] = node
        ordered_edges.append(edge)
        if len(ordered_edges) >= max_edges:
            break
    lines = ["sequenceDiagram"]
    for node in sorted(participants.values(), key=lambda n: n.id):
        lines.append(f"  participant {_mermaid_id(node.id)} as {_sequence_label(node)}")
    for edge in ordered_edges:
        source_id = _mermaid_id(edge.source)
        target_id = _mermaid_id(edge.target)
        message = _mermaid_label(edge.metadata.get("callee_name") or "calls")
        lines.append(f"  {source_id}->>+{target_id}: {message}")
        lines.append(f"  {target_id}-->>-{source_id}: return")
    truncated = len(ordered_edges) < len(call_edges)
    return "\n".join(lines), len(participants), len(ordered_edges), truncated


def _flowchart_diagram(
    nodes: list[KnowledgeNode],
    edges: list[KnowledgeEdge],
    diagram: str,
) -> str:
    lines = ["flowchart LR"]
    for node in nodes:
        node_id = _mermaid_id(node.id)
        label = _mermaid_label(node.label or node.id)
        lines.append(f'  {node_id}["{label}"]')
    for edge in edges:
        lines.append(
            f"  {_mermaid_id(edge.source)} -->|{_mermaid_label(edge.kind)}| "
            f"{_mermaid_id(edge.target)}"
        )
    if diagram == "component":
        lines.append("  %% component view: files, docs, symbols, and relationships")
    return "\n".join(lines)


def _mermaid_id(raw: str) -> str:
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    stem = "".join(ch if ch.isalnum() else "_" for ch in raw)[-48:].strip("_")
    return "n_" + (stem or "node") + "_" + digest


def _mermaid_label(raw: Any) -> str:
    return str(raw).replace("\\", "\\\\").replace('"', "'").replace("\n", " ")[:120]


def _sequence_label(node: KnowledgeNode) -> str:
    label = node.label or node.id
    if node.file_path and node.file_path not in label:
        label = f"{label}\\n{node.file_path}"
    return '"' + _mermaid_label(label) + '"'


def _package_by_file(nodes: list[KnowledgeNode]) -> dict[str, str]:
    result: dict[str, str] = {}
    packages = [node for node in nodes if node.kind == "package"]
    files = [node for node in nodes if node.kind in {"file", "markdown"}]
    for file_node in files:
        directory = "/".join(file_node.file_path.split("/")[:-1]) or "<root>"
        package_id = "package:" + directory.replace("/", ".")
        if any(package.id == package_id for package in packages):
            result[file_node.file_path] = package_id
        else:
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
