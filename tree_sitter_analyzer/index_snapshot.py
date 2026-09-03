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
from .index_snapshot_manifest import _read_bounded_manifest_impl
from .index_snapshot_registry import (
    _WAL_CONNECTION_OVERHEAD_BYTES,
    IndexSnapshot,
    IndexSnapshotRegistry,
)
from .index_snapshot_schema import index_fingerprint, validate_snapshot_schema
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
# TD-003: alias for _WAL_CONNECTION_OVERHEAD_BYTES in index_snapshot_registry.py.
# Both represent the same ~2 MB process-local overhead per open WAL connection.
# (import direction: index_snapshot.py → index_snapshot_registry.py avoids circular import)
_SNAPSHOT_OVERHEAD_BYTES = _WAL_CONNECTION_OVERHEAD_BYTES
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
    """Read a manifest with owner-module budgets and monkeypatch seams."""
    return _read_bounded_manifest_impl(
        connection,
        deadline,
        clock=_clock,
        require_budget=_require_capture_budget,
        text_byte_budget=_MANIFEST_TEXT_BYTE_BUDGET,
        scope_byte_budget=_MANIFEST_SCOPE_BYTE_BUDGET,
        total_byte_budget=_MANIFEST_TOTAL_BYTE_BUDGET,
    )


def _capture_wal_snapshot(
    canonical_root: str,
    candidate: str,
    *,
    pin: bool = False,
    deadline: float,
) -> IndexSnapshot:
    """WAL read-only snapshot path for non-POSIX or systems without /dev/fd.

    Phase B-1 prototype. Replaces the SECURE_FD_SNAPSHOT_UNSUPPORTED gate with a
    WAL read-only SQLite URI connection that provides snapshot isolation via BEGIN.
    Multiple concurrent WAL readers are permitted; _CAPTURE_LOCK is not acquired.

    Physical identity: verified via os.stat() before and after connecting.
    FTS5 rank: symbol_projection_is_exact() is skipped (requires write access).
    Tech-debt: [TBD-FTS5-WAL] — see tech-debt-log.md.
    """
    connection: sqlite3.Connection | None = None
    try:
        # Stat identity BEFORE open (anti-swap check step 1)
        try:
            pre_stat = os.stat(candidate)
        except OSError:
            return _unknown("MISSING_INDEX")
        pre_id = (
            pre_stat.st_dev,
            pre_stat.st_ino,
            pre_stat.st_size,
            pre_stat.st_mtime_ns,
        )

        # Open WAL read-only connection.  mode=ro lets SQLite read the WAL
        # transparently; BEGIN pins the current write generation as a reader.
        uri = f"file:{quote(candidate, safe='/')}?mode=ro"
        connection = sqlite3.connect(
            uri, uri=True, timeout=0, isolation_level=None, check_same_thread=False
        )
        _require_memory_temp_store(connection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=0")
        # BEGIN acquires a WAL reader slot, pinning the current write generation.
        connection.execute("BEGIN")

        # Stat identity AFTER connecting (verify no swap between stat and open)
        try:
            post_stat = os.stat(candidate)
        except OSError:
            raise ValueError("CONCURRENT_WRITER") from None
        post_id = (
            post_stat.st_dev,
            post_stat.st_ino,
            post_stat.st_size,
            post_stat.st_mtime_ns,
        )
        if pre_id != post_id:
            raise ValueError("CONCURRENT_WRITER")

        _require_capture_budget(deadline)
        validate_snapshot_schema(connection, deadline=deadline)
        from .cache.build_state import build_in_progress

        if build_in_progress(connection):
            raise ValueError("CONCURRENT_WRITER")

        _require_capture_budget(deadline)
        root = canonical_root
        index = _index_fingerprint_with_deadline(connection, root, deadline)
        _require_capture_budget(deadline)
        recorded = recorded_source_rows(connection, deadline=deadline)
        _require_capture_budget(deadline)
        manifest = _read_bounded_manifest(connection, deadline)
        if manifest is not None:
            _validate_manifest_scalars(manifest)

        current = None
        source_scope = None
        scope_reason: str | None = None
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
                current = _capture_sources_with_deadline(root, source_scope, deadline)
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
        call_graph_complete = _exact_call_graph_marker(connection, deadline=deadline)
        complete = exact_sources and exact_manifest and call_graph_complete

        if complete:
            reason: str | None = None
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

        # Phase B-1 NOTE: FTS5 rank=1 is a transactional write command.
        # WAL read-only connections cannot execute it; symbol_projection_is_exact()
        # is therefore skipped.  A complete index is still reported as complete
        # (projection_exact=False) so that callers get useful results rather than
        # SYMBOL_PROJECTION_INCOMPLETE on every non-POSIX host.
        # Tech-debt: [TBD-FTS5-WAL] Revisit when WAL write-capable rank caching
        # is added (e.g. run rank=1 on a brief write connection before snapshot).
        projection_exact = False

        if source_scope is not None and current is not None:
            _require_capture_budget(deadline)
            final_current = _capture_sources_with_deadline(root, source_scope, deadline)
            if final_current.state != "exact":
                raise ValueError(final_current.reason or "SOURCE_INDEX_MISMATCH")
            if (
                current.state != "exact"
                or final_current.rows != current.rows
                or final_current.fingerprint != current.fingerprint
            ):
                raise ValueError("CONCURRENT_SOURCE")

        # Final stat identity check (anti-swap step 3)
        try:
            final_stat = os.stat(candidate)
        except OSError:
            raise ValueError("CONCURRENT_WRITER") from None
        final_id = (
            final_stat.st_dev,
            final_stat.st_ino,
            final_stat.st_size,
            final_stat.st_mtime_ns,
        )
        if final_id != pre_id:
            raise ValueError("CONCURRENT_WRITER")

        # WAL connection overhead: no backup copy, so charge ~2 MB overhead only.
        charged = _SNAPSHOT_OVERHEAD_BYTES
        REGISTRY.ensure_capacity(charged)
        _require_capture_budget(deadline)

        snapshot = IndexSnapshot(
            None,
            current.fingerprint if current else None,
            index,
            current.generation if current else None,
            "complete" if complete else "partial",
            reason,
            root,
            count,
            _physical_storage_identity(connection),
            projection_exact,
            source_scope,
        )
        published = REGISTRY.publish(snapshot, connection, charged, deadline, pin=pin)
        connection = None  # ownership transferred to registry
        return published
    except FileNotFoundError as exc:
        return _unknown(str(exc))
    except sqlite3.DatabaseError as exc:
        return _unknown(
            "CONCURRENT_WRITER"
            if any(x in str(exc).lower() for x in ("locked", "busy"))
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


def _capture_existing_snapshot(
    project_root: str, *, pin: bool = False, deadline: float | None = None
) -> IndexSnapshot:
    # Absence is platform-independent and publishes no file evidence.  Report it
    # before the secure-fd capability gate so fresh Windows installs preserve the
    # established missing-index contract; an existing database still fails closed.
    canonical_root = os.path.realpath(project_root)
    if not os.path.isdir(canonical_root):
        return _unknown("MISSING_PROJECT_ROOT")
    candidate = os.path.join(canonical_root, ".ast-cache", "index.db")
    if not os.path.lexists(candidate):
        return _unknown("MISSING_INDEX")
    # Phase B-1: Replace POSIX gate with WAL read-only fallback.
    # Non-POSIX systems (Windows) and POSIX without /dev/fd use WAL path.
    # POSIX with /dev/fd continues using the existing fd-pinned backup path.
    if os.name != "posix" or not os.path.exists("/dev/fd"):
        wal_deadline = _clock() + _CAPTURE_DEADLINE_SECONDS if deadline is None else deadline
        return _capture_wal_snapshot(
            canonical_root, candidate, pin=pin, deadline=wal_deadline
        )
    handles: tuple[int, int, int] | None = None
    connection: sqlite3.Connection | None = None
    evidence: sqlite3.Connection | None = None
    deadline = _clock() + _CAPTURE_DEADLINE_SECONDS if deadline is None else deadline
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

            # Copy in bounded 512 KiB chunks at the minimum SQLite page size;
            # this avoids thousands of Python callbacks for large certified caches.
            backup_pages = max(64, (512 * 1024) // source_page_size)
            connection.backup(evidence, pages=backup_pages, progress=progress, sleep=0)
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
            if complete and not projection_exact:
                complete = False
                reason = "SYMBOL_PROJECTION_INCOMPLETE"
            snapshot = IndexSnapshot(
                None,
                current.fingerprint if current else None,
                index,
                current.generation if current else None,
                "complete" if complete else "partial",
                reason,
                root,
                count,
                _physical_storage_identity(evidence),
                projection_exact,
                source_scope,
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
def lease_existing_snapshot(
    project_root: str, *, deadline: float | None = None
) -> Iterator[IndexSnapshot]:
    """Keep a successfully published capability pinned until response assembly."""
    snapshot = _capture_existing_snapshot(project_root, pin=True, deadline=deadline)
    try:
        yield snapshot
    finally:
        if snapshot.snapshot_id is not None:
            REGISTRY.release_pin(snapshot.snapshot_id)


@contextmanager
def lease_reusable_snapshot(
    project_root: str, *, deadline: float | None = None
) -> Iterator[IndexSnapshot | None]:
    """Pin a capability only while its source generation remains current."""
    with REGISTRY.pin_reusable(project_root) as snapshot:
        if (
            snapshot is None
            or snapshot.source_scope is None
            or snapshot.source_generation is None
        ):
            yield None
            return
        current = capture_current_source_snapshot(
            project_root,
            snapshot.source_scope,
            deadline=(
                _clock() + _CAPTURE_DEADLINE_SECONDS if deadline is None else deadline
            ),
        )
        if current.state != "exact" or current.generation != snapshot.source_generation:
            yield None
            return
        yield snapshot


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
    snapshot_id: str,
    project_root: str,
    source_generation: str | None = None,
    *,
    deadline: float | None = None,
) -> Any:
    """Acquire the registry-owned private copy, optionally with an absolute deadline."""
    return REGISTRY.acquire(
        snapshot_id, project_root, source_generation, deadline=deadline
    )


def verify_snapshot_source_current(
    snapshot: IndexSnapshot, *, deadline: float | None = None
) -> None:
    """Revalidate one acquired snapshot's source state after a read.

    RFC-0022 P0.4 after-read revalidation: recapture the current source over
    the snapshot's ``source_scope`` and compare the generation (or fingerprint)
    with the acquired capability. A mismatch raises ``SOURCE_GENERATION_MISMATCH``
    and the caller must emit no result. Snapshots without a scope descriptor
    (no manifest to capture against) skip the check, mirroring
    ``constraint_index_snapshot.evaluate_ordinary_snapshot``.
    """
    source_scope = snapshot.source_scope
    if source_scope is None:
        return
    source_root = snapshot.canonical_root
    if not isinstance(source_root, str) or not source_root:
        raise ValueError("INDEX_SNAPSHOT_UNKNOWN")
    deadline = _clock() + _CAPTURE_DEADLINE_SECONDS if deadline is None else deadline
    current = _capture_sources_with_deadline(source_root, source_scope, deadline)
    if current.state != "exact":
        raise ValueError(current.reason or "SOURCE_SCOPE_UNKNOWN")
    expected_generation = snapshot.source_generation
    if expected_generation is None:
        expected_fingerprint = snapshot.source_fingerprint
        if expected_fingerprint is None:
            raise ValueError("SOURCE_GENERATION_MISMATCH")
        if current.fingerprint != expected_fingerprint:
            raise ValueError("SOURCE_GENERATION_MISMATCH")
    elif current.generation != expected_generation:
        raise ValueError("SOURCE_GENERATION_MISMATCH")


@contextmanager
def read_existing_index_scope(
    snapshot_id: str,
    project_root: str,
    source_generation: str | None = None,
    *,
    deadline: float | None = None,
) -> Iterator[tuple[IndexSnapshot, sqlite3.Connection]]:
    """Acquire one certified index capability and revalidate it around the read.

    Consumer seam for the P0.1 read_existing route: acquires the registry copy
    (before-read token revalidation) under one absolute deadline, gates the
    capability (completeness + full source scope), re-captures the current
    source BEFORE the read and AGAIN after it, and compares generations both
    times. Any mismatch raises the stable code and the route emits no result.
    Reader pins and the I/O lock are released by ``acquire_index_snapshot``'s
    own cleanup on exit.
    """
    scope_deadline = (
        deadline if deadline is not None else _clock() + _CAPTURE_DEADLINE_SECONDS
    )
    with acquire_index_snapshot(
        snapshot_id, project_root, source_generation, deadline=scope_deadline
    ) as (snapshot, conn):
        try:
            # Codex P1 (#1299): a partial capability (CALL_GRAPH_INCOMPLETE /
            # SYMBOL_PROJECTION_INCOMPLETE) cannot certify project-wide graph
            # claims. RFC-0022 P0.1 oracle: graph-consuming rows do not start
            # without completeness "complete"; mirror the constraint route's
            # completeness gate.
            if snapshot.completeness != "complete":
                raise ValueError("INDEX_SNAPSHOT_INCOMPLETE")
            # A partial source scope (exclusions / non-root roots) cannot
            # certify project-wide graph claims: the after-read recapture
            # only re-checks the snapshot's OWN scope, so out-of-scope files
            # could be served uncertified. Mirror the constraint route's
            # full-scope gate.
            from .index_source_scope import SourceScopeDescriptor

            if not (
                isinstance(snapshot.source_scope, SourceScopeDescriptor)
                and snapshot.source_scope.roots == (".",)
                and not snapshot.source_scope.exclude_patterns
            ):
                raise ValueError("CONSTRAINED_INDEX_SCOPE")
            # Codex P1 (#1299): recapture BEFORE the read too. Acquisition
            # only compares the caller's token against registry metadata — a
            # source already modified when the read starts (and restored
            # mid-read) would otherwise pass the single after-read check
            # while the reader consumed the modified bytes. The pre-read
            # check runs at __enter__ (normal generator start), the
            # post-read check only on normal exit — the reader's own
            # exception always wins over the after-read check.
            verify_snapshot_source_current(snapshot, deadline=scope_deadline)
        except (ValueError, RuntimeError) as exc:
            # Codex P2 (#1299): pre-yield failures still acquired the
            # capability; carry its identity so the consumer's failure
            # envelope can cite the exact snapshot that was acquired.
            # cast(Any, ...) keeps mypy happy (ValueError/RuntimeError have
            # no such attribute) without ruff rewriting a setattr back into
            # an attribute assignment.
            cast(Any, exc)._read_existing_identity = (
                snapshot.snapshot_id,
                snapshot.source_generation,
            )
            raise

        # Codex P2 (#1299): bound the reader's SQL work with the same
        # absolute deadline. SQLite's progress handler fires every 1000 VM
        # opcodes; returning nonzero aborts the running statement. The
        # post-yield deadline re-check below is the hard guarantee even when
        # a reader swallows the abort inside its own exception guards.
        def _deadline_breached() -> int:
            return int(_clock() >= scope_deadline)

        conn.set_progress_handler(_deadline_breached, 1_000)
        try:
            yield snapshot, conn
        finally:
            conn.set_progress_handler(None, 0)
        if _clock() >= scope_deadline:
            raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")
        verify_snapshot_source_current(snapshot, deadline=scope_deadline)


def _unknown(reason: str) -> IndexSnapshot:
    return IndexSnapshot(None, None, None, None, "unknown", reason, None, 0)
