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


@dataclass(frozen=True)
class NodeRef:
    """Parsed node id components used by graph read paths."""

    file_path: str
    name: str
    line: int


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

    def __init__(
        self,
        conn_or_db_path: sqlite3.Connection | str,
        *,
        ensure_schema: bool = True,
    ) -> None:
        self._owns_conn = isinstance(conn_or_db_path, str)
        if self._owns_conn:
            self._conn = sqlite3.connect(str(conn_or_db_path))
            self._conn.row_factory = sqlite3.Row
        else:
            self._conn = cast(sqlite3.Connection, conn_or_db_path)
        if ensure_schema:
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

    def has_edges(self, kind: EdgeKind | str | None = None) -> bool:
        """Return true when the store contains at least one edge."""
        kind_value = _kind_value(kind)
        if kind_value is None:
            row = self._conn.execute("SELECT 1 FROM edges LIMIT 1").fetchone()
        else:
            row = self._conn.execute(
                "SELECT 1 FROM edges WHERE kind = ? LIMIT 1",
                (kind_value,),
            ).fetchone()
        return row is not None

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

    def query_callers(
        self,
        callee_name: str,
        callee_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Return callers of ``callee_name`` from unified CALLS edges."""
        return _bfs_call_edges(
            self._conn,
            start_name=callee_name,
            start_file=callee_file,
            max_depth=max_depth,
            direction="callers",
        )

    def query_callees(
        self,
        caller_name: str,
        caller_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Return callees of ``caller_name`` from unified CALLS edges."""
        return _bfs_call_edges(
            self._conn,
            start_name=caller_name,
            start_file=caller_file,
            max_depth=max_depth,
            direction="callees",
        )


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


def parse_node_id(node_id: str) -> NodeRef:
    """Parse a stable node id into file/name/line components."""
    if node_id.startswith("file:"):
        return NodeRef(file_path=node_id.removeprefix("file:"), name="", line=0)
    if node_id.startswith("module:"):
        return NodeRef(file_path="", name=node_id.removeprefix("module:"), line=0)
    if node_id.startswith("class:"):
        return NodeRef(file_path="", name=node_id.removeprefix("class:"), line=0)
    parts = node_id.rsplit(":", 2)
    if len(parts) == 3:
        file_path, name, line_text = parts
        try:
            return NodeRef(file_path=file_path, name=name, line=int(line_text))
        except ValueError:
            pass
    parts = node_id.rsplit(":", 1)
    if len(parts) == 2:
        return NodeRef(file_path=parts[0], name=parts[1], line=0)
    return NodeRef(file_path="", name=node_id, line=0)


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


def _bfs_call_edges(
    conn: sqlite3.Connection,
    start_name: str,
    start_file: str | None,
    max_depth: int,
    direction: str,
) -> list[dict[str, Any]]:
    if max_depth <= 0:
        return []
    start_file = start_file.replace("\\", "/") if start_file else None
    visited: set[str] = set()
    result: list[dict[str, Any]] = []
    queue: deque[tuple[str, str | None, int]] = deque([(start_name, start_file, 0)])
    while queue:
        current_name, current_file, depth = queue.popleft()
        if depth >= max_depth:
            continue
        rows = (
            _direct_callers(conn, current_name, current_file)
            if direction == "callers"
            else _direct_callees(conn, current_name, current_file)
        )
        for row in rows:
            edge = _edge_from_row(row)
            source = parse_node_id(edge.source_node_id)
            target = parse_node_id(edge.target_node_id)
            key = (
                f"{source.file_path}:{source.name}:{source.line}:"
                f"{target.file_path}:{target.name}:{target.line}"
            )
            if key in visited:
                continue
            visited.add(key)
            result.append(_call_edge_entry(edge, source, target, depth))
            if max_depth > 1:
                if direction == "callers":
                    queue.append((source.name, source.file_path, depth + 1))
                else:
                    queue.append((target.name, None, depth + 1))
    return result


def _call_edges(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM edges WHERE kind = ? ORDER BY source_node_id, target_node_id, line",
        (EdgeKind.CALLS.value,),
    ).fetchall()


def _direct_callers(
    conn: sqlite3.Connection,
    callee_name: str,
    callee_file: str | None,
) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    for row in _call_edges(conn):
        edge = _edge_from_row(row)
        target = parse_node_id(edge.target_node_id)
        if not _matches_callee(edge, target, callee_name):
            continue
        if callee_file and target.file_path != callee_file:
            continue
        rows.append(row)
    return rows


def _direct_callees(
    conn: sqlite3.Connection,
    caller_name: str,
    caller_file: str | None,
) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    bare = caller_name.split(".")[-1] if "." in caller_name else caller_name
    for row in _call_edges(conn):
        edge = _edge_from_row(row)
        source = parse_node_id(edge.source_node_id)
        if source.name not in {caller_name, bare}:
            continue
        if caller_file and source.file_path != caller_file:
            continue
        rows.append(row)
    return rows


def _matches_callee(edge: Edge, target: NodeRef, callee_name: str) -> bool:
    names = {target.name, str(edge.metadata.get("callee_full", ""))}
    return callee_name in names


def _call_edge_entry(
    edge: Edge,
    source: NodeRef,
    target: NodeRef,
    depth: int,
) -> dict[str, Any]:
    resolved_file = str(edge.metadata.get("callee_resolved_file", ""))
    return {
        "caller_name": source.name,
        "caller_file": source.file_path,
        "caller_line": source.line,
        "callee_name": target.name,
        "callee_full": str(edge.metadata.get("callee_full", "")),
        "callee_file": resolved_file or target.file_path,
        "callee_resolved_file": resolved_file,
        "callee_line": target.line or edge.line or 0,
        "depth": depth + 1,
    }
