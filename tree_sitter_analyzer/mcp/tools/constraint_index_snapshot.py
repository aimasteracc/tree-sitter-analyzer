"""Portable private SQLite snapshots for ordinary read-only constraint checks."""

from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ...cache.build_state import build_in_progress
from ...index_snapshot_capability import (
    exact_call_graph_marker,
    require_memory_temp_store,
)
from ...index_snapshot_schema import index_fingerprint, validate_snapshot_schema
from ...index_snapshot_symbols import has_ordinary_symbol_projection
from ...index_source_snapshot import (
    capture_current_source_snapshot,
    recorded_source_rows,
)
from ...index_symbol_projection import (
    sqlite_compile_supports_fts5,
    symbol_projection_is_exact,
)
from ...portable_source_snapshot import capture_portable_source_snapshot
from .constraint_check_portable_snapshot import (
    portable_snapshot_required as _portable_snapshot_required,
)
from .constraint_index_snapshot_budget import copy_pinned_database
from .constraint_index_snapshot_faults import (
    close_optional_fd,
    path_identity,
    stat_identity,
)

_MAX_BACKUP_BYTES = 510 * 1024 * 1024


def _open(*args: Any, **kwargs: Any) -> int:
    """Module-local open seam for exact pathname-swap fault injection."""
    return os.open(*args, **kwargs)


@dataclass(frozen=True, slots=True)
class OrdinaryConstraintSnapshot:
    """Certification metadata paired with a caller-owned private connection."""

    completeness: str
    reason: str | None
    source_scope: Any | None
    source_generation: str | None = None
    source_fingerprint: str | None = None


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return stat_identity(info)


def _identity(path: Path, *, directory: bool) -> tuple[int, int, int, int, int]:
    return path_identity(path, directory=directory)


def _open_database_fd(db_path: Path, expected: tuple[int, int, int, int, int]) -> int:
    """Open the database read-only and bind the descriptor to its lstat identity."""
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    fd = _open(db_path, flags)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or _stat_identity(opened) != expected:
            raise ValueError("CONCURRENT_WRITER")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _copy_pinned_database(
    fd: int,
    expected: tuple[int, int, int, int, int],
    stream: Any,
    *,
    deadline: float,
) -> None:
    copy_pinned_database(
        fd,
        expected,
        stream,
        deadline=deadline,
        byte_limit=_MAX_BACKUP_BYTES,
        check_deadline=_deadline,
        stat_identity=_stat_identity,
    )


@contextmanager
def _temporary_copy(
    fd: int,
    expected: tuple[int, int, int, int, int],
    root: str,
    *,
    deadline: float,
) -> Iterator[Path]:
    """Stream a pinned database into a private directory outside the project."""
    with tempfile.TemporaryDirectory(prefix="tsa-constraint-index-") as tmp:
        tmp_real = os.path.realpath(tmp)
        try:
            inside_project = os.path.commonpath((root, tmp_real)) == root
        except ValueError:
            inside_project = False
        if inside_project:
            raise ValueError("INDEX_TEMP_OUTSIDE_PROJECT_REQUIRED")
        copy_path = Path(tmp_real) / "index.db"
        with copy_path.open("xb", buffering=0) as stream:
            _copy_pinned_database(fd, expected, stream, deadline=deadline)
        yield copy_path


def _sidecar_state(
    db_path: Path,
) -> tuple[tuple[str, tuple[int, int, int, int, int] | None], ...]:
    states: list[tuple[str, tuple[int, int, int, int, int] | None]] = []
    for suffix in ("-wal", "-journal", "-shm"):
        path = Path(str(db_path) + suffix)
        try:
            identity = _identity(path, directory=False)
        except FileNotFoundError:
            identity = None
        if suffix != "-shm" and identity is not None and identity[2] != 0:
            raise ValueError("CONCURRENT_WRITER")
        states.append((suffix, identity))
    return tuple(states)


def _close_optional_fd(fd: int | None) -> None:
    close_optional_fd(fd)


def _deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")


def _capture_constraint_sources(root: str, source_scope: Any, deadline: float) -> Any:
    if portable_snapshot_required():
        return capture_portable_source_snapshot(root, source_scope, deadline=deadline)
    return capture_current_source_snapshot(root, source_scope, deadline=deadline)


def _certify_private_copy(
    conn: sqlite3.Connection, root: str, *, deadline: float
) -> OrdinaryConstraintSnapshot:
    """Apply the same exact-manifest authority checks to an in-memory copy."""
    from ...index_snapshot import _read_bounded_manifest, _validate_manifest_scalars
    from ...index_source_snapshot import parse_source_scope_descriptor

    _deadline(deadline)
    validate_snapshot_schema(conn, deadline=deadline)
    if build_in_progress(conn):
        raise ValueError("CONCURRENT_WRITER")
    manifest = _read_bounded_manifest(conn, deadline)
    if manifest is None:
        return OrdinaryConstraintSnapshot(
            "partial", "SOURCE_SCOPE_DESCRIPTOR_MISSING", None
        )
    _validate_manifest_scalars(manifest)
    try:
        source_scope = parse_source_scope_descriptor(
            manifest["source_scope_descriptor"]
        )
    except (TypeError, ValueError):
        return OrdinaryConstraintSnapshot(
            "partial", "SOURCE_SCOPE_DESCRIPTOR_INVALID", None
        )
    current = _capture_constraint_sources(root, source_scope, deadline)
    if current.state != "exact":
        return OrdinaryConstraintSnapshot(
            "partial", current.reason or "SOURCE_SCOPE_UNKNOWN", source_scope
        )
    recorded = recorded_source_rows(conn, deadline=deadline)
    index = index_fingerprint(conn, root, deadline=deadline)
    exact = (
        recorded == current.rows
        and manifest["canonical_root"] == root
        and manifest["source_fingerprint"] == current.fingerprint
        and manifest["index_fingerprint"] == index
        and manifest["file_count"] == len(recorded)
        and manifest["manifest_version"] == 2
        and exact_call_graph_marker(conn, deadline=deadline)
    )
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    fts5 = sqlite_compile_supports_fts5(conn)
    projection_exact = bool(
        fts5 is not None
        and has_ordinary_symbol_projection(conn, tables)
        and symbol_projection_is_exact(conn, deadline=deadline, require_fts=fts5)
    )
    if not exact:
        return OrdinaryConstraintSnapshot(
            "partial", "NO_EXACT_FULL_INDEX_MANIFEST", source_scope
        )
    if not projection_exact:
        return OrdinaryConstraintSnapshot(
            "partial", "SYMBOL_PROJECTION_INCOMPLETE", source_scope
        )
    final_current = _capture_constraint_sources(root, source_scope, deadline)
    if final_current.state != "exact":
        return OrdinaryConstraintSnapshot(
            "partial",
            final_current.reason or "SOURCE_SCOPE_UNKNOWN",
            source_scope,
        )
    if (
        final_current.rows != current.rows
        or final_current.fingerprint != current.fingerprint
    ):
        raise ValueError("CONCURRENT_SOURCE")
    return OrdinaryConstraintSnapshot(
        "complete",
        None,
        source_scope,
        final_current.generation,
        final_current.fingerprint,
    )


@contextmanager
def portable_ordinary_snapshot(
    project_root: str, *, deadline: float
) -> Iterator[tuple[OrdinaryConstraintSnapshot, sqlite3.Connection]]:
    """Certify a stable pinned database through an outside-project private copy."""
    root = os.path.realpath(os.path.abspath(project_root))
    root_path = Path(root)
    cache_path = root_path / ".ast-cache"
    db_path = cache_path / "index.db"
    root_before = _identity(root_path, directory=True)
    try:
        cache_before = _identity(cache_path, directory=True)
        db_before = _identity(db_path, directory=False)
    except FileNotFoundError as exc:
        raise ValueError("MISSING_INDEX") from exc
    sidecars_before = _sidecar_state(db_path)
    _deadline(deadline)
    db_fd: int | None = None
    source: sqlite3.Connection | None = None
    private: sqlite3.Connection | None = None
    try:
        db_fd = _open_database_fd(db_path, db_before)
        with _temporary_copy(db_fd, db_before, root, deadline=deadline) as copy_path:
            if (
                _identity(root_path, directory=True) != root_before
                or _identity(cache_path, directory=True) != cache_before
                or _identity(db_path, directory=False) != db_before
                or _sidecar_state(db_path) != sidecars_before
            ):
                raise ValueError("CONCURRENT_WRITER")
            # SQLite is intentionally given only the private copy's pathname,
            # never the mutable project database pathname.
            copy_complete = False
            try:
                uri = copy_path.as_uri() + "?mode=ro&immutable=1"
                source = sqlite3.connect(uri, uri=True, timeout=0, isolation_level=None)
                source.execute("PRAGMA query_only=ON")
                source.execute("PRAGMA busy_timeout=0")
                require_memory_temp_store(source)
                page_size = int(source.execute("PRAGMA page_size").fetchone()[0])
                page_count = int(source.execute("PRAGMA page_count").fetchone()[0])
                if page_size * page_count > _MAX_BACKUP_BYTES:
                    raise RuntimeError("INDEX_BACKUP_BUDGET")
                private = sqlite3.connect(":memory:")
                require_memory_temp_store(private)

                def progress(_status: int, _remaining: int, total: int) -> None:
                    if total * page_size > _MAX_BACKUP_BYTES:
                        raise RuntimeError("INDEX_BACKUP_BUDGET")
                    _deadline(deadline)

                source.backup(
                    private,
                    pages=max(64, (512 * 1024) // page_size),
                    progress=progress,
                    sleep=0,
                )
                copy_complete = True
            finally:
                try:
                    if source is not None:
                        source.close()
                        source = None
                finally:
                    if not copy_complete and private is not None:
                        private.close()
                        private = None

        if private is None:
            raise ValueError("CONSTRAINT_INDEX_UNKNOWN")
        if (
            _stat_identity(os.fstat(db_fd)) != db_before
            or _identity(root_path, directory=True) != root_before
            or _identity(cache_path, directory=True) != cache_before
            or _identity(db_path, directory=False) != db_before
            or _sidecar_state(db_path) != sidecars_before
        ):
            raise ValueError("CONCURRENT_WRITER")
        private.row_factory = sqlite3.Row
        try:
            snapshot = _certify_private_copy(private, root, deadline=deadline)
        except sqlite3.DatabaseError as exc:
            raise ValueError("CORRUPT_INDEX") from exc
        if (
            _stat_identity(os.fstat(db_fd)) != db_before
            or _identity(root_path, directory=True) != root_before
            or _identity(cache_path, directory=True) != cache_before
            or _identity(db_path, directory=False) != db_before
            or _sidecar_state(db_path) != sidecars_before
        ):
            raise ValueError("CONCURRENT_WRITER")
        private.execute("PRAGMA query_only=ON")
        private.execute("BEGIN")
        yield snapshot, private
    finally:
        try:
            if source is not None:
                source.close()
        finally:
            try:
                if private is not None:
                    private.close()
            finally:
                _close_optional_fd(db_fd)


def ordinary_source_scope_is_full(source_scope: object) -> bool:
    """Reject caller-selected exclusions and partial roots for project-wide checks."""
    from ...index_source_scope import SourceScopeDescriptor

    return (
        isinstance(source_scope, SourceScopeDescriptor)
        and source_scope.roots == (".",)
        and not source_scope.exclude_patterns
    )


def portable_snapshot_required() -> bool:
    return _portable_snapshot_required()


def evaluate_ordinary_snapshot(
    tool: Any,
    constraints: list[Any],
    *,
    path_filter: str,
    min_severity_rank: int,
    scope_paths: frozenset[str] | None,
    evaluator: Any,
    deadline: float,
) -> tuple[list[dict[str, Any]], int]:
    """Acquire the platform authority and evaluate its private connection."""
    import inspect

    project_root = tool.project_root
    if project_root is None:
        raise ValueError("MISSING_PROJECT_ROOT")
    if portable_snapshot_required():
        authority = portable_ordinary_snapshot(project_root, deadline=deadline)
    else:
        from ...index_snapshot import acquire_index_snapshot, lease_existing_snapshot

        @contextmanager
        def registry_authority() -> Iterator[tuple[Any, sqlite3.Connection]]:
            lease_kwargs = (
                {"deadline": deadline}
                if "deadline" in inspect.signature(lease_existing_snapshot).parameters
                else {}
            )
            with lease_existing_snapshot(project_root, **lease_kwargs) as index:
                if index.snapshot_id is None or index.completeness != "complete":
                    raise ValueError(index.reason or "CONSTRAINT_INDEX_UNKNOWN")
                acquire_kwargs = (
                    {"deadline": deadline}
                    if "deadline"
                    in inspect.signature(acquire_index_snapshot).parameters
                    else {}
                )
                with acquire_index_snapshot(
                    index.snapshot_id,
                    project_root,
                    index.source_generation,
                    **acquire_kwargs,
                ) as (_, conn):
                    yield index, conn

        authority = registry_authority()
    with authority as (index, conn):
        if index.completeness != "complete":
            raise ValueError(index.reason or "CONSTRAINT_INDEX_UNKNOWN")
        source_scope = getattr(index, "source_scope", None)
        if hasattr(index, "source_scope") and not ordinary_source_scope_is_full(
            source_scope
        ):
            raise ValueError("CONSTRAINT_INDEX_SCOPE_MISMATCH")
        result = cast(
            tuple[list[dict[str, Any]], int],
            tool._evaluate_connection(
                conn,
                constraints,
                path_filter=path_filter,
                min_severity_rank=min_severity_rank,
                scope_paths=scope_paths,
                evaluator=evaluator,
                deadline=deadline,
            ),
        )
        if source_scope is not None:
            current = _capture_constraint_sources(project_root, source_scope, deadline)
            if current.state != "exact":
                raise ValueError(current.reason or "SOURCE_SCOPE_UNKNOWN")
            expected_generation = getattr(index, "source_generation", None)
            if expected_generation is None:
                expected_fingerprint = getattr(index, "source_fingerprint", None)
                if expected_fingerprint is None:
                    raise ValueError("SOURCE_GENERATION_MISMATCH")
                if current.fingerprint != expected_fingerprint:
                    raise ValueError("SOURCE_GENERATION_MISMATCH")
            elif current.generation != expected_generation:
                raise ValueError("SOURCE_GENERATION_MISMATCH")
        return result
