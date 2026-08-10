"""Schema ownership and canonical fingerprints for index snapshots."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import struct
import time
from typing import Any

from .index_source_snapshot import inventory_fingerprint, recorded_source_rows

SNAPSHOT_SCHEMA_VERSION = 13
SCHEMA_V13_INDEX_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS ast_index_snapshot_manifest (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    canonical_root TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    index_fingerprint TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    manifest_version INTEGER NOT NULL
);
"""
_CONTROL_TABLES = frozenset(
    {"ast_index_snapshot_manifest", "ast_build_state", "sqlite_sequence"}
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
            "manifest_version",
        }
    ),
}
_FINGERPRINT_DEADLINE_SECONDS = 5.0
_FINGERPRINT_ROW_BUDGET = 2_000_000
_FINGERPRINT_BYTE_BUDGET = 512 * 1024 * 1024


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


def stamp_full_index_manifest(conn: sqlite3.Connection, project_root: str) -> None:
    """Atomically certify canonical graph rows and the recorded source inventory."""
    root = os.path.realpath(os.path.abspath(project_root))
    source = source_fingerprint(conn, root)
    index = index_fingerprint(conn, root)
    count = int(conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0])
    conn.execute("DELETE FROM ast_index_snapshot_manifest")
    conn.execute(
        "INSERT INTO ast_index_snapshot_manifest "
        "(singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, manifest_version) VALUES (1, ?, ?, ?, ?, 1)",
        (root, source, index, count),
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
    """Hash the cache-recorded path/content/language inventory."""
    return inventory_fingerprint(recorded_source_rows(conn))


def index_fingerprint(conn: sqlite3.Connection, root: str) -> str:
    """Hash every query-visible SQLite table schema and typed row."""
    deadline = time.monotonic() + _FINGERPRINT_DEADLINE_SECONDS
    digest = hashlib.sha256(b"tsa-index-sqlite-v2\0")
    _frame(digest, b"root", root.encode("utf-8", "surrogatepass"))
    inventory = [
        (str(row[0]), str(row[1] or ""))
        for row in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
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
        encoded_rows: list[bytes] = []
        for row in conn.execute(f'SELECT * FROM "{table}"'):
            encoded = _typed(tuple(row))
            rows_seen += 1
            bytes_seen += len(encoded)
            if (
                rows_seen > _FINGERPRINT_ROW_BUDGET
                or bytes_seen > _FINGERPRINT_BYTE_BUDGET
            ):
                raise RuntimeError("INDEX_FINGERPRINT_BUDGET")
            _check_deadline(deadline)
            encoded_rows.append(encoded)
        for encoded in sorted(encoded_rows):
            _frame(digest, b"row", encoded)
    return "sha256:" + digest.hexdigest()


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
