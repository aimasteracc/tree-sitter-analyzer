"""Indexing helpers for ASTCache.

Pure functions extracted from ASTCache indexing pipeline methods to
reduce ast_cache.py line count. ASTCache keeps thin wrapper methods
that delegate here.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import sqlite3
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from functools import partial
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    pass

from ..constants import EXCLUDE_DIRS as _EXCLUDE_DIRS
from ..index_source_snapshot import (
    SourceScopeDescriptor,
    make_source_scope_descriptor,
    validate_full_index_source_scope,
)
from ..indexing_limits import normalize_index_max_files
from ..indexing_snapshot import (
    IndexCandidateSnapshot,
    IndexFileFingerprint,
    IndexSnapshotEntry,
    changed_since_snapshot,
    validate_index_candidate_snapshot,
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

# Extractor version constant — kept in sync with ast_cache.py.
# v3: #610 — Python module-level constants extracted as kind="constant".
# v4: #613 — Go package-level const/var specs extracted as kind="constant".
# v5: #613 — Rust const/static items extracted as kind="constant".
# v6: #614 — docstring/return_type/params serialized into symbols_json.
# v7: #624 — PHP const declarations extracted as kind="constant".
# v8: #626 — JS/TS function-local variables no longer over-captured.
# v9: #626 — Java function-local variables no longer over-captured.
# v10: #628 — C# function-local variables no longer over-captured.
# v11: #638 — call edges keep ALL same-named definition spans; calls inside
#      the earlier of two same-named methods regain their enclosing caller.
# v12: #779 — walker depth cap raised 20 -> 100; bump forces re-index of files
#      cached under the old cap so deeply nested symbols are no longer truncated.
# v13: #949 — bash variable_assignment indexing: skip command-prefix env vars
#      (``FOO=bar make``) and unwrap subscript only for assignment targets.
# v14: #1094 / RFC-0019 — function symbols now carry the extractor's canonical
#      ``complexity`` so the cache-backed heatmap matches the extractor instead
#      of re-deriving the count from the per-arm ``decision_points`` sum.
_AST_CACHE_EXTRACTOR_VERSION = 14


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


def check_cache_or_read(
    conn: sqlite3.Connection,
    rel_path: str,
    abs_path: str,
    stat: os.stat_result,
    content_hash_fn: Any,
    extractor_version: int,
) -> dict[str, Any] | tuple[str, str]:
    """Return cached-response dict or (source_code, content_hash) if stale."""
    row = conn.execute(
        "SELECT content_hash, mtime_ns, file_size, extractor_version "
        "FROM ast_index WHERE file_path = ?",
        (rel_path,),
    ).fetchone()
    if row is not None and (
        row["mtime_ns"] == int(stat.st_mtime_ns)
        and row["file_size"] == stat.st_size
        and row["extractor_version"] >= extractor_version
    ):
        return {"file": rel_path, "status": "cached", "reason": "unchanged"}
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            source_code = f.read()
    except OSError as e:
        return {"file": rel_path, "status": "error", "reason": str(e)}
    content_hash = content_hash_fn(source_code)
    if (
        row is not None
        and row["content_hash"] == content_hash
        and row["extractor_version"] >= extractor_version
    ):
        conn.execute(
            "UPDATE ast_index SET mtime_ns = ?, file_size = ? WHERE file_path = ?",
            (int(stat.st_mtime_ns), stat.st_size, rel_path),
        )
        conn.commit()
        return {"file": rel_path, "status": "cached", "reason": "content unchanged"}
    return source_code, content_hash


def parse_and_write(
    cache: Any,
    conn: sqlite3.Connection,
    abs_path: str,
    rel_path: str,
    language: str,
    stat: os.stat_result,
    source_code: str,
    content_hash: str,
    extractor_version: int,
) -> dict[str, Any]:
    """Parse a file and write all cache rows. Returns result dict."""
    from .extraction import (
        _extract_call_edges,
        _extract_imports,
        _extract_structure,
        _extract_symbols,
    )

    result = cache.parser.parse_file(abs_path, language)
    if not result.success:
        return {
            "file": rel_path,
            "status": "error",
            "reason": result.error_message or "parse failed",
        }
    symbols = _extract_symbols(result.tree, source_code, language)
    imports = _extract_imports(symbols)
    structure = _extract_structure(symbols)
    call_edges = _extract_call_edges(result.tree, source_code, language, symbols)
    indexed_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO ast_index "
        "(file_path, content_hash, language, mtime_ns, file_size, "
        "extractor_version, symbols_json, imports_json, structure_json, indexed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rel_path,
            content_hash,
            language,
            int(stat.st_mtime_ns),
            stat.st_size,
            extractor_version,
            json.dumps(symbols, ensure_ascii=False),
            json.dumps(imports, ensure_ascii=False),
            json.dumps(structure, ensure_ascii=False),
            indexed_at,
        ),
    )
    from . import write as _write

    inserted = _write.write_fts5_symbols(
        conn, rel_path, language, symbols, cache.fts5_available
    )
    cache._write_imports_for_file(conn, rel_path, language, imports)  # noqa: SLF001
    cache._write_activation_for_file(conn, rel_path, inserted)  # noqa: SLF001
    # CALLS rows live in the unified ``edges`` table (B1.3 — no ast_call_edges).
    # Write the edges first so synapse resolution can UPDATE them in place.
    if not _write.write_graph_edges_for_file(
        conn, rel_path, language, symbols, imports, call_edges
    ):
        conn.rollback()
        return {
            "file": rel_path,
            "status": "error",
            "reason": "graph edge write failed",
            "certification_errors": 1,
        }
    cache._resolve_call_edges_for_file(conn, rel_path)  # noqa: SLF001
    conn.commit()
    return {
        "file": rel_path,
        "status": "indexed",
        "symbols": len(symbols.get("symbols", [])),
        "call_edges": len(call_edges),
        "content_hash": content_hash[:16],
    }


def walk_and_partition(
    cache: Any,
    conn: sqlite3.Connection,
    max_files: int,
    force: bool,
    activation_enabled: bool,
    walk_fn: Any,
    language_fn: Any,
    extractor_version: int,
    make_error_entry: Any,
    language_filter: str | None = None,
    exclude_patterns: frozenset[str] | None = None,
    candidate_snapshot: IndexCandidateSnapshot | None = None,
) -> tuple[dict[str, Any], list[tuple[str, str]], int]:
    """Walk source files and partition into (stats, candidates, count).

    ``language_filter`` (#1018): when set, only files whose detected language
    equals it are considered; non-matching files are skipped BEFORE any parse
    attempt, so a Python-scoped run never tries to load an optional grammar
    (e.g. Swift) and never surfaces a "grammar not installed" error.
    """
    max_files = normalize_index_max_files(max_files)
    candidates: list[tuple[str, str]] = []
    already_cached: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "mode_used": "full" if force else "incremental",
        "indexed": 0,
        "cached": 0,
        "errors": 0,
        "skipped": 0,
        "processed": 0,
        "changed_during_run": 0,
        "changed_during_run_files": [],
        "files": [],
        "activation_enabled": activation_enabled,
        "truncated_by_max_files": False,
    }
    if force:
        indexed_map: dict[str, tuple[int, int, int]] = {}
    else:
        rows = conn.execute(
            "SELECT file_path, mtime_ns, file_size, extractor_version FROM ast_index"
        ).fetchall()
        indexed_map = {
            r["file_path"]: (r["mtime_ns"], r["file_size"], r["extractor_version"])
            for r in rows
        }

    if candidate_snapshot is not None:
        validate_index_candidate_snapshot(
            cache.project_root, max_files, candidate_snapshot
        )
        stats["truncated_by_max_files"] = candidate_snapshot.truncated_by_max_files
        stats["snapshot_metrics"] = candidate_snapshot.metrics()
        count = len(candidate_snapshot.entries)
        for entry in candidate_snapshot.entries:
            if entry.decision == "excluded":
                stats["skipped"] += 1
                continue
            if entry.decision == "skipped":
                if entry.language is None:
                    _warn_unwired_plugin_extension(entry.abs_path)
                stats["skipped"] += 1
                continue
            if entry.decision == "error":
                stats["errors"] += 1
                stats["files"].append(
                    make_error_entry(entry.rel_path, entry.reason or "stat failed")
                )
                continue

            change_reason = changed_since_snapshot(entry)
            if change_reason is not None:
                stats["skipped"] += 1
                stats["changed_during_run"] += 1
                stats["changed_during_run_files"].append(entry.rel_path)
                stats["files"].append(
                    {
                        "file": entry.rel_path,
                        "status": "skipped",
                        "reason": change_reason,
                    }
                )
                continue

            fingerprint = cast(IndexFileFingerprint, entry.fingerprint)
            language = cast(str, entry.language)
            row = indexed_map.get(entry.rel_path)
            if (
                row is not None
                and row[0] == fingerprint.mtime_ns
                and row[1] == fingerprint.file_size
                and row[2] >= extractor_version
            ):
                already_cached.append(
                    {
                        "file": entry.rel_path,
                        "status": "cached",
                        "reason": "unchanged",
                    }
                )
                continue
            candidates.append((entry.abs_path, language))

        stats["cached"] += len(already_cached)
        stats["files"].extend(already_cached)
        stats["processed"] = len(candidates) + len(already_cached)
        return stats, candidates, count

    count = 0
    for abs_path in walk_fn(cache.project_root):
        if count >= max_files:
            stats["truncated_by_max_files"] = True
            break
        count += 1
        rel_path = _normalize_relative_path(
            os.path.relpath(abs_path, cache.project_root)
        )
        # REQ-E-016: skip files matching corpus-exclusion patterns.
        if exclude_patterns:
            if any(fnmatch.fnmatch(rel_path, pat) for pat in exclude_patterns):
                stats["skipped"] += 1
                continue
        lang = language_fn(abs_path)
        if lang is None:
            # REQ-E-020: emit a one-time WARNING for plugin-registered extensions
            # that are not wired into the full-index path.
            _warn_unwired_plugin_extension(abs_path)
            stats["skipped"] += 1
            continue
        if language_filter is not None and lang != language_filter:
            stats["skipped"] += 1
            continue
        try:
            stat = os.stat(abs_path)
        except OSError as e:
            stats["errors"] += 1
            stats["files"].append(make_error_entry(rel_path, str(e)))
            continue
        row = indexed_map.get(rel_path)
        if (
            row is not None
            and row[0] == int(stat.st_mtime_ns)
            and row[1] == stat.st_size
            and row[2] >= extractor_version
        ):
            already_cached.append(
                {"file": rel_path, "status": "cached", "reason": "unchanged"}
            )
            continue
        candidates.append((abs_path, lang))
    stats["cached"] += len(already_cached)
    stats["files"].extend(already_cached)
    stats["processed"] = len(candidates) + len(already_cached)
    return stats, candidates, count


def _clear_full_rebuild_rows(cache: Any, conn: sqlite3.Connection) -> None:
    """Clear primary and derived index rows before a forced rebuild."""
    conn.execute("DELETE FROM ast_index")
    if cache.fts5_available:
        conn.execute(
            "INSERT INTO ast_symbols_fts(ast_symbols_fts) VALUES('delete-all')"
        )
    _delete_all_rows_if_present(conn, "ast_symbol_rows")
    for table in ("ast_imports", "ast_symbol_activation", "edges"):
        _delete_all_rows_if_present(conn, table)


def _delete_all_rows_if_present(conn: sqlite3.Connection, table: str) -> None:
    """Delete a legacy-optional table, propagating every real database failure."""
    try:
        conn.execute(f"DELETE FROM {table}")  # nosec B608 - fixed table names
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise


def insert_index_row(
    cache: Any,
    conn: sqlite3.Connection,
    r: dict[str, Any],
    indexed_at: str,
    extractor_version: int,
    include_activation: bool = True,
) -> None:
    """Write one worker result to SQLite (main table + optional FTS5)."""
    rel_path = r["rel_path"]
    conn.execute(
        """INSERT OR REPLACE INTO ast_index
           (file_path, content_hash, language, mtime_ns, file_size,
            extractor_version, symbols_json, imports_json, structure_json,
            indexed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            rel_path,
            r["content_hash"],
            r["language"],
            r["mtime_ns"],
            r["file_size"],
            extractor_version,
            r["symbols_json"],
            r["imports_json"],
            r["structure_json"],
            indexed_at,
        ),
    )
    from . import write as _write

    inserted_symbol_rows = _write.write_fts5_symbols_from_tuples(
        conn,
        rel_path,
        r["language"],
        r["symbol_rows"],
        cache.fts5_available,
    )
    call_edges = json.loads(r.get("call_edges_json", "[]"))
    imports_list = json.loads(r.get("imports_json", "[]"))
    cache._write_imports_for_file(conn, rel_path, r["language"], imports_list)  # noqa: SLF001
    symbols = json.loads(r.get("symbols_json", "{}"))
    # CALLS rows live in the unified ``edges`` table (B1.3 — no ast_call_edges).
    # Cross-file / synapse resolution UPDATEs these rows in the post-index pass.
    if not _write.write_graph_edges_for_file(
        conn, rel_path, r["language"], symbols, imports_list, call_edges
    ):
        raise sqlite3.OperationalError("GRAPH_EDGE_WRITE_FAILED")
    if include_activation:
        cache._write_activation_for_file(conn, rel_path, inserted_symbol_rows)  # noqa: SLF001
    else:
        _clear_activation_for_file_fn(conn, rel_path)


def index_parallel(
    cache: Any,
    candidates: list[tuple[str, str]],
    workers: int,
    fingerprints: Mapping[str, IndexFileFingerprint] | None = None,
) -> list[dict[str, Any]]:
    """Dispatch parse+extract to a spawn process pool (safe on macOS/Linux)."""
    from multiprocessing import get_context

    from .extraction import _init_worker_parser, _worker_index_file

    ctx = get_context("spawn")
    args_iter = [
        (
            path,
            cache.project_root,
            language,
            fingerprints.get(path) if fingerprints is not None else None,
        )
        for path, language in candidates
    ]
    with ctx.Pool(processes=workers, initializer=_init_worker_parser) as pool:
        return list(pool.imap_unordered(_worker_index_file, args_iter, chunksize=8))


def _snapshot_result_change_reason(
    result: dict[str, Any],
    entries: dict[str, IndexSnapshotEntry],
) -> tuple[str, str | None]:
    rel_path = _normalize_relative_path(str(result["rel_path"]))
    entry = entries[rel_path]
    if result.get("status") == "source_changed":
        return rel_path, "file changed after candidate snapshot"
    fingerprint = cast(IndexFileFingerprint, entry.fingerprint)
    worker_fingerprint = (
        int(result.get("mtime_ns", fingerprint.mtime_ns)),
        int(result.get("file_size", fingerprint.file_size)),
    )
    expected_fingerprint = (fingerprint.mtime_ns, fingerprint.file_size)
    return rel_path, (
        "file changed after candidate snapshot"
        if worker_fingerprint != expected_fingerprint
        else changed_since_snapshot(entry)
    )


def _record_snapshot_change(
    stats: dict[str, Any], rel_path: str, change_reason: str
) -> None:
    """Replace one processed result with a deterministic snapshot skip."""
    stats["skipped"] += 1
    stats["processed"] = max(0, int(stats["processed"]) - 1)
    stats["changed_during_run"] += 1
    stats["changed_during_run_files"].append(rel_path)
    stats["files"].append(
        {"file": rel_path, "status": "skipped", "reason": change_reason}
    )


def _discard_snapshot_generation(
    cache: Any,
    conn: sqlite3.Connection,
    rel_path: str,
) -> None:
    """Remove canonical rows and invalidate their derived graph projection."""
    from . import write as _write

    _write.discard_file_rows(conn, rel_path, cache.fts5_available)
    try:
        from ..knowledge_graph.stores import LadybugKnowledgeGraphStore

        LadybugKnowledgeGraphStore(cache.project_root).remove_if_exists()
    except Exception:
        logger.debug("could not invalidate Ladybug mirror", exc_info=True)


def _snapshot_result_is_stable(
    result: dict[str, Any],
    entries: dict[str, IndexSnapshotEntry],
    stats: dict[str, Any],
    *,
    cache: Any,
    conn: sqlite3.Connection,
) -> bool:
    """Validate one worker result immediately before its database write."""
    rel_path, change_reason = _snapshot_result_change_reason(result, entries)
    if change_reason is None:
        return True

    _discard_snapshot_generation(cache, conn, rel_path)
    _record_snapshot_change(stats, rel_path, change_reason)
    return False


def _revalidate_snapshot_batch(
    pending_results: list[dict[str, Any]],
    *,
    cache: Any,
    conn: sqlite3.Connection,
    entries: dict[str, IndexSnapshotEntry],
    stats: dict[str, Any],
) -> None:
    """Discard pending generations that changed before their batch commit."""
    for result in pending_results:
        rel_path, change_reason = _snapshot_result_change_reason(result, entries)
        if change_reason is None:
            continue
        _discard_snapshot_generation(cache, conn, rel_path)
        if result["status"] in ("io_error", "parse_failed"):
            stats["errors"] -= 1
        else:
            stats["indexed"] -= 1
        for index in range(len(stats["files"]) - 1, -1, -1):
            if stats["files"][index]["file"] == rel_path:
                del stats["files"][index]
                break
        _record_snapshot_change(stats, rel_path, change_reason)


def _revalidate_committed_snapshot(
    *,
    cache: Any,
    conn: sqlite3.Connection,
    entries: dict[str, IndexSnapshotEntry],
    stats: dict[str, Any],
) -> None:
    """Invalidate any earlier committed generation changed before backfill."""
    known_changed = set(stats["changed_during_run_files"])
    for rel_path, entry in entries.items():
        change_reason = (
            None if rel_path in known_changed else changed_since_snapshot(entry)
        )
        if change_reason is None:
            continue
        _discard_snapshot_generation(cache, conn, rel_path)
        detail_files = [detail["file"] for detail in stats["files"]]
        detail_index = detail_files.index(rel_path)
        detail = stats["files"].pop(detail_index)
        counter = {
            "error": "errors",
            "indexed": "indexed",
            "cached": "cached",
        }[detail["status"]]
        stats[counter] -= 1
        _record_snapshot_change(stats, rel_path, change_reason)


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
) -> dict[str, Any]:
    """Orchestrate a full ASTCache project index run.

    ASTCache keeps the connection/backfill helpers; this module owns the
    high-level control flow so ``ast_cache.py`` stays thin.
    """
    max_files = normalize_index_max_files(max_files)
    activation_enabled = _project_index_activation_enabled(include_activation)
    if resolve_only:
        synapse = cache._run_synapse_backfill()
        edge_store_refresh = cache._refresh_graph_edges_from_cache()
        unresolved = cache._run_unresolved_refs_backfill()
        return {
            "mode_used": "resolve_only",
            "resolve_only": True,
            "indexed": 0,
            "cached": 0,
            "errors": 0,
            "skipped": 0,
            "files": [],
            "synapse_backfill": synapse,
            "edge_store_refresh": edge_store_refresh,
            "unresolved_refs_backfill": unresolved,
            "activation_enabled": activation_enabled,
        }
    if candidate_snapshot is not None:
        validate_index_candidate_snapshot(
            cache.project_root, max_files, candidate_snapshot
        )
    try:
        if force:
            # #578: a full rebuild empties ast_index up front (the DELETE
            # below commits), then re-populates in bounded batches over
            # ~70 s. Stamp a persisted marker across that window so
            # concurrent readers on other connections/processes warn
            # instead of trusting the half-built table. MARK + DELETE live
            # INSIDE the try so the finally clears the marker even if the
            # DELETE/commit itself raises (e.g. SQLITE_FULL) — otherwise a
            # failed rebuild would leave a stuck marker until TTL expiry.
            conn = cache._get_conn()
            had_call_graph = cache.call_graph_built()
            _mark_build_in_progress(conn)
            _clear_call_graph_built(conn)
            try:
                _clear_full_rebuild_rows(cache, conn)
                conn.commit()
                try:
                    from ..knowledge_graph.stores import LadybugKnowledgeGraphStore

                    LadybugKnowledgeGraphStore(cache.project_root).remove_if_exists()
                except Exception:
                    logger.debug("could not invalidate Ladybug mirror", exc_info=True)
            except Exception:
                conn.rollback()
                if had_call_graph:
                    _mark_call_graph_built(conn)
                raise
        conn = cache._get_conn()
        effective_exclude = (
            exclude_patterns
            if exclude_patterns is not None
            else _DEFAULT_EXCLUDE_PATTERNS
        )
        if source_scope is None:
            source_scope = make_source_scope_descriptor(
                no_default_excludes=exclude_patterns is not None,
                exclude_patterns=tuple(sorted(effective_exclude))
                if exclude_patterns is not None
                else (),
                certification_max_files=max_files,
            )
        validate_full_index_source_scope(source_scope, effective_exclude, max_files)
        stats, candidates, count = walk_and_partition(
            cache,
            conn,
            max_files,
            force,
            activation_enabled,
            _walk_source_files,
            _language_from_ext,
            _AST_CACHE_EXTRACTOR_VERSION,
            _make_error_entry,
            language_filter,
            effective_exclude,
            candidate_snapshot,
        )
        candidate_fingerprints = (
            {
                entry.abs_path: cast(IndexFileFingerprint, entry.fingerprint)
                for entry in candidate_snapshot.selected_entries
            }
            if candidate_snapshot is not None
            else {}
        )
        workers = cache._resolve_worker_count(workers, candidates)
        if workers and workers >= 2 and len(candidates) >= 2:
            results = index_parallel(cache, candidates, workers, candidate_fingerprints)
        else:
            from .extraction import _worker_index_file

            results = [
                _worker_index_file(
                    (
                        path,
                        cache.project_root,
                        language,
                        candidate_fingerprints.get(path),
                    )
                )
                for path, language in candidates
            ]
        indexed_at = datetime.now(timezone.utc).isoformat()
        from .. import ast_cache as _ast_cache_mod

        snapshot_entries = (
            {entry.rel_path: entry for entry in candidate_snapshot.selected_entries}
            if candidate_snapshot is not None
            else None
        )
        result_guard = (
            partial(
                _snapshot_result_is_stable,
                entries=snapshot_entries,
                stats=stats,
                cache=cache,
                conn=conn,
            )
            if snapshot_entries is not None
            else None
        )
        batch_guard = (
            partial(
                _revalidate_snapshot_batch,
                cache=cache,
                conn=conn,
                entries=snapshot_entries,
                stats=stats,
            )
            if snapshot_entries is not None
            else None
        )
        _ast_cache_mod._commit_index_results(
            conn,
            results,
            stats,
            partial(
                insert_index_row,
                cache,
                conn,
                extractor_version=_AST_CACHE_EXTRACTOR_VERSION,
            ),
            indexed_at,
            activation_enabled,
            result_guard=result_guard,
            batch_guard=batch_guard,
        )
        if snapshot_entries is not None:
            _revalidate_committed_snapshot(
                cache=cache,
                conn=conn,
                entries=snapshot_entries,
                stats=stats,
            )
        if stats["changed_during_run"] > 0:
            _clear_call_graph_built(conn)
        stats["total_files"] = count
        stats["workers"] = workers
        if (
            candidate_snapshot is not None
            and not candidate_snapshot.truncated_by_max_files
            and candidate_snapshot.errors == 0
            and stats.get("changed_during_run", 0) == 0
        ):
            stats["pruned"] = _prune_to_selected_scope(cache, conn, candidate_snapshot)
        # A missing marker is persisted evidence that a previous backfill did
        # not converge. Fully cached retries must run the complete chain again.
        needs_backfill = bool(
            stats["indexed"] > 0
            or stats.get("pruned", 0) > 0
            or not _call_graph_marker_is_built(conn)
        )
        if needs_backfill:
            _clear_call_graph_built(conn)
            post_index_backfill(cache, stats)
            if stats.get("backfill_errors", 0) == 0 and _candidate_paths_are_exact(
                conn, candidate_snapshot, stats
            ):
                try:
                    _mark_call_graph_built_strict(conn)
                except sqlite3.OperationalError:
                    logger.warning(
                        "call-graph marker certification failed", exc_info=True
                    )
                    stats["backfill_errors"] = stats.get("backfill_errors", 0) + 1
                    stats["manifest_warning"] = "CALL_GRAPH_MARKER_CERTIFICATION_FAILED"
                    _clear_call_graph_built(conn)
            else:
                _clear_call_graph_built(conn)
        if force:
            stats["db_maintenance"] = (
                _ast_cache_mod._reclaim_storage_after_full_rebuild(conn, cache.db_path)
            )
        _update_authoritative_manifest(cache, candidate_snapshot, stats, source_scope)
        return stats
    finally:
        if force:
            _clear_build_in_progress(cache._get_conn())


def _call_graph_marker_is_built(conn: sqlite3.Connection) -> bool:
    """Require the persisted success marker; derived rows alone are not proof."""
    try:
        row = conn.execute(
            "SELECT built FROM ast_call_graph_state WHERE id = 1"
        ).fetchone()
        incomplete = conn.execute(
            "SELECT 1 FROM ast_call_graph_state WHERE id = 2"
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    return bool(row and int(row[0]) == 1 and incomplete is None)


def _prune_to_selected_scope(
    cache: Any, conn: sqlite3.Connection, candidate: IndexCandidateSnapshot
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
            _discard_snapshot_generation(cache, conn, rel_path)
        _clear_call_graph_built_strict(conn)
    except Exception:
        conn.rollback()
        raise
    return len(stale)


def _candidate_paths_are_exact(
    conn: sqlite3.Connection,
    candidate: IndexCandidateSnapshot | None,
    stats: Mapping[str, Any],
) -> bool:
    paths = {
        _normalize_relative_path(str(row[0]))
        for row in conn.execute("SELECT file_path FROM ast_index")
    }
    if candidate is None:
        return (
            bool(paths)
            and not stats.get("truncated_by_max_files", False)
            and not (stats.get("errors", 0) or stats.get("skipped", 0))
        )
    selected = {entry.rel_path for entry in candidate.selected_entries}
    return bool(
        not candidate.truncated_by_max_files
        and candidate.errors == 0
        and stats.get("errors", 0) == 0
        and stats.get("changed_during_run", 0) == 0
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
    source_certification_supported = os.name == "posix" and os.path.exists("/dev/fd")
    exact_paths = bool(
        source_certification_supported
        and candidate_snapshot is not None
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
            # The stamper rolls back its epoch and conditionally removes only
            # the stale manifest it observed.  Do not race a later certifier
            # with an unconditional delete here.
            logger.warning(
                "index snapshot manifest certification failed", exc_info=True
            )
            stats["manifest_warning"] = "INDEX_MANIFEST_CERTIFICATION_FAILED"
            return
    if not source_certification_supported:
        stats["manifest_warning"] = "SOURCE_SCOPE_UNSUPPORTED"
    elif exact_paths and not _call_graph_marker_is_built(conn):
        stats["manifest_warning"] = "CALL_GRAPH_INCOMPLETE"
    conn.execute("DELETE FROM ast_index_snapshot_manifest")
    conn.commit()


def _record_backfill_result(stats: dict[str, Any], key: str, result: Any) -> None:
    """Keep a helper diagnostic and fail closed unless it reports zero errors."""
    stats[key] = result
    if not isinstance(result, Mapping) or result.get("errors", 0) != 0:
        stats["backfill_errors"] += 1


def post_index_backfill(
    cache: Any,
    stats: dict[str, Any],
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
        from ..knowledge_graph.stores import LadybugKnowledgeGraphStore

        # SQLite is the canonical graph index. LadybugDB is a derived projection
        # and must never survive an SQLite update as an implicitly fresh mirror.
        ladybug_removed = LadybugKnowledgeGraphStore(
            cache.project_root
        ).remove_if_exists()
        if ladybug_removed:
            stats["knowledge_graph"] = {"ladybug_stale_removed": True}
    except Exception:
        logger.debug("auto knowledge graph build failed", exc_info=True)
