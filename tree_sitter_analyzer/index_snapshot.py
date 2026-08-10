"""Authoritative, read-only capabilities for one coherent AST index snapshot."""

from __future__ import annotations

import atexit
import errno
import json
import os
import secrets
import sqlite3
import stat
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal, cast
from urllib.parse import quote

from .index_snapshot_registry import ensure_capacity as ensure_registry_capacity
from .index_snapshot_registry import reuse_snapshot
from .index_snapshot_schema import (
    SNAPSHOT_SCHEMA_VERSION,
    index_fingerprint,
    validate_snapshot_schema,
)
from .index_snapshot_schema import (
    stamp_full_index_manifest as stamp_full_index_manifest,
)
from .index_source_snapshot import (
    capture_current_source_snapshot,
    parse_source_scope_descriptor,
    recorded_source_rows,
)

ACTION_VERSION = "index.status/v1"
_MAX_SNAPSHOTS = 16
_MAX_CHARGED_BYTES = 512 * 1024 * 1024
_TTL_SECONDS = 35.0
_SNAPSHOT_OVERHEAD_BYTES = 2 * 1024 * 1024
_CAPTURE_DEADLINE_SECONDS = 10.0
_BACKUP_PAGE_BUDGET = 131_072
_SYMBOL_FALLBACK_BYTE_BUDGET = 512 * 1024 * 1024
_SYMBOL_FALLBACK_ROW_BUDGET = 2_000_000
_clock = time.monotonic


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
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, _Entry] = {}

    def ensure_capacity(self, charged_bytes: int) -> None:
        with self._lock:
            self._purge(_clock())
            ensure_registry_capacity(
                self._entries, charged_bytes, _MAX_SNAPSHOTS, _MAX_CHARGED_BYTES
            )

    def publish(
        self,
        snapshot: IndexSnapshot,
        connection: sqlite3.Connection,
        charged_bytes: int,
    ) -> IndexSnapshot:
        with self._lock:
            now = _clock()
            self._purge(now)
            existing = reuse_snapshot(
                self._entries, snapshot, connection, now + _TTL_SECONDS
            )
            if existing is not None:
                return cast(IndexSnapshot, existing)
            self.ensure_capacity(charged_bytes)
            snapshot_id = "idxsnap_" + secrets.token_urlsafe(24)
            published = IndexSnapshot(
                snapshot_id,
                snapshot.source_fingerprint,
                snapshot.index_fingerprint,
                snapshot.source_generation,
                snapshot.completeness,
                snapshot.reason,
                snapshot.canonical_root,
                snapshot.file_count,
            )
            self._entries[snapshot_id] = _Entry(
                published, connection, charged_bytes, _clock() + _TTL_SECONDS
            )
            return published

    @contextmanager
    def acquire(
        self, snapshot_id: str, project_root: str, source_generation: str | None = None
    ) -> Iterator[tuple[IndexSnapshot, sqlite3.Connection]]:
        canonical_root = os.path.realpath(os.path.abspath(project_root))
        with self._lock:
            now = _clock()
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
                self._purge(_clock())

    def close_all(self) -> None:
        with self._lock:
            entries = tuple(self._entries.values())
            self._entries.clear()
        for entry in entries:
            entry.connection.close()

    def _purge(self, now: float) -> None:
        for key in [
            k
            for k, v in self._entries.items()
            if v.expires_at <= now and v.readers == 0
        ]:
            self._entries.pop(key).connection.close()


REGISTRY = IndexSnapshotRegistry()
_CAPTURE_LOCK = threading.Lock()
atexit.register(REGISTRY.close_all)


def read_existing_snapshot(project_root: str) -> IndexSnapshot:
    # Absence is platform-independent and publishes no file evidence.  Report it
    # before the secure-fd capability gate so fresh Windows installs preserve the
    # established missing-index contract; an existing database still fails closed.
    candidate = os.path.join(os.path.realpath(project_root), ".ast-cache", "index.db")
    if not os.path.lexists(candidate):
        return _unknown("MISSING_INDEX")
    if os.name != "posix" or not os.path.exists("/dev/fd"):
        return _unknown("SECURE_FD_SNAPSHOT_UNSUPPORTED")
    handles: tuple[int, int, int] | None = None
    connection: sqlite3.Connection | None = None
    evidence: sqlite3.Connection | None = None
    with _CAPTURE_LOCK:
        try:
            root, root_fd, cache_fd, db_fd = _open_bound_database(project_root)
            handles = (root_fd, cache_fd, db_fd)
            initial = os.fstat(db_fd)
            if initial.st_size + _SNAPSHOT_OVERHEAD_BYTES > _MAX_CHARGED_BYTES:
                raise RuntimeError("INDEX_SNAPSHOT_CAPACITY")
            _reject_sidecars(cache_fd)
            REGISTRY.ensure_capacity(initial.st_size + _SNAPSHOT_OVERHEAD_BYTES)
            uri = f"file:{quote('/dev/fd/' + str(db_fd), safe='/')}?mode=ro&immutable=1"
            connection = sqlite3.connect(
                uri, uri=True, timeout=0, isolation_level=None, check_same_thread=False
            )
            if not _path_matches_pinned_database(cache_fd, db_fd):
                raise ValueError("CONCURRENT_WRITER")
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA busy_timeout=0")
            validate_snapshot_schema(connection)
            from .cache.build_state import build_in_progress

            if build_in_progress(connection):
                raise ValueError("CONCURRENT_WRITER")
            index = index_fingerprint(connection, root)
            recorded = recorded_source_rows(connection)
            manifest = connection.execute(
                "SELECT canonical_root, source_fingerprint, index_fingerprint, "
                "file_count, source_scope_descriptor, manifest_version "
                "FROM ast_index_snapshot_manifest WHERE singleton=1"
            ).fetchone()
            current = None
            scope_reason = None
            if manifest is None:
                scope_reason = "SOURCE_SCOPE_DESCRIPTOR_MISSING"
            else:
                try:
                    source_scope = parse_source_scope_descriptor(
                        str(manifest["source_scope_descriptor"])
                    )
                except (TypeError, ValueError):
                    scope_reason = "SOURCE_SCOPE_DESCRIPTOR_INVALID"
                else:
                    current = capture_current_source_snapshot(root, source_scope)
                    if current.state == "unknown":
                        raise ValueError(current.reason or "SOURCE_SCOPE_UNKNOWN")
            count = len(recorded)
            exact_sources = bool(
                current and current.state == "exact" and recorded == current.rows
            )
            exact_manifest = bool(
                manifest
                and current
                and manifest["canonical_root"] == root
                and manifest["source_fingerprint"] == current.fingerprint
                and manifest["index_fingerprint"] == index
                and int(manifest["file_count"]) == count
                and int(manifest["manifest_version"]) == 2
            )
            complete = exact_sources and exact_manifest
            reason = None if complete else scope_reason
            if reason is None:
                reason = (
                    current.reason or "SOURCE_INDEX_MISMATCH"
                    if not exact_sources and current
                    else "NO_EXACT_FULL_INDEX_MANIFEST"
                )
            snapshot = IndexSnapshot(
                None,
                current.fingerprint if current else None,
                index,
                current.generation if current else None,
                "complete" if complete else "partial",
                reason,
                root,
                count,
            )
            evidence = sqlite3.connect(":memory:", check_same_thread=False)
            deadline = _clock() + _CAPTURE_DEADLINE_SECONDS
            copied_pages = 0

            def progress(_status: int, remaining: int, total: int) -> None:
                nonlocal copied_pages
                copied_pages = total - remaining
                if copied_pages > _BACKUP_PAGE_BUDGET or _clock() > deadline:
                    raise RuntimeError("INDEX_BACKUP_BUDGET")

            connection.backup(evidence, pages=64, progress=progress, sleep=0)
            _reject_sidecars(cache_fd)
            final = os.fstat(db_fd)
            if (
                initial.st_dev,
                initial.st_ino,
                initial.st_size,
                initial.st_mtime_ns,
                initial.st_ctime_ns,
            ) != (
                final.st_dev,
                final.st_ino,
                final.st_size,
                final.st_mtime_ns,
                final.st_ctime_ns,
            ) or not _path_matches_pinned_database(cache_fd, db_fd):
                raise ValueError("CONCURRENT_WRITER")
            connection.close()
            connection = None
            evidence.row_factory = sqlite3.Row
            evidence.execute("PRAGMA query_only=ON")
            evidence.execute("BEGIN")
            charged = (
                int(evidence.execute("PRAGMA page_size").fetchone()[0])
                * int(evidence.execute("PRAGMA page_count").fetchone()[0])
                + _SNAPSHOT_OVERHEAD_BYTES
            )
            published = REGISTRY.publish(snapshot, evidence, charged)
            evidence = None
            return published
        except FileNotFoundError as exc:
            return _unknown(str(exc))
        except sqlite3.DatabaseError as exc:
            path_changed = bool(
                handles and not _path_matches_pinned_database(handles[1], handles[2])
            )
            return _unknown(
                "CONCURRENT_WRITER"
                if path_changed
                or any(x in str(exc).lower() for x in ("locked", "busy"))
                else "CORRUPT_INDEX"
            )
        except (OSError, ValueError, RuntimeError) as exc:
            reason = str(exc)
            if isinstance(exc, OSError) and getattr(exc, "errno", None) in (
                errno.ELOOP,
                errno.ENOTDIR,
            ):
                reason = "INDEX_PATH_SYMLINK"
            return _unknown(reason or "INDEX_SNAPSHOT_FAILED")
        finally:
            if connection is not None:
                connection.close()
            if evidence is not None:
                evidence.close()
            if handles is not None:
                for fd in reversed(handles):
                    os.close(fd)


def run_graph_snapshot_read(
    snapshot_id: str, project_root: str, source_generation: str | None, reader: Any
) -> dict[str, Any]:
    with acquire_index_snapshot(snapshot_id, project_root, source_generation) as (
        snapshot,
        conn,
    ):
        payload = reader(conn)
        if not isinstance(payload, dict):
            raise TypeError("graph snapshot reader must return a mapping")
        result = dict(payload)
        result.update(
            snapshot_id=snapshot.snapshot_id,
            source_generation=snapshot.source_generation,
            source_fingerprint=snapshot.source_fingerprint,
            index_fingerprint=snapshot.index_fingerprint,
        )
        return result


def read_snapshot_stats(
    snapshot_id: str, project_root: str, source_generation: str | None
) -> dict[str, Any]:
    """Read status graph statistics through the production capability seam."""

    def reader(conn: sqlite3.Connection) -> dict[str, Any]:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        free_pages = int(conn.execute("PRAGMA freelist_count").fetchone()[0])

        def grouped(sql: str) -> dict[str, int]:
            return {str(row[0]): int(row[1]) for row in conn.execute(sql)}

        fts5_available = {
            "ast_symbols_fts",
            "ast_symbol_rows",
        }.issubset(tables)
        if fts5_available:
            total_symbols = int(
                conn.execute("SELECT COUNT(*) FROM ast_symbol_rows").fetchone()[0]
            )
            symbols_by_kind = grouped(
                "SELECT kind, COUNT(*) FROM ast_symbol_rows GROUP BY kind ORDER BY kind"
            )
            symbols_by_language = grouped(
                "SELECT language, COUNT(*) FROM ast_symbol_rows "
                "GROUP BY language ORDER BY language"
            )
        else:
            total_symbols, symbols_by_kind, symbols_by_language = (
                _fallback_symbol_counts(conn)
            )

        return {
            "total_files": int(
                conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
            ),
            "total_symbols": total_symbols,
            "total_edges": int(
                conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            ),
            "symbols_by_kind": symbols_by_kind,
            "symbols_by_language": symbols_by_language,
            "edges_by_kind": grouped(
                "SELECT kind, COUNT(*) FROM edges GROUP BY kind ORDER BY kind"
            ),
            "fts5_available": fts5_available,
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "db_size_bytes": page_size * page_count,
            "db_page_size": page_size,
            "db_page_count": page_count,
            "db_free_pages": free_pages,
            "db_free_bytes": free_pages * page_size,
            "db_auto_vacuum_mode": int(
                conn.execute("PRAGMA auto_vacuum").fetchone()[0]
            ),
        }

    return run_graph_snapshot_read(snapshot_id, project_root, source_generation, reader)


def _fallback_symbol_counts(
    conn: sqlite3.Connection,
) -> tuple[int, dict[str, int], dict[str, int]]:
    """Count legacy/no-FTS symbols from bounded primary index JSON rows."""
    total = bytes_seen = 0
    by_kind: dict[str, int] = {}
    by_language: dict[str, int] = {}
    for row in conn.execute(
        "SELECT symbols_json, language FROM ast_index ORDER BY file_path"
    ):
        raw = str(row[0])
        bytes_seen += len(raw.encode("utf-8", "surrogatepass"))
        if bytes_seen > _SYMBOL_FALLBACK_BYTE_BUDGET:
            raise RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET")
        payload = json.loads(raw)
        symbols = payload.get("symbols", []) if isinstance(payload, dict) else []
        if not isinstance(symbols, list):
            raise ValueError("CORRUPT_INDEX")
        language = str(row[1])
        for symbol in symbols:
            total += 1
            if total > _SYMBOL_FALLBACK_ROW_BUDGET:
                raise RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET")
            kind = (
                str(symbol.get("kind", "unknown"))
                if isinstance(symbol, dict)
                else "unknown"
            )
            by_kind[kind] = by_kind.get(kind, 0) + 1
            by_language[language] = by_language.get(language, 0) + 1
    return total, dict(sorted(by_kind.items())), dict(sorted(by_language.items()))


def acquire_index_snapshot(
    snapshot_id: str, project_root: str, source_generation: str | None = None
) -> Any:
    return REGISTRY.acquire(snapshot_id, project_root, source_generation)


def _unknown(reason: str) -> IndexSnapshot:
    return IndexSnapshot(None, None, None, None, "unknown", reason, None, 0)


def _open_bound_database(project_root: str) -> tuple[str, int, int, int]:
    logical = os.path.abspath(project_root)
    if not os.path.isdir(logical):
        raise FileNotFoundError("MISSING_PROJECT_ROOT")
    root = os.path.realpath(logical)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    root_fd = os.open(root, flags)
    try:
        cache_fd = os.open(".ast-cache", flags | os.O_NOFOLLOW, dir_fd=root_fd)
    except FileNotFoundError:
        os.close(root_fd)
        raise FileNotFoundError("MISSING_INDEX") from None
    except Exception:
        os.close(root_fd)
        raise
    try:
        db_fd = os.open("index.db", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=cache_fd)
        if not stat.S_ISREG(os.fstat(db_fd).st_mode):
            os.close(db_fd)
            raise ValueError("INDEX_PATH_UNSAFE")
    except FileNotFoundError:
        os.close(cache_fd)
        os.close(root_fd)
        raise FileNotFoundError("MISSING_INDEX") from None
    except Exception:
        os.close(cache_fd)
        os.close(root_fd)
        raise
    return root, root_fd, cache_fd, db_fd


def _path_matches_pinned_database(cache_fd: int, db_fd: int) -> bool:
    """Return whether the cache path still names the securely pinned inode."""
    try:
        path_info = os.stat("index.db", dir_fd=cache_fd, follow_symlinks=False)
        pinned_info = os.fstat(db_fd)
    except OSError:
        return False
    return (path_info.st_dev, path_info.st_ino) == (
        pinned_info.st_dev,
        pinned_info.st_ino,
    )


def _reject_sidecars(cache_fd: int) -> None:
    for name in ("index.db-wal", "index.db-shm", "index.db-journal"):
        try:
            info = os.stat(name, dir_fd=cache_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_size:
            raise ValueError("CONCURRENT_WRITER")
