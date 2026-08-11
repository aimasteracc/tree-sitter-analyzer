"""Authoritative, read-only capabilities for one coherent AST index snapshot."""

from __future__ import annotations

import atexit
import errno
import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from urllib.parse import quote

from .index_snapshot_capability import (
    exact_call_graph_marker as _exact_call_graph_marker,
)
from .index_snapshot_capability import (
    hierarchy_matches_pinned_database as _hierarchy_matches_pinned_database,
)
from .index_snapshot_capability import (
    open_bound_database as _open_bound_database,
)
from .index_snapshot_capability import (
    path_matches_pinned_database as _path_matches_pinned_database,
)
from .index_snapshot_capability import (
    physical_storage_identity as _physical_storage_identity,
)
from .index_snapshot_capability import (
    reject_sidecars as _reject_sidecars,
)
from .index_snapshot_capability import (
    require_memory_temp_store as _require_memory_temp_store,
)
from .index_snapshot_registry import IndexSnapshot, IndexSnapshotRegistry
from .index_snapshot_schema import (
    _deadline_ordered_rows,
    index_fingerprint,
    validate_snapshot_schema,
)
from .index_snapshot_schema import (
    stamp_full_index_manifest as stamp_full_index_manifest,
)
from .index_snapshot_schema import (
    validate_manifest_scalars as _validate_manifest_scalars,
)
from .index_snapshot_symbols import (
    fallback_symbol_counts as _fallback_symbol_counts,  # noqa: F401
)
from .index_snapshot_symbols import has_ordinary_symbol_projection
from .index_source_snapshot import (
    SOURCE_SCOPE_DESCRIPTOR_BYTE_BUDGET,
    capture_current_source_snapshot,
    parse_source_scope_descriptor,
    recorded_source_rows,
)
from .index_symbol_projection import (
    sqlite_compile_supports_fts5,
    symbol_projection_is_exact,
)

ACTION_VERSION = "index.status/v1"


def _close_pinned_descriptor(fd: int) -> None:
    """Module-local seam for independently closing one pinned handle."""
    os.close(fd)


_MAX_SNAPSHOTS = 16
_MAX_CHARGED_BYTES = 512 * 1024 * 1024
_TTL_SECONDS = 35.0
_SNAPSHOT_OVERHEAD_BYTES = 2 * 1024 * 1024
_CAPTURE_DEADLINE_SECONDS = 10.0
_BACKUP_BYTE_BUDGET = _MAX_CHARGED_BYTES - _SNAPSHOT_OVERHEAD_BYTES
_clock = time.monotonic


def _require_capture_budget(deadline: float) -> None:
    if _clock() >= deadline:
        raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")


def _capture_sources_with_deadline(
    root: str, source_scope: Any, deadline: float
) -> Any:
    """Keep pre-deadline two-argument test seams source-compatible."""
    try:
        return capture_current_source_snapshot(root, source_scope, deadline=deadline)
    except TypeError as exc:
        if "unexpected keyword argument 'deadline'" not in str(exc):
            raise
        return capture_current_source_snapshot(root, source_scope)


def _index_fingerprint_with_deadline(
    connection: sqlite3.Connection, root: str, deadline: float
) -> str:
    """Keep pre-deadline two-argument test seams source-compatible."""
    try:
        return index_fingerprint(connection, root, deadline=deadline)
    except TypeError as exc:
        if "unexpected keyword argument 'deadline'" not in str(exc):
            raise
        return index_fingerprint(connection, root)


REGISTRY = IndexSnapshotRegistry(
    clock=lambda: _clock(),
    max_snapshots=lambda: _MAX_SNAPSHOTS,
    max_charged_bytes=lambda: _MAX_CHARGED_BYTES,
    ttl_seconds=lambda: _TTL_SECONDS,
    capture_deadline_seconds=lambda: _CAPTURE_DEADLINE_SECONDS,
)
_CAPTURE_LOCK = threading.Lock()
atexit.register(REGISTRY.close_all)


_MANIFEST_TEXT_BYTE_BUDGET = 1024 * 1024
_MANIFEST_SCOPE_BYTE_BUDGET = SOURCE_SCOPE_DESCRIPTOR_BYTE_BUDGET
_MANIFEST_TOTAL_BYTE_BUDGET = 3 * 1024 * 1024


def _read_bounded_manifest(
    connection: sqlite3.Connection, deadline: float
) -> sqlite3.Row | None:
    """Preflight manifest cell sizes inside SQLite before decoding values."""
    columns = (
        "canonical_root",
        "source_fingerprint",
        "index_fingerprint",
        "file_count",
        "source_scope_descriptor",
        "manifest_version",
    )
    count_rows = _deadline_ordered_rows(
        connection,
        "SELECT COUNT(*) FROM ast_index_snapshot_manifest WHERE singleton=1",
        deadline,
    )
    count_row = next(count_rows, None)
    if (
        count_row is None
        or len(count_row) != 1
        or not isinstance(count_row[0], int)
        or next(count_rows, None) is not None
    ):
        raise ValueError("INDEX_MANIFEST_INVALID")
    if count_row[0] == 0:
        return None
    if count_row[0] != 1:
        raise ValueError("INDEX_MANIFEST_INVALID")

    length_query = (
        "SELECT "
        + ", ".join(f"length(CAST({column} AS BLOB))" for column in columns)
        + " FROM ast_index_snapshot_manifest WHERE singleton=1"
    )
    length_rows = _deadline_ordered_rows(connection, length_query, deadline)
    first_lengths = next(length_rows, None)
    if first_lengths is None or next(length_rows, None) is not None:
        raise ValueError("INDEX_MANIFEST_INVALID")
    lengths = tuple(0 if value is None else int(value) for value in first_lengths)
    per_cell = (
        _MANIFEST_TEXT_BYTE_BUDGET,
        _MANIFEST_TEXT_BYTE_BUDGET,
        _MANIFEST_TEXT_BYTE_BUDGET,
        _MANIFEST_TEXT_BYTE_BUDGET,
        _MANIFEST_SCOPE_BYTE_BUDGET,
        _MANIFEST_TEXT_BYTE_BUDGET,
    )
    if any(
        length < 0 or length > budget
        for length, budget in zip(lengths, per_cell, strict=True)
    ):
        raise ValueError("INDEX_MANIFEST_INVALID")
    if sum(lengths) > _MANIFEST_TOTAL_BYTE_BUDGET:
        raise ValueError("INDEX_MANIFEST_INVALID")
    query = (
        "SELECT "
        + ", ".join(columns)
        + (" FROM ast_index_snapshot_manifest WHERE singleton=1")
    )

    def expired() -> int:
        return int(_clock() >= deadline)

    connection.set_progress_handler(expired, 1_000)
    try:
        _require_capture_budget(deadline)
        cursor = connection.execute(query)
        fetchone = getattr(cursor, "fetchone", None)
        if callable(fetchone):
            manifest = fetchone()
            duplicate = fetchone()
        else:
            rows = iter(cursor)
            manifest = next(rows, None)
            duplicate = next(rows, None)
        _require_capture_budget(deadline)
    finally:
        connection.set_progress_handler(None, 0)
    if manifest is None or duplicate is not None:
        raise ValueError("INDEX_MANIFEST_INVALID")
    return cast(sqlite3.Row, manifest)


def _capture_existing_snapshot(
    project_root: str, *, pin: bool = False
) -> IndexSnapshot:
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
    deadline = _clock() + _CAPTURE_DEADLINE_SECONDS
    if not _CAPTURE_LOCK.acquire(timeout=max(0.0, deadline - _clock())):
        return _unknown("INDEX_SNAPSHOT_DEADLINE")
    try:
        try:
            root, root_fd, cache_fd, db_fd = _open_bound_database(project_root)
            handles = (root_fd, cache_fd, db_fd)
            initial = os.fstat(db_fd)
            if initial.st_size + _SNAPSHOT_OVERHEAD_BYTES > _MAX_CHARGED_BYTES:
                raise RuntimeError("INDEX_SNAPSHOT_CAPACITY")
            _reject_sidecars(cache_fd)
            uri = f"file:{quote('/dev/fd/' + str(db_fd), safe='/')}?mode=ro&immutable=1"
            connection = sqlite3.connect(
                uri, uri=True, timeout=0, isolation_level=None, check_same_thread=False
            )
            _require_memory_temp_store(connection)
            if not _path_matches_pinned_database(cache_fd, db_fd):
                raise ValueError("CONCURRENT_WRITER")
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA busy_timeout=0")
            source_page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
            source_page_count = int(
                connection.execute("PRAGMA page_count").fetchone()[0]
            )
            source_bytes = source_page_size * source_page_count
            if source_bytes > _BACKUP_BYTE_BUDGET:
                raise RuntimeError("INDEX_BACKUP_BUDGET")
            REGISTRY.ensure_capacity(source_bytes + _SNAPSHOT_OVERHEAD_BYTES)
            _require_capture_budget(deadline)
            validate_snapshot_schema(connection, deadline=deadline)
            from .cache.build_state import build_in_progress

            if build_in_progress(connection):
                raise ValueError("CONCURRENT_WRITER")
            _require_capture_budget(deadline)
            index = _index_fingerprint_with_deadline(connection, root, deadline)
            _require_capture_budget(deadline)
            recorded = recorded_source_rows(connection, deadline=deadline)
            _require_capture_budget(deadline)
            manifest = _read_bounded_manifest(connection, deadline)
            if manifest is not None:
                _validate_manifest_scalars(manifest)
            current = None
            source_scope = None
            scope_reason = None
            if manifest is None:
                scope_reason = "SOURCE_SCOPE_DESCRIPTOR_MISSING"
            else:
                try:
                    source_scope = parse_source_scope_descriptor(
                        manifest["source_scope_descriptor"]
                    )
                except (TypeError, ValueError):
                    scope_reason = "SOURCE_SCOPE_DESCRIPTOR_INVALID"
                else:
                    _require_capture_budget(deadline)
                    current = _capture_sources_with_deadline(
                        root, source_scope, deadline
                    )
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
                and manifest["file_count"] == count
                and manifest["manifest_version"] == 2
            )
            _require_capture_budget(deadline)
            call_graph_complete = _exact_call_graph_marker(
                connection, deadline=deadline
            )
            complete = exact_sources and exact_manifest and call_graph_complete
            if complete:
                reason = None
            elif not call_graph_complete:
                reason = "CALL_GRAPH_INCOMPLETE"
            elif scope_reason is not None:
                reason = scope_reason
            elif not exact_sources:
                reason = (
                    current.reason or "SOURCE_INDEX_MISMATCH"
                    if current
                    else "SOURCE_INDEX_MISMATCH"
                )
            else:
                reason = "NO_EXACT_FULL_INDEX_MANIFEST"
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
            _require_memory_temp_store(evidence)
            _require_capture_budget(deadline)
            copied_pages = 0
            max_backup_pages = (
                _BACKUP_BYTE_BUDGET + source_page_size - 1
            ) // source_page_size

            def progress(_status: int, remaining: int, total: int) -> None:
                nonlocal copied_pages
                copied_pages = total - remaining
                copied_bytes = copied_pages * source_page_size
                if (
                    copied_pages > max_backup_pages
                    or copied_bytes > _BACKUP_BYTE_BUDGET
                    or _clock() > deadline
                ):
                    raise RuntimeError(
                        "INDEX_SNAPSHOT_DEADLINE"
                        if _clock() > deadline
                        else "INDEX_BACKUP_BUDGET"
                    )

            connection.backup(evidence, pages=64, progress=progress, sleep=0)
            # FTS5's rank=1 integrity control command is a transactional write.
            # Run it exactly once on the private in-memory evidence copy while it
            # is still writable, then cache the result on the capability before
            # query_only is enabled. The immutable workspace source is never used.
            evidence_tables = {
                str(row[0])
                for row in evidence.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            evidence_fts5 = sqlite_compile_supports_fts5(evidence)
            projection_exact = bool(
                evidence_fts5 is not None
                and has_ordinary_symbol_projection(evidence, evidence_tables)
                and symbol_projection_is_exact(
                    evidence, deadline=deadline, require_fts=evidence_fts5
                )
            )
            if source_scope is not None and current is not None:
                _require_capture_budget(deadline)
                final_current = _capture_sources_with_deadline(
                    root, source_scope, deadline
                )
                if final_current.state != "exact":
                    raise ValueError(final_current.reason or "SOURCE_INDEX_MISMATCH")
                if (
                    current.state != "exact"
                    or final_current.rows != current.rows
                    or final_current.fingerprint != current.fingerprint
                ):
                    raise ValueError("CONCURRENT_SOURCE")
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
            snapshot = IndexSnapshot(
                snapshot.snapshot_id,
                snapshot.source_fingerprint,
                snapshot.index_fingerprint,
                snapshot.source_generation,
                snapshot.completeness,
                snapshot.reason,
                snapshot.canonical_root,
                snapshot.file_count,
                _physical_storage_identity(evidence),
                projection_exact,
            )
            _require_capture_budget(deadline)
            if not _hierarchy_matches_pinned_database(root, root_fd, cache_fd, db_fd):
                raise ValueError("CONCURRENT_WRITER")
            published = REGISTRY.publish(snapshot, evidence, charged, deadline, pin=pin)
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
        except (OSError, TimeoutError, TypeError, ValueError, RuntimeError) as exc:
            reason = "INDEX_SNAPSHOT_DEADLINE" if _clock() >= deadline else str(exc)
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
                    try:
                        _close_pinned_descriptor(fd)
                    except OSError:
                        # Every pinned descriptor owns an independent resource;
                        # one cleanup failure must not leak the remaining chain or
                        # replace the already-determined snapshot classification.
                        pass
    finally:
        _CAPTURE_LOCK.release()


def read_existing_snapshot(project_root: str) -> IndexSnapshot:
    """Capture a legacy unpinned capability for direct graph-reader clients."""
    return _capture_existing_snapshot(project_root)


@contextmanager
def lease_existing_snapshot(project_root: str) -> Iterator[IndexSnapshot]:
    """Keep a successfully published capability pinned until response assembly."""
    snapshot = _capture_existing_snapshot(project_root, pin=True)
    try:
        yield snapshot
    finally:
        if snapshot.snapshot_id is not None:
            REGISTRY.release_pin(snapshot.snapshot_id)


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
    from .index_snapshot_stats import collect_snapshot_stats

    try:
        deadline = REGISTRY.capture_deadline(snapshot_id)
        projection_exact = REGISTRY.symbol_projection_exact(snapshot_id)
    except ValueError:
        # Lightweight reader seams can supply their own connection without the
        # production registry; production-issued IDs always take the first path.
        deadline = _clock() + _CAPTURE_DEADLINE_SECONDS
        projection_exact = None
    _require_capture_budget(deadline)
    return run_graph_snapshot_read(
        snapshot_id,
        project_root,
        source_generation,
        lambda conn: collect_snapshot_stats(
            conn, deadline=deadline, projection_exact=projection_exact
        ),
    )


def acquire_index_snapshot(
    snapshot_id: str, project_root: str, source_generation: str | None = None
) -> Any:
    return REGISTRY.acquire(snapshot_id, project_root, source_generation)


def _unknown(reason: str) -> IndexSnapshot:
    return IndexSnapshot(None, None, None, None, "unknown", reason, None, 0)
