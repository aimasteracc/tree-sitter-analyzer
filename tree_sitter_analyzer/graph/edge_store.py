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
    caller_name TEXT NOT NULL DEFAULT '',
    callee_name TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '',
    caller_line INTEGER NOT NULL DEFAULT 0,
    callee_full TEXT NOT NULL DEFAULT '',
    callee_line INTEGER NOT NULL DEFAULT 0,
    language TEXT NOT NULL DEFAULT '',
    callee_resolution TEXT NOT NULL DEFAULT 'unknown',
    callee_resolved_file TEXT NOT NULL DEFAULT '',
    callee_symbol_id INTEGER,
    UNIQUE(source_node_id, target_node_id, kind, line)
)
""".strip(),
    "CREATE INDEX IF NOT EXISTS idx_edges_source_kind ON edges(source_node_id, kind)",
    "CREATE INDEX IF NOT EXISTS idx_edges_target_kind ON edges(target_node_id, kind)",
    "CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind)",
    "CREATE INDEX IF NOT EXISTS idx_edges_callee_name ON edges(callee_name, kind)",
    "CREATE INDEX IF NOT EXISTS idx_edges_caller_name ON edges(caller_name, kind)",
    "CREATE INDEX IF NOT EXISTS idx_edges_file_path ON edges(file_path)",
    "CREATE INDEX IF NOT EXISTS idx_edges_resolved ON edges(callee_resolved_file)",
)

EDGE_STORE_SCHEMA = ";\n\n".join(EDGE_STORE_SCHEMA_STATEMENTS) + ";"

# Real columns promoted from the JSON ``metadata`` blob. ALTER TABLE has no
# IF NOT EXISTS form, so these are added only when a legacy ``edges`` table
# (v8/v9/v10 shape) is missing them. B1.1 promoted caller_name/callee_name/
# file_path; B1.3 promotes the remaining resolution scalars so synapse /
# unresolved second-pass resolution can UPDATE them in place (no ast_call_edges).
_EDGE_NAME_COLUMNS: tuple[tuple[str, str], ...] = (
    (
        "caller_name",
        "ALTER TABLE edges ADD COLUMN caller_name TEXT NOT NULL DEFAULT ''",
    ),
    (
        "callee_name",
        "ALTER TABLE edges ADD COLUMN callee_name TEXT NOT NULL DEFAULT ''",
    ),
    ("file_path", "ALTER TABLE edges ADD COLUMN file_path TEXT NOT NULL DEFAULT ''"),
    (
        "caller_line",
        "ALTER TABLE edges ADD COLUMN caller_line INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "callee_full",
        "ALTER TABLE edges ADD COLUMN callee_full TEXT NOT NULL DEFAULT ''",
    ),
    (
        "callee_line",
        "ALTER TABLE edges ADD COLUMN callee_line INTEGER NOT NULL DEFAULT 0",
    ),
    ("language", "ALTER TABLE edges ADD COLUMN language TEXT NOT NULL DEFAULT ''"),
    (
        "callee_resolution",
        "ALTER TABLE edges ADD COLUMN callee_resolution TEXT NOT NULL "
        "DEFAULT 'unknown'",
    ),
    (
        "callee_resolved_file",
        "ALTER TABLE edges ADD COLUMN callee_resolved_file TEXT NOT NULL DEFAULT ''",
    ),
    ("callee_symbol_id", "ALTER TABLE edges ADD COLUMN callee_symbol_id INTEGER"),
)


def ensure_edge_schema(conn: sqlite3.Connection) -> None:
    """Create the ``edges`` table + indexes; ALTER legacy tables for new columns.

    The table is created first (no-op if present), then the promoted name/file
    columns are added on legacy (v8/v9) tables before the name-column indexes
    are created — ``CREATE INDEX ON edges(callee_name, ...)`` would otherwise
    fail on a table that predates the column.
    """
    conn.execute(EDGE_STORE_SCHEMA_STATEMENTS[0])
    existing = {row[1] for row in conn.execute("PRAGMA table_info(edges)").fetchall()}
    for column, ddl in _EDGE_NAME_COLUMNS:
        if column not in existing:
            conn.execute(ddl)
    for statement in EDGE_STORE_SCHEMA_STATEMENTS[1:]:
        conn.execute(statement)


def backfill_edge_name_columns(conn: sqlite3.Connection) -> None:
    """Populate caller_name/callee_name/file_path for pre-v10 rows.

    Re-parses existing node ids so legacy ``edges`` rows (written before the
    columns existed) become queryable via the name indexes. Idempotent: only
    touches rows where all three promoted columns are still empty.
    """
    rows = conn.execute(
        "SELECT id, source_node_id, target_node_id FROM edges "
        "WHERE caller_name = '' AND callee_name = '' AND file_path = ''"
    ).fetchall()
    for row in rows:
        source = parse_node_id(row[1])
        target = parse_node_id(row[2])
        conn.execute(
            "UPDATE edges SET caller_name = ?, callee_name = ?, file_path = ? "
            "WHERE id = ?",
            (source.name, target.name, source.file_path, row[0]),
        )


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
        ensure_edge_schema(self._conn)
        self._commit_if_owned()

    def close(self) -> None:
        if self._owns_conn:
            self._conn.close()

    def replace_edges_for_file(
        self,
        file_path: str,
        edges: list[Edge],
        *,
        preserve_calls: bool = False,
    ) -> None:
        """Replace all edges whose source belongs to ``file_path``.

        Deletion is keyed on the indexed ``file_path`` real column (B1.3) — the
        source's file is recorded there for every edge kind — which replaces the
        ``source_node_id LIKE 'file:%'`` prefix scan that was a full-table hot
        spot on large repos. The node-id predicates remain as a belt-and-braces
        fallback for any pre-B1.1 row whose ``file_path`` column was never
        backfilled.

        ``preserve_calls=True`` keeps existing CALLS rows (and their second-pass
        resolution columns) intact — used by the structural-edge refresh path,
        which has no extracted call-edge source to rebuild them from after the
        ``ast_call_edges`` table was dropped.
        """
        file_node_id = file_node(file_path)
        symbol_prefix = _escape_like(f"{file_path}:")
        calls_clause = "" if not preserve_calls else "kind != 'calls' AND "
        self._conn.execute(
            f"DELETE FROM edges WHERE {calls_clause}"  # nosec B608 — constant clause
            "(file_path = ? OR source_node_id = ? OR source_node_id LIKE ? ESCAPE '\\')",
            (file_path, file_node_id, f"{symbol_prefix}%"),
        )
        self.upsert_edges(edges)

    def backfill_name_columns(self) -> None:
        """Populate caller_name/callee_name/file_path for pre-v10 rows."""
        backfill_edge_name_columns(self._conn)
        self._commit_if_owned()

    def upsert_edges(self, edges: list[Edge]) -> None:
        for edge in edges:
            cols = _edge_real_columns(edge)
            self._conn.execute(
                """INSERT OR REPLACE INTO edges
                   (source_node_id, target_node_id, kind, line, provenance,
                    metadata, caller_name, callee_name, file_path,
                    caller_line, callee_full, callee_line, language,
                    callee_resolution, callee_resolved_file, callee_symbol_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.normalized_kind(),
                    edge.line,
                    edge.provenance,
                    json.dumps(edge.metadata, ensure_ascii=False, sort_keys=True),
                    cols["caller_name"],
                    cols["callee_name"],
                    cols["file_path"],
                    cols["caller_line"],
                    cols["callee_full"],
                    cols["callee_line"],
                    cols["language"],
                    cols["callee_resolution"],
                    cols["callee_resolved_file"],
                    cols["callee_symbol_id"],
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


def _edge_real_columns(edge: Edge) -> dict[str, Any]:
    """Derive every promoted real-column value for one ``Edge``.

    ``caller_name``/``callee_name``/``file_path`` mirror ``parse_node_id`` over
    the source/target node ids (so SQL pushdown returns the same rows the legacy
    Python-side filter did). The resolution scalars (``caller_line``,
    ``callee_full``, ``language``, ``callee_resolution``, ``callee_resolved_file``,
    ``callee_symbol_id``) come from ``metadata`` — the same values that previously
    only lived in the JSON blob — so synapse / unresolved second-pass resolution
    can UPDATE them in place without a separate ``ast_call_edges`` table.
    ``callee_line`` is the call-site line (== ``edge.line`` == legacy
    ``ast_call_edges.callee_line``).
    """
    source = parse_node_id(edge.source_node_id)
    target = parse_node_id(edge.target_node_id)
    meta = edge.metadata
    symbol_id = meta.get("callee_symbol_id")
    return {
        "caller_name": source.name,
        "callee_name": target.name,
        "file_path": source.file_path,
        "caller_line": _as_int(meta.get("caller_line"), source.line),
        "callee_full": str(meta.get("callee_full", "")),
        "callee_line": _as_int(edge.line, target.line),
        "language": str(meta.get("language", "")),
        "callee_resolution": str(meta.get("callee_resolution", "unknown")),
        "callee_resolved_file": str(meta.get("callee_resolved_file", "")),
        "callee_symbol_id": int(symbol_id) if symbol_id is not None else None,
    }


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except (TypeError, ValueError):
        return int(default) if isinstance(default, int) else 0


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
            result.append(_call_edge_entry(row, edge, source, target, depth))
            if max_depth > 1:
                if direction == "callers":
                    queue.append((source.name, source.file_path, depth + 1))
                else:
                    queue.append((target.name, None, depth + 1))
    return result


def _callers_by_name(conn: sqlite3.Connection, callee_name: str) -> list[sqlite3.Row]:
    """CALLS rows whose callee matches ``callee_name`` (index-backed pushdown).

    The ``callee_name`` column holds the *bare* callee name (target node name).
    A query may pass a fully-qualified name (e.g. ``engine.handleHTTPRequest``)
    that only matches via ``metadata.callee_full``; in that case the candidate
    set is narrowed by the bare suffix and ``_matches_callee`` confirms the full
    match in Python. Either way the SQL stays on ``idx_edges_callee_name``.
    """
    bare = callee_name.split(".")[-1] if "." in callee_name else callee_name
    if callee_name == bare:
        return conn.execute(
            "SELECT * FROM edges WHERE kind = ? AND callee_name = ? "
            "ORDER BY source_node_id, target_node_id, line",
            (EdgeKind.CALLS.value, callee_name),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM edges WHERE kind = ? AND callee_name IN (?, ?) "
        "ORDER BY source_node_id, target_node_id, line",
        (EdgeKind.CALLS.value, callee_name, bare),
    ).fetchall()


def _callees_by_name(
    conn: sqlite3.Connection, caller_name: str, bare: str
) -> list[sqlite3.Row]:
    """CALLS rows whose caller matches ``caller_name``/``bare`` (index-backed)."""
    if caller_name == bare:
        return conn.execute(
            "SELECT * FROM edges WHERE kind = ? AND caller_name = ? "
            "ORDER BY source_node_id, target_node_id, line",
            (EdgeKind.CALLS.value, caller_name),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM edges WHERE kind = ? AND caller_name IN (?, ?) "
        "ORDER BY source_node_id, target_node_id, line",
        (EdgeKind.CALLS.value, caller_name, bare),
    ).fetchall()


def _direct_callers(
    conn: sqlite3.Connection,
    callee_name: str,
    callee_file: str | None,
) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    fallback_rows: list[sqlite3.Row] = []
    for row in _callers_by_name(conn, callee_name):
        edge = _edge_from_row(row)
        source = parse_node_id(edge.source_node_id)
        target = parse_node_id(edge.target_node_id)
        if not _matches_callee(row, target, callee_name):
            continue
        if callee_file:
            resolved_file = str(
                _row_col(row, "callee_resolved_file", "callee_resolved_file", edge)
                or ""
            )
            # B1.3: cross-file resolution lives in the ``callee_resolved_file``
            # column on the original (same-file) CALLS edge, so a query scoped
            # to the callee's resolved file must match it even when the edge's
            # target node still points at the unresolved same-file symbol.
            if target.file_path == callee_file or resolved_file == callee_file:
                rows.append(row)
            elif source.file_path == callee_file:
                fallback_rows.append(row)
            continue
        rows.append(row)
    return rows or fallback_rows


def _direct_callees(
    conn: sqlite3.Connection,
    caller_name: str,
    caller_file: str | None,
) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    bare = caller_name.split(".")[-1] if "." in caller_name else caller_name
    for row in _callees_by_name(conn, caller_name, bare):
        edge = _edge_from_row(row)
        source = parse_node_id(edge.source_node_id)
        if source.name not in {caller_name, bare}:
            continue
        if caller_file and source.file_path != caller_file:
            continue
        rows.append(row)
    return rows


def _row_col(row: sqlite3.Row, column: str, meta_key: str, edge: Edge) -> Any:
    """Read a promoted real column, falling back to the metadata JSON.

    Post-v11 every edge row carries the resolution scalars as real columns, so
    synapse / unresolved second-pass UPDATEs are visible here. The metadata
    fallback keeps the reader resilient to rows written by an older schema that
    happen to coexist in the same DB.
    """
    try:
        value = row[column]
    except (IndexError, KeyError):
        value = None
    if value in (None, "", 0):
        meta_value = edge.metadata.get(meta_key)
        if meta_value not in (None, "", 0):
            return meta_value
    return value


def _matches_callee(row: sqlite3.Row, target: NodeRef, callee_name: str) -> bool:
    edge = _edge_from_row(row)
    names = {target.name, str(_row_col(row, "callee_full", "callee_full", edge) or "")}
    return callee_name in names


def _call_edge_entry(
    row: sqlite3.Row,
    edge: Edge,
    source: NodeRef,
    target: NodeRef,
    depth: int,
) -> dict[str, Any]:
    resolved_file = str(
        _row_col(row, "callee_resolved_file", "callee_resolved_file", edge) or ""
    )
    callee_full = str(_row_col(row, "callee_full", "callee_full", edge) or "")
    return {
        "caller_name": source.name,
        "caller_file": source.file_path,
        "caller_line": source.line,
        "callee_name": target.name,
        "callee_full": callee_full,
        "callee_file": resolved_file or target.file_path,
        "callee_resolved_file": resolved_file,
        "callee_line": target.line or edge.line or 0,
        "depth": depth + 1,
    }
