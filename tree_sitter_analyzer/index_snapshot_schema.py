"""Schema ownership and canonical fingerprints for index snapshots."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import struct
import time
from typing import Any

from .index_source_snapshot import (
    SourceScopeDescriptor,
    canonical_source_scope_descriptor,
    capture_current_source_snapshot,
    inventory_fingerprint,
    make_source_scope_descriptor,
    recorded_source_rows,
)

SNAPSHOT_SCHEMA_VERSION = 13
SCHEMA_V13_INDEX_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS ast_index_snapshot_manifest (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    canonical_root TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    index_fingerprint TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    source_scope_descriptor TEXT NOT NULL,
    manifest_version INTEGER NOT NULL
);
"""
_CONTROL_TABLES = frozenset(
    {
        "ast_index_snapshot_manifest",
        "ast_cache_metadata",
        "ast_build_state",
        "ast_call_graph_state",
        "ast_resolve_state",
        "sqlite_sequence",
    }
)
_REQUIRED_COLUMNS = {
    "ast_index": frozenset(
        {
            "file_path",
            "content_hash",
            "language",
            "symbols_json",
            "imports_json",
            "structure_json",
        }
    ),
    "ast_imports": frozenset({"file_path", "language", "module_path", "local_name"}),
    "edges": frozenset({"source_node_id", "target_node_id", "kind", "file_path"}),
    "ast_index_snapshot_manifest": frozenset(
        {
            "canonical_root",
            "source_fingerprint",
            "index_fingerprint",
            "file_count",
            "source_scope_descriptor",
            "manifest_version",
        }
    ),
}
_FINGERPRINT_DEADLINE_SECONDS = 5.0
_FINGERPRINT_ROW_BUDGET = 2_000_000
_FINGERPRINT_BYTE_BUDGET = 512 * 1024 * 1024
_FINGERPRINT_CELL_BYTE_BUDGET = 4 * 1024 * 1024
_FINGERPRINT_ROW_BYTE_BUDGET = 16 * 1024 * 1024
_SCHEMA_CELL_BYTE_BUDGET = 1024 * 1024
_SCHEMA_TOTAL_BYTE_BUDGET = 4 * 1024 * 1024
_SCHEMA_TABLE_BUDGET = 4096


def apply_snapshot_migration(conn: sqlite3.Connection, record_fn: Any) -> None:
    """Install the owner-written full-index manifest table (schema v13)."""
    try:
        conn.executescript(SCHEMA_V13_INDEX_SNAPSHOT)
        record_fn(
            conn, SNAPSHOT_SCHEMA_VERSION, "Authoritative index snapshot manifest"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass


def stamp_full_index_manifest(
    conn: sqlite3.Connection,
    project_root: str,
    source_scope: SourceScopeDescriptor | None = None,
) -> None:
    """Atomically certify canonical graph rows and the recorded source inventory."""
    if os.name != "posix" or not os.path.exists("/dev/fd"):
        raise sqlite3.OperationalError("SOURCE_SCOPE_UNSUPPORTED")
    try:
        marker_rows = conn.execute(
            "SELECT id, built FROM ast_call_graph_state WHERE id IN (1, 2) ORDER BY id"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise sqlite3.OperationalError("CALL_GRAPH_INCOMPLETE") from exc
    if [(int(row[0]), int(row[1])) for row in marker_rows] != [(1, 1)]:
        raise sqlite3.OperationalError("CALL_GRAPH_INCOMPLETE")
    root = os.path.realpath(os.path.abspath(project_root))
    scope = source_scope or make_source_scope_descriptor()
    scope_json = canonical_source_scope_descriptor(scope)
    source = source_fingerprint(conn, root)
    index = index_fingerprint(conn, root)
    recorded = recorded_source_rows(conn)
    current = capture_current_source_snapshot(root, scope)
    if current.state != "exact" or current.rows != recorded:
        conn.rollback()
        conn.execute("DELETE FROM ast_index_snapshot_manifest")
        conn.commit()
        raise sqlite3.OperationalError("SOURCE_CHANGED")
    count = len(recorded)
    conn.execute("DELETE FROM ast_index_snapshot_manifest")
    conn.execute(
        "INSERT INTO ast_index_snapshot_manifest "
        "(singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, source_scope_descriptor, manifest_version) "
        "VALUES (1, ?, ?, ?, ?, ?, 2)",
        (root, source, index, count, scope_json),
    )
    conn.commit()


def validate_snapshot_schema(conn: sqlite3.Connection) -> None:
    versions = {
        int(row[0]) for row in conn.execute("SELECT version FROM ast_schema_version")
    }
    if SNAPSHOT_SCHEMA_VERSION not in versions or any(
        v > SNAPSHOT_SCHEMA_VERSION for v in versions
    ):
        raise ValueError("INCOMPATIBLE_SCHEMA")
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if not set(_REQUIRED_COLUMNS).issubset(tables):
        raise ValueError("INCOMPATIBLE_SCHEMA")
    for table, required in _REQUIRED_COLUMNS.items():
        columns = {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}
        if not required.issubset(columns):
            raise ValueError("INCOMPATIBLE_SCHEMA")


def source_fingerprint(conn: sqlite3.Connection, _root: str) -> str:
    """Hash recorded inventory with the shared bounded, deadline-aware order."""
    deadline = time.monotonic() + _FINGERPRINT_DEADLINE_SECONDS
    try:
        rows = recorded_source_rows(conn, deadline=deadline)
        return inventory_fingerprint(rows, deadline=deadline)
    except TimeoutError as exc:
        raise RuntimeError("INDEX_FINGERPRINT_DEADLINE") from exc


def index_fingerprint(conn: sqlite3.Connection, root: str) -> str:
    """Hash every query-visible SQLite table schema and typed row."""
    deadline = time.monotonic() + _FINGERPRINT_DEADLINE_SECONDS
    digest = hashlib.sha256(b"tsa-index-sqlite-v2\0")
    _frame(digest, b"root", root.encode("utf-8", "surrogatepass"))
    _preflight_schema_inventory(conn, deadline)
    inventory = [
        (str(row[0]), str(row[1] or ""))
        for row in _deadline_ordered_rows(
            conn,
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name",
            deadline,
        )
        if str(row[0]) not in _CONTROL_TABLES
    ]
    rows_seen = bytes_seen = 0
    for table, schema in inventory:
        _check_deadline(deadline)
        _frame(digest, b"table", table.encode("utf-8", "surrogatepass"))
        _frame(digest, b"schema", schema.encode("utf-8", "surrogatepass"))
        columns = tuple(
            str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')
        )
        _frame(digest, b"columns", _typed(columns))
        quoted_columns = tuple(_quote_identifier(column) for column in columns)
        preflight_rows, preflight_bytes = _preflight_table_rows(
            conn, table, quoted_columns, deadline
        )
        if (
            rows_seen + preflight_rows > _FINGERPRINT_ROW_BUDGET
            or bytes_seen + preflight_bytes > _FINGERPRINT_BYTE_BUDGET
        ):
            raise RuntimeError("INDEX_FINGERPRINT_BUDGET")
        order_by = ", ".join(f"{column} COLLATE BINARY" for column in quoted_columns)
        query = f"SELECT * FROM {_quote_identifier(table)} ORDER BY {order_by}"
        for row in _deadline_ordered_rows(conn, query, deadline):
            _check_deadline(deadline)
            encoded = _typed(tuple(row))
            rows_seen += 1
            bytes_seen += len(encoded)
            if (
                rows_seen > _FINGERPRINT_ROW_BUDGET
                or bytes_seen > _FINGERPRINT_BYTE_BUDGET
            ):
                raise RuntimeError("INDEX_FINGERPRINT_BUDGET")
            _frame(digest, b"row", encoded)
            _check_deadline(deadline)
    return "sha256:" + digest.hexdigest()


def _preflight_schema_inventory(conn: sqlite3.Connection, deadline: float) -> None:
    """Bound schema text inside SQLite before Python decodes sqlite_master."""
    query = (
        "SELECT length(CAST(name AS BLOB)), length(CAST(sql AS BLOB)) "
        "FROM sqlite_master WHERE type='table'"
    )
    tables = total = 0
    for row in _deadline_ordered_rows(conn, query, deadline):
        _check_deadline(deadline)
        lengths = tuple(0 if value is None else int(value) for value in row)
        if any(length > _SCHEMA_CELL_BYTE_BUDGET for length in lengths):
            raise RuntimeError("INDEX_FINGERPRINT_SCHEMA_CELL_BUDGET")
        tables += 1
        total += sum(lengths)
        if tables > _SCHEMA_TABLE_BUDGET or total > _SCHEMA_TOTAL_BYTE_BUDGET:
            raise RuntimeError("INDEX_FINGERPRINT_SCHEMA_BUDGET")


def _preflight_table_rows(
    conn: sqlite3.Connection,
    table: str,
    quoted_columns: tuple[str, ...],
    deadline: float,
) -> tuple[int, int]:
    """Bound SQLite values before Python materializes or typed-encodes them."""
    lengths = ", ".join(f"length(CAST({column} AS BLOB))" for column in quoted_columns)
    query = f"SELECT {lengths} FROM {_quote_identifier(table)}"
    rows_seen = bytes_seen = 0
    for row in _deadline_ordered_rows(conn, query, deadline):
        _check_deadline(deadline)
        cell_lengths = tuple(0 if value is None else int(value) for value in row)
        if any(length > _FINGERPRINT_CELL_BYTE_BUDGET for length in cell_lengths):
            raise RuntimeError("INDEX_FINGERPRINT_CELL_BUDGET")
        row_bytes = sum(cell_lengths)
        if row_bytes > _FINGERPRINT_ROW_BYTE_BUDGET:
            raise RuntimeError("INDEX_FINGERPRINT_ROW_BUDGET")
        rows_seen += 1
        bytes_seen += row_bytes
        if rows_seen > _FINGERPRINT_ROW_BUDGET or bytes_seen > _FINGERPRINT_BYTE_BUDGET:
            raise RuntimeError("INDEX_FINGERPRINT_BUDGET")
    return rows_seen, bytes_seen


def _deadline_ordered_rows(
    conn: sqlite3.Connection, query: str, deadline: float
) -> Any:
    """Stream an ORDER BY while interrupting SQLite's internal sorter."""

    def expired() -> int:
        return int(time.monotonic() > deadline)

    conn.set_progress_handler(expired, 1_000)
    try:
        yield from conn.execute(query)
    except sqlite3.OperationalError as exc:
        if time.monotonic() > deadline or "interrupt" in str(exc).lower():
            raise RuntimeError("INDEX_FINGERPRINT_DEADLINE") from exc
        raise
    except sqlite3.DataError as exc:
        raise RuntimeError("INDEX_FINGERPRINT_INVALID") from exc
    finally:
        conn.set_progress_handler(None, 0)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _typed(values: tuple[Any, ...]) -> bytes:
    result = bytearray()
    for value in values:
        if value is None:
            tag, raw = b"n", b""
        elif isinstance(value, bytes):
            tag, raw = b"b", value
        elif isinstance(value, int):
            tag, raw = b"i", str(value).encode("ascii")
        elif isinstance(value, float):
            tag, raw = b"f", struct.pack(">d", value)
        else:
            tag, raw = b"t", str(value).encode("utf-8", "surrogatepass")
        result.extend(tag)
        result.extend(len(raw).to_bytes(8, "big"))
        result.extend(raw)
    return bytes(result)


def _frame(digest: Any, label: bytes, raw: bytes) -> None:
    digest.update(len(label).to_bytes(4, "big"))
    digest.update(label)
    digest.update(len(raw).to_bytes(8, "big"))
    digest.update(raw)


def _check_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise RuntimeError("INDEX_FINGERPRINT_DEADLINE")
