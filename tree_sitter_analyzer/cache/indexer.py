"""Indexing helpers for ASTCache."""
# ruff: noqa: E402, F401, I001

from __future__ import annotations

import fnmatch
import json
import logging
import os
import sqlite3
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from functools import partial
from typing import Any, cast


from ..constants import EXCLUDE_DIRS as _EXCLUDE_DIRS
from ..index_candidate_walker import (
    CandidateDiscoveryBudgetExceeded,
    CandidateDiscoveryError,
)
from ..index_source_snapshot import (
    SourceScopeDescriptor,
    canonical_source_scope_descriptor,
    make_source_scope_descriptor,
    parse_source_scope_descriptor,
    validate_full_index_source_scope,
)
from ..index_symbol_projection import symbol_projection_is_exact
from ..indexing_limits import normalize_index_max_files
from ..indexing_snapshot import (
    IndexCandidateSnapshot,
    IndexFileFingerprint,
    IndexSnapshotEntry,
    build_index_candidate_snapshot,
    changed_since_snapshot,
    validate_index_candidate_snapshot,
    walk_index_candidate_entries,
)
from ..languages.lang_extension_map import EXT_TO_LANG as _EXT_TO_LANG
from ..project_graph import _language_from_ext
from .build_state import (
    clear_build_in_progress as _clear_build_in_progress,
)
from .build_state import (
    mark_build_in_progress as _mark_build_in_progress,
)
from .callgraph_state import (
    clear_call_graph_built as _clear_call_graph_built,
)
from .callgraph_state import (
    clear_call_graph_built_strict as _clear_call_graph_built_strict,
)
from .callgraph_state import (
    mark_call_graph_built as _mark_call_graph_built,
)
from .callgraph_state import (
    mark_call_graph_built_strict as _mark_call_graph_built_strict,
)
from .helpers import (
    _make_error_entry,
    _project_index_activation_enabled,
)
from .schema import (
    clear_activation_for_file as _clear_activation_for_file_fn,
)

logger = logging.getLogger(__name__)


def _normalize_relative_path(value: str) -> str:
    """Treat backslash as a separator only on Windows."""
    return value.replace("\\", "/") if os.name == "nt" else value


def _remove_ladybug_from_pinned_cache(cache_fd: int) -> bool:
    """Remove the optional mirror relative to its identity-bound directory."""
    try:
        os.stat("knowledge-graph.lbug", dir_fd=cache_fd, follow_symlinks=False)
        os.unlink("knowledge-graph.lbug", dir_fd=cache_fd)
        return True
    except FileNotFoundError:
        return False


def _invalidate_ladybug(cache: Any, root_fd: int | None) -> bool:
    """Invalidate the mirror without leaving a pinned-cache mutation boundary."""
    if root_fd is not None:
        if not getattr(cache, "_uses_project_mirror", True):
            return False
        cache_fd = getattr(cache, "_cache_dir_fd", None)
        if cache_fd is None:
            raise OSError("AST_CACHE_DIRECTORY_UNBOUND")
        return _remove_ladybug_from_pinned_cache(cache_fd)
    from ..knowledge_graph.stores import LadybugKnowledgeGraphStore

    return LadybugKnowledgeGraphStore(cache.project_root).remove_if_exists()


# Corpus-directory patterns excluded from full-index (REQ-E-016).
# Uses fnmatch syntax relative to the project root (forward-slash normalised).
_DEFAULT_EXCLUDE_PATTERNS: frozenset[str] = frozenset(
    {
        "tests/golden/corpus_*",
    }
)

# Extensions that have a plugin but are NOT wired for full-index
# (REQ-E-020).  When a file with one of these extensions is encountered and
# language_fn returns None, a one-time WARNING is emitted so callers know why
# the file was silently skipped.
_PLUGIN_EXTS: frozenset[str] = frozenset(
    {
        ".css",
        ".html",
        ".md",
        ".sql",
        ".yaml",
        ".yml",
    }
)

# De-duplication set: only warn once per extension per process lifetime.
_warned_extensions: set[str] = set()

# Extractor version constant — kept in sync with ast_cache.py. Version 25
# persists parse-error state and invalidates every projection semantic fix.
_AST_CACHE_EXTRACTOR_VERSION = 29


def _walk_source_files(project_root: str) -> Iterator[str]:
    for dirpath, dirnames, filenames in os.walk(project_root):
        retained: list[str] = []
        for dirname in dirnames:
            if dirname in _EXCLUDE_DIRS or dirname.startswith("."):
                continue
            candidate = os.path.join(dirpath, dirname)
            if os.path.islink(candidate):
                if os.path.splitext(dirname)[1].lower() in _EXT_TO_LANG:
                    yield candidate
                continue
            retained.append(dirname)
        dirnames[:] = retained
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in _EXT_TO_LANG:
                yield os.path.join(dirpath, fname)


def _bounded_selected_supported_paths(
    project_root: str,
    max_files: int,
    language_filter: str | None,
    exclude_patterns: frozenset[str] | None,
) -> set[str] | None:
    """Rediscover the candidate-less run's exact bounded persisted path scope."""
    selected: set[str] = set()
    count = 0

    def legacy_candidates() -> Iterator[str]:
        # This fallback restores the pre-P0.1 operational marker on Windows.
        # It is never used by the authoritative manifest path, which remains
        # POSIX descriptor-bound and reports unsupported on this platform.
        def raise_walk_error(exc: OSError) -> None:
            raise exc

        for dirpath, dirnames, filenames in os.walk(
            project_root, onerror=raise_walk_error
        ):
            retained: list[str] = []
            for dirname in dirnames:
                if dirname in _EXCLUDE_DIRS or dirname.startswith("."):
                    continue
                candidate = os.path.join(dirpath, dirname)
                if os.path.islink(candidate):
                    if os.path.splitext(dirname)[1].lower() in _EXT_TO_LANG:
                        yield candidate
                    continue
                retained.append(dirname)
            dirnames[:] = retained
            for filename in filenames:
                yield os.path.join(dirpath, filename)

    try:
        candidates = (
            walk_index_candidate_entries(
                project_root, excluded_dir_names=frozenset(_EXCLUDE_DIRS)
            )
            if os.name == "posix"
            else legacy_candidates()
        )
        for abs_path in candidates:
            # Match the legacy walk's supported-extension window: unsupported
            # entries are still charged by the authoritative walker, but do not
            # consume max_files.
            if os.path.splitext(abs_path)[1].lower() not in _EXT_TO_LANG:
                continue
            if count >= max_files:
                return None
            count += 1
            rel_path = _normalize_relative_path(os.path.relpath(abs_path, project_root))
            if exclude_patterns and any(
                fnmatch.fnmatch(rel_path, pattern) for pattern in exclude_patterns
            ):
                continue
            language = _language_from_ext(abs_path)
            if language is None or (
                language_filter is not None and language != language_filter
            ):
                continue
            try:
                os.stat(abs_path, follow_symlinks=False)
            except OSError:
                return None
            selected.add(rel_path)
    except (CandidateDiscoveryBudgetExceeded, CandidateDiscoveryError, OSError):
        return None
    return selected


def _warn_unwired_plugin_extension(abs_path: str) -> None:
    """Emit the existing one-time warning for unsupported plugin extensions."""
    ext = os.path.splitext(abs_path)[1].lower()
    if ext and ext not in _warned_extensions and ext in _PLUGIN_EXTS:
        logger.warning(
            "Extension %s is registered in a plugin but not wired for "
            "full-index; use single-file mode for this language. File: %s",
            ext,
            abs_path,
        )
        _warned_extensions.add(ext)


from .indexer_io import (
    _clear_full_rebuild_rows,
    _delete_all_rows_if_present,
    check_cache_or_read,
    index_parallel,
    insert_index_row,
    parse_and_write,
    walk_and_partition,
)
from .indexer_snapshot import (
    _discard_snapshot_generation,
    _record_frozen_replay_mismatches,
    _snapshot_result_change_reason,
    _revalidate_committed_snapshot,
    _revalidate_snapshot_batch,
    _snapshot_result_is_stable,
    _unsafe_force_snapshot_result,
)


def _discard_with_root_lease(
    cache: Any, conn: sqlite3.Connection, rel_path: str, root_fd: int | None
) -> None:
    kwargs = {} if root_fd is None else {"root_fd": root_fd}
    _discard_snapshot_generation(cache, conn, rel_path, **kwargs)


def run_index_project(
    cache: Any,
    max_files: int = 20_000,
    force: bool = False,
    *,
    workers: int | None = None,
    resolve_only: bool = False,
    include_activation: bool | None = None,
    language_filter: str | None = None,
    exclude_patterns: frozenset[str] | None = None,
    candidate_snapshot: IndexCandidateSnapshot | None = None,
    source_scope: SourceScopeDescriptor | None = None,
    certify_manifest: bool = True,
) -> dict[str, Any]:
    import types
    from .index_project_runner import run_index_project as implementation

    bound = types.FunctionType(
        implementation.__code__,
        globals(),
        implementation.__name__,
        implementation.__defaults__,
        implementation.__closure__,
    )
    bound.__kwdefaults__ = implementation.__kwdefaults__
    return cast(
        dict[str, Any],
        bound(
            cache,
            max_files,
            force,
            workers=workers,
            resolve_only=resolve_only,
            include_activation=include_activation,
            language_filter=language_filter,
            exclude_patterns=exclude_patterns,
            candidate_snapshot=candidate_snapshot,
            source_scope=source_scope,
            certify_manifest=certify_manifest,
        ),
    )


def _call_graph_marker_is_built(conn: sqlite3.Connection) -> bool:
    """Require the shared exact current-pipeline marker predicate."""
    from .callgraph_state import call_graph_marker_is_current

    return call_graph_marker_is_current(conn)


def _prune_to_selected_scope(
    cache: Any,
    conn: sqlite3.Connection,
    candidate: IndexCandidateSnapshot,
    *,
    root_fd: int | None = None,
) -> int:
    """Transactionally remove primary and graph generations outside the scope."""
    selected = {entry.rel_path for entry in candidate.selected_entries}
    stale = {
        _normalize_relative_path(str(row[0]))
        for row in conn.execute("SELECT file_path FROM ast_index")
        if _normalize_relative_path(str(row[0])) not in selected
    }
    if not stale:
        return 0
    try:
        for rel_path in stale:
            _discard_with_root_lease(cache, conn, rel_path, root_fd)
        _clear_call_graph_built_strict(conn)
    except Exception:
        conn.rollback()
        raise
    return len(stale)


def _candidate_paths_are_exact(
    cache: Any,
    conn: sqlite3.Connection,
    candidate: IndexCandidateSnapshot | None,
    stats: Mapping[str, Any],
    max_files: int,
    language_filter: str | None,
    exclude_patterns: frozenset[str] | None,
) -> bool:
    paths = {
        _normalize_relative_path(str(row[0]))
        for row in conn.execute("SELECT file_path FROM ast_index")
    }
    run_is_complete = bool(
        not stats.get("truncated_by_max_files", False)
        and stats.get("errors", 0) == 0
        and stats.get("backfill_errors", 0) == 0
        and stats.get("incomplete_skips", 0) == 0
        and stats.get("changed_during_run", 0) == 0
    )
    if candidate is None:
        # A cached legacy run may still contain rows for sources deleted since
        # its previous marker.  Reapply the same bounded max/exclude/language
        # selection semantics and certify only exact persisted path equality.
        discovered = _bounded_selected_supported_paths(
            cache.project_root,
            max_files,
            language_filter,
            exclude_patterns,
        )
        return bool(run_is_complete and discovered is not None and paths == discovered)
    selected = {entry.rel_path for entry in candidate.selected_entries}
    return bool(
        run_is_complete
        and not candidate.truncated_by_max_files
        and candidate.errors == 0
        and paths == selected
    )


def _update_authoritative_manifest(
    cache: Any,
    candidate_snapshot: IndexCandidateSnapshot | None,
    stats: dict[str, Any],
    source_scope: SourceScopeDescriptor,
) -> None:
    """Certify only an exact, successful full-index inventory."""
    conn = cache._get_conn()
    selected_paths = (
        {entry.rel_path for entry in candidate_snapshot.selected_entries}
        if candidate_snapshot is not None
        else set()
    )
    exact_paths = bool(
        candidate_snapshot is not None
        and candidate_snapshot.limited == 0
        and candidate_snapshot.errors == 0
        and stats.get("errors", 0) == 0
        and stats.get("changed_during_run", 0) == 0
        and stats.get("backfill_errors", 0) == 0
        and {
            _normalize_relative_path(str(row["file_path"]))
            for row in conn.execute("SELECT file_path FROM ast_index")
        }
        == selected_paths
    )
    if exact_paths and _call_graph_marker_is_built(conn):
        from ..index_snapshot_schema import stamp_full_index_manifest

        try:
            stamp_full_index_manifest(conn, cache.project_root, source_scope)
            return
        except Exception:
            # The stamper rolls back its transaction, preserving the prior
            # manifest. Revoke the prerequisite marker in a separate committed
            # transaction so direct ASTCache readers cannot trust this run.
            from .callgraph_state import clear_call_graph_built_strict

            clear_call_graph_built_strict(conn)
            conn.commit()
            logger.warning(
                "index snapshot manifest certification failed", exc_info=True
            )
            stats["manifest_warning"] = "INDEX_MANIFEST_CERTIFICATION_FAILED"
            stats["manifest_certification_failed"] = True
            stats["certification_errors"] = stats.get("certification_errors", 0) + 1
            stats["scope_complete"] = False
            stats["verdict"] = "WARN"
            return
    if exact_paths and not _call_graph_marker_is_built(conn):
        stats["manifest_warning"] = "CALL_GRAPH_INCOMPLETE"
    # Do not delete a manifest epoch this operation did not publish. Status
    # compares source/index/marker fingerprints and classifies it as stale.


def _record_backfill_result(stats: dict[str, Any], key: str, result: Any) -> None:
    """Keep a helper diagnostic and fail closed unless it reports zero errors."""
    stats[key] = result
    if not isinstance(result, Mapping) or result.get("errors", 0) != 0:
        stats["backfill_errors"] += 1


def post_index_backfill(
    cache: Any,
    stats: dict[str, Any],
    *,
    root_fd: int | None = None,
) -> None:
    """Run backfills, recording suppressed failures for certification gates."""
    stats.setdefault("backfill_errors", 0)
    try:
        _record_backfill_result(
            stats, "cross_file_backfill", cache.backfill_cross_file_edges()
        )
    except Exception:
        stats["backfill_errors"] += 1
        logger.debug("cross-file backfill failed", exc_info=True)
    try:
        _record_backfill_result(
            stats, "synapse_backfill", cache._run_synapse_backfill()
        )
    except Exception:
        stats["backfill_errors"] += 1
        logger.debug("synapse backfill failed", exc_info=True)
    # ``insert_index_row`` already writes every file's graph edges during
    # commit on every SQLite backend. Re-deriving them here is pure duplicate
    # work: ~85 s on django (47 % of total index time) for an identical edge
    # set (244,590 rows either way, verified).
    try:
        _record_backfill_result(
            stats,
            "unresolved_refs_backfill",
            cache._run_unresolved_refs_backfill(),
        )
    except Exception:
        stats["backfill_errors"] += 1
        logger.debug("unresolved refs backfill failed", exc_info=True)
    if stats["backfill_errors"] == 0:
        try:
            from .unresolved import mark_resolution_converged

            mark_resolution_converged(cache._get_conn())
        except Exception:
            logger.debug("could not mark resolution converged", exc_info=True)
    try:
        # SQLite is the canonical graph index. LadybugDB is a derived projection
        # and must never survive an SQLite update as an implicitly fresh mirror.
        ladybug_removed = _invalidate_ladybug(cache, root_fd)
        if ladybug_removed:
            stats["knowledge_graph"] = {"ladybug_stale_removed": True}
    except Exception:
        logger.debug("auto knowledge graph build failed", exc_info=True)
