"""Schema ownership and canonical fingerprints for index snapshots."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from typing import Any

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
_SOURCE_COLUMNS = ("file_path", "content_hash", "language", "extractor_version")
_INDEX_TABLE_EXCLUDES = {
    "ast_schema_version": frozenset({"applied_at"}),
    "ast_index": frozenset({"indexed_at", "mtime_ns"}),
    "ast_symbol_activation": frozenset({"computed_at"}),
    "ast_constraint_violations": frozenset({"detected_at"}),
}
_INDEX_TABLES = (
    "ast_schema_version",
    "ast_index",
    "ast_symbol_rows",
    "ast_imports",
    "edges",
    "ast_symbol_activation",
    "ast_constraint_violations",
)
_REQUIRED_COLUMNS = {
    "ast_index": frozenset(
        (*_SOURCE_COLUMNS, "symbols_json", "imports_json", "structure_json")
    ),
    "ast_symbol_rows": frozenset(
        {"name", "kind", "file_path", "language", "line", "end_line"}
    ),
    "ast_imports": frozenset({"file_path", "language", "module_path", "local_name"}),
    "edges": frozenset(
        {
            "source_node_id",
            "target_node_id",
            "kind",
            "line",
            "provenance",
            "metadata",
            "caller_name",
            "callee_name",
            "file_path",
            "caller_line",
            "callee_full",
            "callee_line",
            "language",
            "callee_resolution",
            "callee_resolved_file",
            "callee_symbol_id",
        }
    ),
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
    """Atomically certify the exact canonical rows produced by a full index."""
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
        version > SNAPSHOT_SCHEMA_VERSION for version in versions
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


def _feed(hasher: Any, values: tuple[Any, ...]) -> None:
    for value in values:
        raw = ("<null>" if value is None else str(value)).encode(
            "utf-8", "surrogatepass"
        )
        hasher.update(len(raw).to_bytes(8, "big"))
        hasher.update(raw)


def source_fingerprint(conn: sqlite3.Connection, _root: str) -> str:
    """Hash only index-owned source inventory and recorded content hashes."""
    hasher = hashlib.sha256(b"tsa-index-source-v1\0")
    sql = "SELECT " + ", ".join(_SOURCE_COLUMNS) + " FROM ast_index ORDER BY file_path"
    for row in conn.execute(sql):
        _feed(hasher, tuple(row))
    return "sha256:" + hasher.hexdigest()


def index_fingerprint(conn: sqlite3.Connection, root: str) -> str:
    hasher = hashlib.sha256(b"tsa-index-rows-v1\0")
    _feed(hasher, (root,))
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for table in _INDEX_TABLES:
        if table not in tables:
            continue
        excluded = _INDEX_TABLE_EXCLUDES.get(table, frozenset({"id"}))
        columns = [
            str(row[1])
            for row in conn.execute(f'PRAGMA table_info("{table}")')
            if str(row[1]) not in excluded and str(row[1]) != "id"
        ]
        if not columns:
            continue
        quoted = ", ".join(f'"{column}"' for column in columns)
        _feed(hasher, (table, *columns))
        for row in conn.execute(f'SELECT {quoted} FROM "{table}" ORDER BY {quoted}'):
            _feed(hasher, tuple(row))
    return "sha256:" + hasher.hexdigest()
