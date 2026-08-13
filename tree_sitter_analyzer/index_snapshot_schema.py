"""Schema ownership and canonical fingerprints for index snapshots."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import struct
import time
from typing import Any

from .index_snapshot_capability import strict_call_graph_marker
from .index_source_snapshot import (
    SOURCE_SCOPE_DESCRIPTOR_BYTE_BUDGET,
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
    "ast_symbol_projection_state": frozenset(
        {"file_path", "content_hash", "symbol_count", "projection_digest"}
    ),
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
_SCHEMA_VALIDATION_ROW_BUDGET = 64
_SCHEMA_VALIDATION_COLUMN_BUDGET = 4096


_MANIFEST_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MANIFEST_TEXT_BYTE_BUDGET = 1024 * 1024


def validate_manifest_scalars(manifest: sqlite3.Row) -> None:
    """Reject SQLite coercions before comparisons or descriptor parsing."""
    root = manifest["canonical_root"]
    source = manifest["source_fingerprint"]
    index = manifest["index_fingerprint"]
    count = manifest["file_count"]
    descriptor = manifest["source_scope_descriptor"]
    version = manifest["manifest_version"]
    if (
        not isinstance(root, str)
        or not root
        or "\0" in root
        or len(root.encode("utf-8", "surrogatepass")) > _MANIFEST_TEXT_BYTE_BUDGET
        or not isinstance(source, str)
        or _MANIFEST_FINGERPRINT.fullmatch(source) is None
        or not isinstance(index, str)
        or _MANIFEST_FINGERPRINT.fullmatch(index) is None
        or not isinstance(count, int)
        or isinstance(count, bool)
        or not 0 <= count <= 2_000_000
        or not isinstance(descriptor, str)
        or not descriptor
        or len(descriptor) > SOURCE_SCOPE_DESCRIPTOR_BYTE_BUDGET
        or not descriptor.isascii()
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version != 2
    ):
        raise ValueError("INDEX_MANIFEST_INVALID")


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
    """Certify one source/index epoch while excluding every SQLite writer."""
    # Finish all preceding indexing work before the certification transaction.
    conn.commit()
    transaction_started = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        transaction_started = True
        if not strict_call_graph_marker(conn):
            raise sqlite3.OperationalError("CALL_GRAPH_INCOMPLETE")
        root = os.path.realpath(os.path.abspath(project_root))
        scope = source_scope or make_source_scope_descriptor()
        scope_json = canonical_source_scope_descriptor(scope)
        source = source_fingerprint(conn, root)
        index = index_fingerprint(conn, root)
        recorded = recorded_source_rows(conn)
        if os.name == "posix" and os.path.exists("/dev/fd"):
            current = capture_current_source_snapshot(root, scope)
        else:
            from .portable_source_snapshot import capture_portable_source_snapshot

            current = capture_portable_source_snapshot(
                root, scope, deadline=time.monotonic() + _FINGERPRINT_DEADLINE_SECONDS
            )
        if current.state != "exact" or current.rows != recorded:
            raise sqlite3.OperationalError("SOURCE_CHANGED")
        conn.execute("DELETE FROM ast_index_snapshot_manifest")
        conn.execute(
            "INSERT INTO ast_index_snapshot_manifest "
            "(singleton, canonical_root, source_fingerprint, index_fingerprint, "
            "file_count, source_scope_descriptor, manifest_version) "
            "VALUES (1, ?, ?, ?, ?, ?, 2)",
            (root, source, index, len(recorded), scope_json),
        )
        conn.commit()
    except BaseException:
        # A failed certifier does not own any published manifest epoch. Roll the
        # transaction back so a prior valid (or observably stale) epoch remains;
        # status fingerprints determine staleness without destructive cleanup.
        if transaction_started and conn.in_transaction:
            conn.rollback()
        raise


def validate_snapshot_schema(
    conn: sqlite3.Connection, *, deadline: float | None = None
) -> None:
    """Validate the reader schema without unbounded SQLite work or rows."""
    deadline = (
        time.monotonic() + _FINGERPRINT_DEADLINE_SECONDS
        if deadline is None
        else deadline
    )
    found_current = False
    schema_bytes = 0

    def expired() -> int:
        return int(time.monotonic() > deadline)

    conn.set_progress_handler(expired, 1_000)
    try:
        cursor = conn.execute(
            "SELECT typeof(version), length(CAST(version AS BLOB)), "
            "CASE WHEN typeof(version) = 'integer' "
            "AND version BETWEEN 1 AND ? THEN 1 ELSE 0 END, "
            "CASE WHEN typeof(version) = 'integer' "
            "AND version = ? THEN 1 ELSE 0 END "
            "FROM ast_schema_version LIMIT ?",
            (
                SNAPSHOT_SCHEMA_VERSION,
                SNAPSHOT_SCHEMA_VERSION,
                _SCHEMA_VALIDATION_ROW_BUDGET + 1,
            ),
        )
        version_rows = 0
        while True:
            _check_deadline(deadline)
            row = cursor.fetchone()
            if row is None:
                break
            version_rows += 1
            if version_rows > _SCHEMA_VALIDATION_ROW_BUDGET:
                raise ValueError("INCOMPATIBLE_SCHEMA")
            if (
                len(row) != 4
                or row[0] != "integer"
                or type(row[1]) is not int
                or not 0 <= row[1] <= 32
                or type(row[2]) is not int
                or row[2] != 1
                or type(row[3]) is not int
                or row[3] not in (0, 1)
            ):
                raise ValueError("INCOMPATIBLE_SCHEMA")
            if row[3] == 1:
                found_current = True
        if not found_current:
            raise ValueError("INCOMPATIBLE_SCHEMA")

        table_count_row = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()
        _check_deadline(deadline)
        if table_count_row is None or int(table_count_row[0]) > _SCHEMA_TABLE_BUDGET:
            raise ValueError("INCOMPATIBLE_SCHEMA")
        for table, required in _REQUIRED_COLUMNS.items():
            _check_deadline(deadline)
            present = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
                (table,),
            ).fetchone()
            if present is None:
                raise ValueError("INCOMPATIBLE_SCHEMA")
            columns: set[str] = set()
            column_rows = 0
            cursor = conn.execute(
                "SELECT typeof(name), length(CAST(name AS BLOB)), "
                "CASE WHEN typeof(name) = 'text' "
                "AND length(CAST(name AS BLOB)) <= ? THEN name END "
                "FROM pragma_table_info(?) LIMIT ?",
                (
                    _SCHEMA_CELL_BYTE_BUDGET,
                    table,
                    _SCHEMA_VALIDATION_COLUMN_BUDGET + 1,
                ),
            )
            while True:
                _check_deadline(deadline)
                row = cursor.fetchone()
                if row is None:
                    break
                column_rows += 1
                if column_rows > _SCHEMA_VALIDATION_COLUMN_BUDGET:
                    raise ValueError("INCOMPATIBLE_SCHEMA")
                if (
                    len(row) != 3
                    or row[0] != "text"
                    or type(row[1]) is not int
                    or not 0 <= row[1] <= _SCHEMA_CELL_BYTE_BUDGET
                    or not isinstance(row[2], str)
                ):
                    raise ValueError("INCOMPATIBLE_SCHEMA")
                name_bytes = row[1]
                schema_bytes += name_bytes
                if schema_bytes > _SCHEMA_TOTAL_BYTE_BUDGET:
                    raise ValueError("INCOMPATIBLE_SCHEMA")
                columns.add(row[2])
            if not required.issubset(columns):
                raise ValueError("INCOMPATIBLE_SCHEMA")
    except sqlite3.OperationalError as exc:
        if time.monotonic() > deadline or "interrupt" in str(exc).lower():
            raise RuntimeError("INDEX_FINGERPRINT_DEADLINE") from exc
        raise
    finally:
        conn.set_progress_handler(None, 0)


def source_fingerprint(conn: sqlite3.Connection, _root: str) -> str:
    """Hash recorded inventory with the shared bounded, deadline-aware order."""
    deadline = time.monotonic() + _FINGERPRINT_DEADLINE_SECONDS
    try:
        rows = recorded_source_rows(conn, deadline=deadline)
        return inventory_fingerprint(rows, deadline=deadline)
    except TimeoutError as exc:
        raise RuntimeError("INDEX_FINGERPRINT_DEADLINE") from exc


def index_fingerprint(
    conn: sqlite3.Connection, root: str, *, deadline: float | None = None
) -> str:
    """Hash every query-visible SQLite table schema and typed row."""
    deadline = (
        time.monotonic() + _FINGERPRINT_DEADLINE_SECONDS
        if deadline is None
        else deadline
    )
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
    # Inventory every table with table_xinfo before any row expression runs.
    # Generated columns can allocate arbitrarily large values even in a tiny DB;
    # hidden virtual-table columns, unlike generated columns, are omitted by
    # SELECT * and therefore are intentionally outside the query-visible scope.
    table_columns = {
        table: _query_visible_columns(conn, table, deadline) for table, _ in inventory
    }
    rows_seen = bytes_seen = 0
    for table, schema in inventory:
        _check_deadline(deadline)
        _frame(digest, b"table", table.encode("utf-8", "surrogatepass"))
        _frame(digest, b"schema", schema.encode("utf-8", "surrogatepass"))
        columns = table_columns[table]
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
        selected = ", ".join(quoted_columns)
        query = f"SELECT {selected} FROM {_quote_identifier(table)} ORDER BY {order_by}"
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


def _query_visible_columns(
    conn: sqlite3.Connection, table: str, deadline: float
) -> tuple[str, ...]:
    """Return SELECT-visible columns and reject generated expressions."""
    columns: list[str] = []
    cursor = conn.execute(f"PRAGMA table_xinfo({_quote_identifier(table)})")
    while True:
        _check_deadline(deadline)
        row = cursor.fetchone()
        if row is None:
            break
        if len(row) < 7 or not isinstance(row[1], str):
            raise RuntimeError("INDEX_FINGERPRINT_UNSUPPORTED_SCHEMA")
        hidden = row[6]
        if hidden in (2, 3):
            raise RuntimeError("INDEX_FINGERPRINT_UNSUPPORTED_SCHEMA")
        if hidden == 0:
            columns.append(row[1])
        elif hidden != 1:
            raise RuntimeError("INDEX_FINGERPRINT_UNSUPPORTED_SCHEMA")
    if not columns:
        raise RuntimeError("INDEX_FINGERPRINT_UNSUPPORTED_SCHEMA")
    return tuple(columns)


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
