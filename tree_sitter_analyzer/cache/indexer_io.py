"""Focused cache I/O and partition helpers for project indexing."""

from __future__ import annotations

import fnmatch
import json
import os
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    pass

from ..indexing_limits import normalize_index_max_files
from ..indexing_snapshot import (
    IndexCandidateSnapshot,
    IndexFileFingerprint,
    changed_since_snapshot,
    validate_index_candidate_snapshot,
)
from .indexer import (
    _normalize_relative_path,
    _warn_unwired_plugin_extension,
)
from .schema import (
    clear_activation_for_file as _clear_activation_for_file_fn,
)


def check_cache_or_read(
    conn: sqlite3.Connection,
    rel_path: str,
    abs_path: str,
    stat: Any,
    content_hash_fn: Any,
    extractor_version: int,
    *,
    source_code: str | None = None,
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
    if source_code is None:
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
    stat: Any,
    source_code: str,
    content_hash: str,
    extractor_version: int,
    *,
    source_is_frozen: bool = False,
) -> dict[str, Any]:
    """Parse a file and write all cache rows. Returns result dict."""
    from .extraction import (
        _extract_call_edges,
        _extract_imports,
        _extract_structure,
        _extract_symbols,
    )

    result = (
        cache.parser.parse_code(source_code, language, filename=abs_path)
        if source_is_frozen
        else cache.parser.parse_file(abs_path, language)
    )
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
        "incomplete_skips": 0,
        "processed": 0,
        "changed_during_run": 0,
        "changed_during_run_files": [],
        "files": [],
        "activation_enabled": activation_enabled,
        "truncated_by_max_files": False,
    }
    if force:
        indexed_map: dict[str, tuple[Any, ...]] = {}
    elif candidate_snapshot is not None:
        rows = conn.execute(
            "SELECT file_path, mtime_ns, file_size, extractor_version, content_hash "
            "FROM ast_index"
        ).fetchall()
        indexed_map = {
            r["file_path"]: (
                r["mtime_ns"],
                r["file_size"],
                r["extractor_version"],
                r["content_hash"],
            )
            for r in rows
        }
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
                elif language_filter is not None:
                    # A language-scoped run cannot certify the process-global
                    # call-graph marker: skipped languages and their edges are
                    # still part of the persisted global source inventory.
                    stats["incomplete_skips"] += 1
                stats["skipped"] += 1
                continue
            if entry.decision == "error":
                stats["errors"] += 1
                stats["files"].append(
                    make_error_entry(entry.rel_path, entry.reason or "stat failed")
                )
                continue

            change_reason = (
                None if entry.frozen_path is not None else changed_since_snapshot(entry)
            )
            if change_reason is not None:
                stats["skipped"] += 1
                stats["incomplete_skips"] += 1
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
                and (not fingerprint.content_hash or row[3] == fingerprint.content_hash)
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
            stats["incomplete_skips"] += 1
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
    from .write import _clear_symbol_resolver_context

    _clear_symbol_resolver_context()
    conn.execute("DELETE FROM ast_index")
    if cache.fts5_available:
        conn.execute(
            "INSERT INTO ast_symbols_fts(ast_symbols_fts) VALUES('delete-all')"
        )
    _delete_all_rows_if_present(conn, "ast_symbol_rows")
    for table in (
        "ast_symbol_projection_state",
        "ast_imports",
        "ast_symbol_activation",
        "edges",
    ):
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
    frozen_paths: Mapping[str, str] | None = None,
    frozen_identities: Mapping[str, tuple[int, int, int]] | None = None,
    frozen_deadline: float | None = None,
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
            frozen_paths.get(path) if frozen_paths is not None else None,
            frozen_identities.get(path) if frozen_identities is not None else None,
            frozen_deadline,
        )
        for path, language in candidates
    ]
    with ctx.Pool(processes=workers, initializer=_init_worker_parser) as pool:
        return list(pool.imap_unordered(_worker_index_file, args_iter, chunksize=8))
