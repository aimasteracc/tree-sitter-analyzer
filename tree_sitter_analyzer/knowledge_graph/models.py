"""Typed payloads for whole-project code/document knowledge graphs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KnowledgeNode:
    """One code, file, package, or document node."""

    id: str
    label: str
    kind: str
    file_path: str = ""
    language: str = ""
    line: int | None = None
    package: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "file_path": self.file_path,
            "language": self.language,
            "line": self.line,
            "package": self.package,
            "metadata": dict(self.metadata),
        }
        return {
            key: value for key, value in payload.items() if value not in ("", None, {})
        }


@dataclass(frozen=True)
class KnowledgeEdge:
    """One directed relationship between knowledge graph nodes."""

    id: str
    source: str
    target: str
    kind: str
    weight: float = 1.0
    provenance: str = "tree-sitter"
    line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "weight": self.weight,
            "provenance": self.provenance,
            "line": self.line,
            "metadata": dict(self.metadata),
        }
        return {
            key: value for key, value in payload.items() if value not in ("", None, {})
        }


@dataclass(frozen=True)
class KnowledgeGraphSnapshot:
    """A bounded exportable graph snapshot."""

    nodes: list[KnowledgeNode]
    edges: list[KnowledgeEdge]
    stats: dict[str, Any]
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "tsa.knowledge_graph.v1",
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "stats": dict(self.stats),
            "truncated": self.truncated,
        }

    def to_graphology(self) -> dict[str, Any]:
        """Return Graphology-compatible JSON for Sigma.js/react-sigma."""

        graph_nodes = [
            {
                "key": node.id,
                "attributes": {
                    "label": node.label,
                    "kind": node.kind,
                    "file_path": node.file_path,
                    "language": node.language,
                    "line": node.line,
                    "package": node.package,
                    **node.metadata,
                },
            }
            for node in self.nodes
        ]
        graph_edges = [
            {
                "key": edge.id,
                "source": edge.source,
                "target": edge.target,
                "attributes": {
                    "kind": edge.kind,
                    "weight": edge.weight,
                    "provenance": edge.provenance,
                    "line": edge.line,
                    **edge.metadata,
                },
            }
            for edge in self.edges
        ]
        return {
            "options": {"type": "directed", "multi": True, "allowSelfLoops": True},
            "nodes": graph_nodes,
            "edges": graph_edges,
            "metadata": {
                "stats": dict(self.stats),
                "truncated": self.truncated,
                "schema": "tsa.knowledge_graph.v1",
            },
        }
