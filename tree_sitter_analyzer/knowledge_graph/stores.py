"""Persistence adapters for the project knowledge graph."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, cast

from .models import KnowledgeGraphSnapshot


class JsonKnowledgeGraphStore:
    """Small JSON sidecar used by CLI/MCP and browser exports."""

    def __init__(self, project_root: str, path: str | None = None) -> None:
        self.project_root = os.path.abspath(project_root)
        self.path = path or os.path.join(
            self.project_root,
            ".ast-cache",
            "knowledge-graph.json",
        )

    def write(self, snapshot: KnowledgeGraphSnapshot) -> dict[str, Any]:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        payload = snapshot.to_dict()
        Path(self.path).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return {"path": self.path, "bytes": os.path.getsize(self.path)}

    def read(self) -> dict[str, Any]:
        payload = json.loads(Path(self.path).read_text(encoding="utf-8"))
        return cast(dict[str, Any], payload)

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def status(self) -> dict[str, Any]:
        if not self.exists():
            return {"exists": False, "path": self.path}
        stat = os.stat(self.path)
        return {
            "exists": True,
            "path": self.path,
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }


class LadybugUnavailableError(RuntimeError):
    """Raised when the optional Ladybug package is not installed."""


class LadybugKnowledgeGraphStore:
    """Optional LadybugDB mirror for fast Cypher graph traversals."""

    def __init__(self, project_root: str, path: str | None = None) -> None:
        self.project_root = os.path.abspath(project_root)
        self.path = path or os.path.join(
            self.project_root,
            ".ast-cache",
            "knowledge-graph.lbug",
        )

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("ladybug") is not None

    def write(self, snapshot: KnowledgeGraphSnapshot) -> dict[str, Any]:
        lb = self._import_ladybug()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        db = lb.Database(self.path)
        conn = lb.Connection(db)
        self._create_schema(conn)
        self._clear(conn)
        for node in snapshot.nodes:
            conn.execute(
                "CREATE (n:KGNode {id: $id, kind: $kind, label: $label, "
                "file_path: $file_path, language: $language, metadata_json: $metadata_json})",
                {
                    "id": node.id,
                    "kind": node.kind,
                    "label": node.label,
                    "file_path": node.file_path,
                    "language": node.language,
                    "metadata_json": json.dumps(node.metadata, ensure_ascii=False),
                },
            )
        for edge in snapshot.edges:
            conn.execute(
                "MATCH (s:KGNode), (t:KGNode) "
                "WHERE s.id = $source AND t.id = $target "
                "CREATE (s)-[:KGEdge {id: $id, kind: $kind, line: $line, "
                "provenance: $provenance, metadata_json: $metadata_json}]->(t)",
                {
                    "id": edge.id,
                    "source": edge.source,
                    "target": edge.target,
                    "kind": edge.kind,
                    "line": edge.line if edge.line is not None else -1,
                    "provenance": edge.provenance,
                    "metadata_json": json.dumps(edge.metadata, ensure_ascii=False),
                },
            )
        return {
            "path": self.path,
            "node_count": len(snapshot.nodes),
            "edge_count": len(snapshot.edges),
        }

    def status(self) -> dict[str, Any]:
        if not self.available():
            return {
                "available": False,
                "path": self.path,
                "install": "pip install 'tree-sitter-analyzer[graph]'",
            }
        return {
            "available": True,
            "path": self.path,
            "exists": os.path.exists(self.path),
        }

    @staticmethod
    def _import_ladybug() -> Any:
        try:
            return importlib.import_module("ladybug")
        except ModuleNotFoundError as exc:
            raise LadybugUnavailableError(
                "LadybugDB Python package is not installed. Install with "
                "`pip install 'tree-sitter-analyzer[graph]'`."
            ) from exc

    @staticmethod
    def _create_schema(conn: Any) -> None:
        conn.execute(
            "CREATE NODE TABLE IF NOT EXISTS KGNode("
            "id STRING PRIMARY KEY, kind STRING, label STRING, "
            "file_path STRING, language STRING, metadata_json STRING)"
        )
        conn.execute(
            "CREATE REL TABLE IF NOT EXISTS KGEdge("
            "FROM KGNode TO KGNode, id STRING, kind STRING, line INT64, "
            "provenance STRING, metadata_json STRING)"
        )

    @staticmethod
    def _clear(conn: Any) -> None:
        conn.execute("MATCH ()-[e:KGEdge]->() DELETE e")
        conn.execute("MATCH (n:KGNode) DELETE n")
