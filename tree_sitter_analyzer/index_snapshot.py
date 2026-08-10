"""Authoritative, read-only capabilities for one coherent AST index snapshot."""

from __future__ import annotations

import atexit
import os
import secrets
import sqlite3
import stat
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from .index_snapshot_schema import (
    SNAPSHOT_SCHEMA_VERSION,
    index_fingerprint,
    source_fingerprint,
    validate_snapshot_schema,
)
from .index_snapshot_schema import (
    stamp_full_index_manifest as stamp_full_index_manifest,
)

ACTION_VERSION = "index.status/v1"
_MAX_SNAPSHOTS = 16
_MAX_CHARGED_BYTES = 512 * 1024 * 1024
_TTL_SECONDS = 35.0
_SNAPSHOT_OVERHEAD_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class IndexSnapshot:
    snapshot_id: str | None
    source_fingerprint: str | None
    index_fingerprint: str | None
    source_generation: str | None
    completeness: Literal["complete", "partial", "unknown"]
    reason: str | None
    canonical_root: str | None
    file_count: int


@dataclass(slots=True)
class _Entry:
    snapshot: IndexSnapshot
    connection: sqlite3.Connection
    charged_bytes: int
    expires_at: float
    readers: int = 0
    io_lock: Any = field(default_factory=threading.RLock)


class IndexSnapshotRegistry:
    """Bounded process-local owner of SQLite read-transaction capabilities."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, _Entry] = {}

    def ensure_capacity(self, charged_bytes: int) -> None:
        """Fail before materialization when retained immutable bytes would overflow."""
        with self._lock:
            self._purge(time.monotonic())
            live_bytes = sum(entry.charged_bytes for entry in self._entries.values())
            if (
                len(self._entries) >= _MAX_SNAPSHOTS
                or charged_bytes > _MAX_CHARGED_BYTES
                or live_bytes + charged_bytes > _MAX_CHARGED_BYTES
            ):
                raise RuntimeError("INDEX_SNAPSHOT_CAPACITY")

    def publish(
        self,
        snapshot: IndexSnapshot,
        connection: sqlite3.Connection,
        charged_bytes: int,
    ) -> IndexSnapshot:
        with self._lock:
            self.ensure_capacity(charged_bytes)
            snapshot_id = "idxsnap_" + secrets.token_urlsafe(24)
            published = IndexSnapshot(
                snapshot_id=snapshot_id,
                source_fingerprint=snapshot.source_fingerprint,
                index_fingerprint=snapshot.index_fingerprint,
                source_generation=snapshot.source_generation,
                completeness=snapshot.completeness,
                reason=snapshot.reason,
                canonical_root=snapshot.canonical_root,
                file_count=snapshot.file_count,
            )
            self._entries[snapshot_id] = _Entry(
                published, connection, charged_bytes, time.monotonic() + _TTL_SECONDS
            )
            return published

    @contextmanager
    def acquire(
        self,
        snapshot_id: str,
        project_root: str,
        source_generation: str | None = None,
    ) -> Iterator[tuple[IndexSnapshot, sqlite3.Connection]]:
        canonical_root = os.path.realpath(os.path.abspath(project_root))
        with self._lock:
            now = time.monotonic()
            self._purge(now)
            entry = self._entries.get(snapshot_id)
            if entry is None or entry.expires_at <= now:
                raise ValueError("INDEX_SNAPSHOT_UNKNOWN")
            if entry.snapshot.canonical_root != canonical_root:
                raise ValueError("INDEX_SNAPSHOT_ROOT_MISMATCH")
            if (
                source_generation is not None
                and source_generation != entry.snapshot.source_generation
            ):
                raise ValueError("SOURCE_GENERATION_MISMATCH")
            entry.readers += 1
        entry.io_lock.acquire()
        try:
            yield entry.snapshot, entry.connection
        finally:
            entry.io_lock.release()
            with self._lock:
                entry.readers -= 1
                self._purge(time.monotonic())

    def close_all(self) -> None:
        with self._lock:
            entries = tuple(self._entries.values())
            self._entries.clear()
        for entry in entries:
            entry.connection.close()

    def _purge(self, now: float) -> None:
        expired = [
            key
            for key, entry in self._entries.items()
            if entry.expires_at <= now and entry.readers == 0
        ]
        for key in expired:
            entry = self._entries.pop(key)
            entry.connection.close()


REGISTRY = IndexSnapshotRegistry()
_CAPTURE_LOCK = threading.Lock()
atexit.register(REGISTRY.close_all)


def read_existing_snapshot(project_root: str) -> IndexSnapshot:
    """Open an existing DB read-only and publish its coherent read transaction."""
    connection: sqlite3.Connection | None = None
    _CAPTURE_LOCK.acquire()
    try:
        root, db_path = _bound_db_path(project_root)
        charged = _snapshot_charge(db_path)
        REGISTRY.ensure_capacity(charged + _SNAPSHOT_OVERHEAD_BYTES)
        uri = f"file:{quote(db_path)}?mode=ro"
        connection = sqlite3.connect(
            uri, uri=True, timeout=0, isolation_level=None, check_same_thread=False
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=0")
        connection.execute("BEGIN")
        validate_snapshot_schema(connection)
        from .cache.build_state import build_in_progress

        if build_in_progress(connection):
            raise ValueError("CONCURRENT_WRITER")
        source = source_fingerprint(connection, root)
        index = index_fingerprint(connection, root)
        row = connection.execute(
            "SELECT canonical_root, source_fingerprint, index_fingerprint, "
            "file_count, manifest_version FROM ast_index_snapshot_manifest "
            "WHERE singleton=1"
        ).fetchone()
        count = int(connection.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0])
        complete = bool(
            row
            and row["canonical_root"] == root
            and row["source_fingerprint"] == source
            and row["index_fingerprint"] == index
            and int(row["file_count"]) == count
            and int(row["manifest_version"]) == 1
            and count > 0
        )
        snapshot = IndexSnapshot(
            snapshot_id=None,
            source_fingerprint=source,
            index_fingerprint=index,
            source_generation="idxsrc-v1:" + source.removeprefix("sha256:"),
            completeness="complete" if complete else "partial",
            reason=None if complete else "NO_EXACT_FULL_INDEX_MANIFEST",
            canonical_root=root,
            file_count=count,
        )
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        materialized_bytes = page_size * page_count
        REGISTRY.ensure_capacity(materialized_bytes + _SNAPSHOT_OVERHEAD_BYTES)
        evidence_connection = sqlite3.connect(":memory:", check_same_thread=False)
        connection.backup(evidence_connection)
        connection.close()
        connection = evidence_connection
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA cache_size=-2048")
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        return REGISTRY.publish(
            snapshot, connection, materialized_bytes + _SNAPSHOT_OVERHEAD_BYTES
        )
    except FileNotFoundError as exc:
        if connection is not None:
            connection.close()
        return _unknown(str(exc))
    except sqlite3.DatabaseError as exc:
        if connection is not None:
            connection.close()
        text = str(exc).lower()
        reason = (
            "CONCURRENT_WRITER"
            if "locked" in text or "busy" in text
            else "CORRUPT_INDEX"
        )
        return _unknown(reason)
    except (ValueError, RuntimeError) as exc:
        if connection is not None:
            connection.close()
        return _unknown(str(exc))
    finally:
        _CAPTURE_LOCK.release()


def run_graph_snapshot_read(
    snapshot_id: str,
    project_root: str,
    source_generation: str,
    reader: Any,
) -> dict[str, Any]:
    """Run a graph read on the certified transaction and echo actual tokens."""
    with acquire_index_snapshot(snapshot_id, project_root, source_generation) as (
        snapshot,
        conn,
    ):
        payload = reader(conn)
        if not isinstance(payload, dict):
            raise TypeError("graph snapshot reader must return a mapping")
        result = dict(payload)
        result["snapshot_id"] = snapshot.snapshot_id
        result["source_generation"] = snapshot.source_generation
        return result


def read_snapshot_stats(snapshot_id: str, project_root: str) -> dict[str, Any]:
    """Return status counters from the exact transaction named by a capability."""
    with acquire_index_snapshot(snapshot_id, project_root) as (_, conn):
        total_files = int(conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0])
        total_symbols = int(
            conn.execute("SELECT COUNT(*) FROM ast_symbol_rows").fetchone()[0]
        )
        total_edges = int(conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0])
        symbols_by_kind = {
            str(row[0]): int(row[1])
            for row in conn.execute(
                "SELECT kind, COUNT(*) FROM ast_symbol_rows GROUP BY kind ORDER BY kind"
            )
        }
        symbols_by_language = {
            str(row[0]): int(row[1])
            for row in conn.execute(
                "SELECT language, COUNT(*) FROM ast_symbol_rows GROUP BY language ORDER BY language"
            )
        }
        edges_by_kind = {
            str(row[0]): int(row[1])
            for row in conn.execute(
                "SELECT kind, COUNT(*) FROM edges GROUP BY kind ORDER BY kind"
            )
        }
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        free_pages = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        return {
            "total_files": total_files,
            "total_symbols": total_symbols,
            "total_edges": total_edges,
            "symbols_by_kind": symbols_by_kind,
            "symbols_by_language": symbols_by_language,
            "edges_by_kind": edges_by_kind,
            "fts5_available": "ast_symbols_fts"
            in {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            },
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "db_page_size": page_size,
            "db_page_count": page_count,
            "db_free_pages": free_pages,
            "db_free_bytes": free_pages * page_size,
        }


def acquire_index_snapshot(
    snapshot_id: str, project_root: str, source_generation: str | None = None
) -> Any:
    """Acquire only an owner-issued capability; arbitrary IDs are never trusted."""
    return REGISTRY.acquire(snapshot_id, project_root, source_generation)


def _unknown(reason: str) -> IndexSnapshot:
    return IndexSnapshot(None, None, None, None, "unknown", reason, None, 0)


def _bound_db_path(project_root: str) -> tuple[str, str]:
    logical = os.path.abspath(project_root)
    if not os.path.isdir(logical):
        raise FileNotFoundError("MISSING_PROJECT_ROOT")
    root = os.path.realpath(logical)
    db_path = os.path.join(logical, ".ast-cache", "index.db")
    if not os.path.exists(db_path):
        raise FileNotFoundError("MISSING_INDEX")
    current = logical
    for component in (".ast-cache", "index.db"):
        current = os.path.join(current, component)
        mode = os.lstat(current).st_mode
        if stat.S_ISLNK(mode):
            raise ValueError("INDEX_PATH_SYMLINK")
    resolved_db = os.path.realpath(db_path)
    if not Path(resolved_db).is_relative_to(root) or not stat.S_ISREG(
        os.stat(db_path).st_mode
    ):
        raise ValueError("INDEX_PATH_OUTSIDE_ROOT")
    return root, resolved_db


def _snapshot_charge(db_path: str) -> int:
    total = os.path.getsize(db_path)
    for suffix in ("-wal", "-shm"):
        try:
            total += os.path.getsize(db_path + suffix)
        except OSError:
            pass
    return total
