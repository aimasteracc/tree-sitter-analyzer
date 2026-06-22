"""Persistence adapters for the project knowledge graph."""

from __future__ import annotations

import csv
import importlib
import importlib.util
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, cast

from .models import KnowledgeEdge, KnowledgeGraphSnapshot, KnowledgeNode


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
        start = time.perf_counter()
        try:
            result = self._write_with_copy(lb, snapshot)
            result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
            return result
        except Exception as exc:
            result = self._write_row_by_row(lb, snapshot)
            result["method"] = "row_by_row_fallback"
            result["fallback_error"] = str(exc)
            result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
            return result

    def _write_with_copy(
        self, lb: Any, snapshot: KnowledgeGraphSnapshot
    ) -> dict[str, Any]:
        parent = Path(self.path).parent
        with tempfile.TemporaryDirectory(prefix="knowledge-graph-", dir=parent) as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "knowledge-graph.lbug"
            node_csv = tmp_path / "nodes.csv"
            edge_csv = tmp_path / "edges.csv"
            node_ids = {node.id for node in snapshot.nodes}
            kept_edges = [
                edge
                for edge in snapshot.edges
                if edge.source in node_ids and edge.target in node_ids
            ]
            self._write_node_csv(node_csv, snapshot.nodes)
            self._write_edge_csv(edge_csv, kept_edges)
            db = lb.Database(str(db_path))
            conn = lb.Connection(db)
            self._create_schema(conn)
            copy_options = "(HEADER=true, DELIM='\\t')"
            conn.execute(
                f"COPY KGNode FROM {self._sql_string(node_csv)} {copy_options}"
            )
            conn.execute(
                f"COPY KGEdge FROM {self._sql_string(edge_csv)} {copy_options}"
            )
            conn.close()
            self._replace_path(db_path)
        return {
            "path": self.path,
            "method": "copy",
            "node_count": len(snapshot.nodes),
            "edge_count": len(kept_edges),
            "skipped_edge_count": len(snapshot.edges) - len(kept_edges),
        }

    def _write_row_by_row(
        self,
        lb: Any,
        snapshot: KnowledgeGraphSnapshot,
    ) -> dict[str, Any]:
        db = lb.Database(self.path)
        conn = lb.Connection(db)
        self._create_schema(conn)
        self._clear(conn)
        node_ids = {node.id for node in snapshot.nodes}
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
        edge_count = 0
        for edge in snapshot.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                continue
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
            edge_count += 1
        conn.close()
        return {
            "path": self.path,
            "method": "row_by_row",
            "node_count": len(snapshot.nodes),
            "edge_count": edge_count,
            "skipped_edge_count": len(snapshot.edges) - edge_count,
        }

    def status(self) -> dict[str, Any]:
        if not self.available():
            return {
                "available": False,
                "path": self.path,
                "install": "pip install 'tree-sitter-analyzer[graph]'",
            }
        if not os.path.exists(self.path):
            return {
                "available": True,
                "path": self.path,
                "exists": False,
            }
        stat = os.stat(self.path)
        return {
            "available": True,
            "path": self.path,
            "exists": True,
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }

    def exists(self) -> bool:
        return os.path.exists(self.path)

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

    @staticmethod
    def _write_node_csv(path: Path, nodes: list[KnowledgeNode]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(
                ["id", "kind", "label", "file_path", "language", "metadata_json"]
            )
            for node in nodes:
                writer.writerow(
                    [
                        node.id,
                        node.kind,
                        node.label,
                        node.file_path,
                        node.language,
                        json.dumps(node.metadata, ensure_ascii=False),
                    ]
                )

    @staticmethod
    def _write_edge_csv(path: Path, edges: list[KnowledgeEdge]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(
                [
                    "source",
                    "target",
                    "id",
                    "kind",
                    "line",
                    "provenance",
                    "metadata_json",
                ]
            )
            for edge in edges:
                writer.writerow(
                    [
                        edge.source,
                        edge.target,
                        edge.id,
                        edge.kind,
                        edge.line if edge.line is not None else -1,
                        edge.provenance,
                        json.dumps(edge.metadata, ensure_ascii=False),
                    ]
                )

    @staticmethod
    def _sql_string(path: Path) -> str:
        return "'" + path.as_posix().replace("'", "''") + "'"

    def _replace_path(self, source: Path) -> None:
        target = Path(self.path)
        old_path = target.with_name(f"{target.name}.old-{os.getpid()}")
        old_wal = self._wal_path(old_path)
        source_wal = self._wal_path(source)
        target_wal = self._wal_path(target)
        if old_path.exists():
            self._remove_path(old_path)
        if old_wal.exists():
            self._remove_path(old_wal)
        if target.exists():
            target.rename(old_path)
        if target_wal.exists():
            target_wal.rename(old_wal)
        source.rename(target)
        if source_wal.exists():
            source_wal.rename(target_wal)
        if old_path.exists():
            self._remove_path(old_path)
        if old_wal.exists():
            self._remove_path(old_wal)

    @staticmethod
    def _remove_path(path: Path) -> None:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    @staticmethod
    def _wal_path(path: Path) -> Path:
        return path.with_name(f"{path.name}.wal")
