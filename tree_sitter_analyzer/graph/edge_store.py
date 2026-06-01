"""SQLite-backed unified edge store.

The store is intentionally small and dependency-light: it is used by
``ASTCache`` during indexing and by graph/query features at read time.
"""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast


class EdgeKind(str, Enum):
    """Supported code relationship edge kinds."""

    CALLS = "calls"
    IMPORTS = "imports"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    REFERENCES = "references"
    CONTAINS = "contains"
    OVERRIDES = "overrides"
    TYPE_OF = "type_of"
    RETURNS = "returns"
    INSTANTIATES = "instantiates"
    DECORATES = "decorates"


@dataclass(frozen=True)
class Edge:
    """One directed relationship between two indexed code nodes."""

    source_node_id: str
    target_node_id: str
    kind: EdgeKind | str
    line: int | None = None
    provenance: str = "tree-sitter"
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_kind(self) -> str:
        return self.kind.value if isinstance(self.kind, EdgeKind) else str(self.kind)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "kind": self.normalized_kind(),
            "line": self.line,
            "provenance": self.provenance,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class Subgraph:
    """A small reachable graph slice."""

    nodes: list[str]
    edges: list[Edge]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "edges": [edge.to_dict() for edge in self.edges],
        }


EDGE_STORE_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER,
    provenance TEXT DEFAULT 'tree-sitter',
    metadata TEXT,
    UNIQUE(source_node_id, target_node_id, kind, line)
)
""".strip(),
    "CREATE INDEX IF NOT EXISTS idx_edges_source_kind ON edges(source_node_id, kind)",
    "CREATE INDEX IF NOT EXISTS idx_edges_target_kind ON edges(target_node_id, kind)",
    "CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind)",
)

EDGE_STORE_SCHEMA = ";\n\n".join(EDGE_STORE_SCHEMA_STATEMENTS) + ";"


class EdgeStore:
    """CRUD and traversal API for the unified ``edges`` table."""

    def __init__(self, conn_or_db_path: sqlite3.Connection | str) -> None:
        self._owns_conn = isinstance(conn_or_db_path, str)
        if self._owns_conn:
            self._conn = sqlite3.connect(str(conn_or_db_path))
            self._conn.row_factory = sqlite3.Row
        else:
            self._conn = cast(sqlite3.Connection, conn_or_db_path)
        self.ensure_schema()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def ensure_schema(self) -> None:
        for statement in EDGE_STORE_SCHEMA_STATEMENTS:
            self._conn.execute(statement)
        self._commit_if_owned()

    def close(self) -> None:
        if self._owns_conn:
            self._conn.close()

    def replace_edges_for_file(self, file_path: str, edges: list[Edge]) -> None:
        """Replace all edges whose source belongs to ``file_path``."""
        file_node_id = file_node(file_path)
        symbol_prefix = _escape_like(f"{file_path}:")
        self._conn.execute(
            "DELETE FROM edges "
            "WHERE source_node_id = ? OR source_node_id LIKE ? ESCAPE '\\'",
            (file_node_id, f"{symbol_prefix}%"),
        )
        self.upsert_edges(edges)

    def upsert_edges(self, edges: list[Edge]) -> None:
        for edge in edges:
            self._conn.execute(
                """INSERT OR REPLACE INTO edges
                   (source_node_id, target_node_id, kind, line, provenance, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.normalized_kind(),
                    edge.line,
                    edge.provenance,
                    json.dumps(edge.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
        self._commit_if_owned()

    def _commit_if_owned(self) -> None:
        if self._owns_conn:
            self._conn.commit()

    def get_edges(
        self,
        node_id: str,
        kind: EdgeKind | str | None = None,
        direction: str = "outgoing",
    ) -> list[Edge]:
        """Return edges touching ``node_id`` in one direction or both."""
        kind_value = _kind_value(kind)
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError("direction must be outgoing, incoming, or both")
        if kind_value is not None:
            sql, params = _edge_query_with_kind(direction, node_id, kind_value)
        else:
            sql, params = _edge_query_without_kind(direction, node_id)
        return [_edge_from_row(row) for row in self._conn.execute(sql, params)]

    def get_neighbors(
        self,
        node_id: str,
        depth: int = 2,
        kinds: list[EdgeKind | str] | None = None,
    ) -> Subgraph:
        """Breadth-first outgoing traversal from ``node_id``."""
        if depth <= 0:
            return Subgraph(nodes=[node_id], edges=[])
        kind_values = {_kind_value(kind) for kind in kinds or []}
        seen_nodes = {node_id}
        seen_edges: set[tuple[str, str, str, int | None]] = set()
        edges: list[Edge] = []
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in self.get_edges(current, direction="outgoing"):
                if kind_values and edge.normalized_kind() not in kind_values:
                    continue
                edge_key = (
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.normalized_kind(),
                    edge.line,
                )
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                edges.append(edge)
                if edge.target_node_id not in seen_nodes:
                    seen_nodes.add(edge.target_node_id)
                    queue.append((edge.target_node_id, current_depth + 1))
        return Subgraph(nodes=sorted(seen_nodes), edges=edges)

    def get_inheritance_tree(self, class_name: str) -> list[dict[str, Any]]:
        """Return inheritance edges whose target is ``class_name``."""
        rows = self._conn.execute(
            """SELECT * FROM edges
               WHERE kind IN (?, ?)
                 AND (
                    target_node_id = ?
                    OR target_node_id = ?
                    OR target_node_id LIKE ?
                    OR target_node_id LIKE ?
                 )
               ORDER BY source_node_id, line""",
            (
                EdgeKind.EXTENDS.value,
                EdgeKind.IMPLEMENTS.value,
                class_name,
                class_node(class_name),
                f"%:{class_name}:%",
                f"%.{class_name}:%",
            ),
        ).fetchall()
        return [_edge_from_row(row).to_dict() for row in rows]


def symbol_node(file_path: str, name: str, line: int | None = None) -> str:
    """Build a stable file-scoped symbol node id."""
    clean = (name or "<anonymous>").replace("\n", " ").strip()
    if line is None:
        return f"{file_path}:{clean}"
    return f"{file_path}:{clean}:{int(line)}"


def file_node(file_path: str) -> str:
    return f"file:{file_path}"


def module_node(module_path: str) -> str:
    return f"module:{module_path}"


def class_node(class_name: str) -> str:
    return f"class:{class_name}"


def _kind_value(kind: EdgeKind | str | None) -> str | None:
    if kind is None:
        return None
    return kind.value if isinstance(kind, EdgeKind) else str(kind)


def _edge_query_with_kind(
    direction: str,
    node_id: str,
    kind_value: str,
) -> tuple[str, tuple[str, ...]]:
    if direction == "outgoing":
        return (
            "SELECT * FROM edges WHERE source_node_id = ? AND kind = ? "
            "ORDER BY kind, source_node_id, target_node_id, line",
            (node_id, kind_value),
        )
    if direction == "incoming":
        return (
            "SELECT * FROM edges WHERE target_node_id = ? AND kind = ? "
            "ORDER BY kind, source_node_id, target_node_id, line",
            (node_id, kind_value),
        )
    return (
        "SELECT * FROM edges WHERE (source_node_id = ? OR target_node_id = ?) "
        "AND kind = ? ORDER BY kind, source_node_id, target_node_id, line",
        (node_id, node_id, kind_value),
    )


def _edge_query_without_kind(
    direction: str, node_id: str
) -> tuple[str, tuple[str, ...]]:
    if direction == "outgoing":
        return (
            "SELECT * FROM edges WHERE source_node_id = ? "
            "ORDER BY kind, source_node_id, target_node_id, line",
            (node_id,),
        )
    if direction == "incoming":
        return (
            "SELECT * FROM edges WHERE target_node_id = ? "
            "ORDER BY kind, source_node_id, target_node_id, line",
            (node_id,),
        )
    return (
        "SELECT * FROM edges WHERE (source_node_id = ? OR target_node_id = ?) "
        "ORDER BY kind, source_node_id, target_node_id, line",
        (node_id, node_id),
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _edge_from_row(row: sqlite3.Row) -> Edge:
    try:
        metadata = json.loads(row["metadata"] or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    return Edge(
        source_node_id=row["source_node_id"],
        target_node_id=row["target_node_id"],
        kind=row["kind"],
        line=row["line"],
        provenance=row["provenance"] or "tree-sitter",
        metadata=metadata,
    )
