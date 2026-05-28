"""Indexing helpers for ASTCache.

Pure functions extracted from ASTCache indexing pipeline methods to
reduce ast_cache.py line count. ASTCache keeps thin wrapper methods
that delegate here.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Extractor version constant — kept in sync with ast_cache.py.
_AST_CACHE_EXTRACTOR_VERSION = 2


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
    from ._ast_extraction import (
        _extract_call_edges,
        _extract_imports,
        _extract_structure,
        _extract_symbols,
    )

    result = cache._parser.parse_file(abs_path, language)
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
    from . import _ast_cache_write as _write

    inserted: list[dict[str, Any]] = (
        _write.write_fts5_symbols(conn, rel_path, language, symbols)
        if cache._fts5_available
        else []
    )
    _write.write_call_edges(conn, rel_path, language, call_edges)
    cache._write_imports_for_file(conn, rel_path, language, imports)
    cache._write_activation_for_file(conn, rel_path, inserted)
    cache._resolve_call_edges_for_file(conn, rel_path)
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
) -> tuple[dict[str, Any], list[tuple[str, str]], int]:
    """Walk source files and partition into (stats, candidates, count)."""
    candidates: list[tuple[str, str]] = []
    already_cached: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "mode_used": "full" if force else "incremental",
        "indexed": 0,
        "cached": 0,
        "errors": 0,
        "skipped": 0,
        "files": [],
        "activation_enabled": activation_enabled,
    }
    count = 0
    for abs_path in walk_fn(cache.project_root):
        if count >= max_files:
            break
        count += 1
        lang = language_fn(abs_path)
        if lang is None:
            stats["skipped"] += 1
            continue
        rel_path = os.path.relpath(abs_path, cache.project_root).replace("\\", "/")
        try:
            stat = os.stat(abs_path)
        except OSError as e:
            stats["errors"] += 1
            stats["files"].append(make_error_entry(rel_path, str(e)))
            continue
        row = conn.execute(
            "SELECT mtime_ns, file_size, extractor_version FROM ast_index WHERE file_path = ?",
            (rel_path,),
        ).fetchone()
        if (
            row is not None
            and row["mtime_ns"] == int(stat.st_mtime_ns)
            and row["file_size"] == stat.st_size
            and row["extractor_version"] >= extractor_version
        ):
            already_cached.append(
                {"file": rel_path, "status": "cached", "reason": "unchanged"}
            )
            continue
        candidates.append((abs_path, lang))
    stats["cached"] += len(already_cached)
    stats["files"].extend(already_cached)
    return stats, candidates, count


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
    if not cache._fts5_available:
        return
    from . import _ast_cache_write as _write

    inserted_symbol_rows = _write.write_fts5_symbols_from_tuples(
        conn, rel_path, r["language"], r["symbol_rows"]
    )
    call_edges = json.loads(r.get("call_edges_json", "[]"))
    _write.write_call_edges(conn, rel_path, r["language"], call_edges)
    imports_list = json.loads(r.get("imports_json", "[]"))
    cache._write_imports_for_file(conn, rel_path, r["language"], imports_list)
    if include_activation:
        cache._write_activation_for_file(conn, rel_path, inserted_symbol_rows)
    else:
        cache._clear_activation_for_file(conn, rel_path)
