"""Data model for the project knowledge graph projection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KnowledgeNode:
    """A code, file, package, or markdown node in the knowledge graph."""

    id: str
    kind: str
    label: str
    file_path: str = ""
    language: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "file_path": self.file_path,
            "language": self.language,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class KnowledgeEdge:
    """A directed relationship between two knowledge graph nodes."""

    id: str
    source: str
    target: str
    kind: str
    line: int | None = None
    provenance: str = "tree-sitter"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "line": self.line,
            "provenance": self.provenance,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class KnowledgeGraphSnapshot:
    """A materialized graph projection ready for JSON/Ladybug/Sigma export."""

    nodes: list[KnowledgeNode]
    edges: list[KnowledgeEdge]
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "tsa.knowledge_graph.v1",
            "stats": dict(self.stats),
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }
