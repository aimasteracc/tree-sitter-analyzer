"""Read / query helper functions for ASTCache.

Pure functions extracted from ASTCache query methods to reduce
ast_cache.py line count. ASTCache keeps thin wrapper methods that
delegate here.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import TYPE_CHECKING, Any, cast

from ._ast_cache_maintenance import get_db_storage_stats
from .utils.test_detection import query_wants_tests, rank_tier

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# SQL constants re-used by multiple query helpers. CALLS rows live in the
# unified ``edges`` table (B1.3): ``file_path`` is the caller's file (== legacy
# ``caller_file``), ``callee_line`` is the call-site line.
_SQL_COUNT_RESOLVED_EDGES = (
    "SELECT COUNT(*) as c FROM edges "
    "WHERE kind = 'calls' AND callee_resolved_file != ''"
)
_SQL_COUNT_CROSS_FILE_EDGES = (
    "SELECT COUNT(*) as c FROM edges "
    "WHERE kind = 'calls' AND callee_resolved_file != '' "
    "AND callee_resolved_file != file_path"
)
_SQL_UPDATE_CALLEE_RESOLVED = (
    "UPDATE edges SET callee_resolved_file = ? "
    "WHERE kind = 'calls' AND file_path = ? AND caller_line = ? "
    "AND caller_name = ? AND callee_line = ?"
)


def invalidate(
    conn: sqlite3.Connection,
    file_path: str,
    project_root: str,
    fts5_available: bool | None,
) -> bool:
    """Remove all cached rows for file_path. Returns True if a row was deleted."""
    import os

    abs_path = os.path.abspath(file_path)
    try:
        rel = os.path.relpath(abs_path, project_root).replace("\\", "/")
    except ValueError:
        return False
    if fts5_available:
        conn.execute("DELETE FROM ast_symbols_fts WHERE file_path = ?", (rel,))
        conn.execute("DELETE FROM ast_symbol_rows WHERE file_path = ?", (rel,))
    # CALLS rows live in the unified ``edges`` table (B1.3 — no ast_call_edges).
    # Clear them so ``get_call_edges`` reflects the invalidation.
    try:
        conn.execute("DELETE FROM edges WHERE kind = 'calls' AND file_path = ?", (rel,))
    except sqlite3.OperationalError:
        pass
    cursor = conn.execute("DELETE FROM ast_index WHERE file_path = ?", (rel,))
    conn.commit()
    return cursor.rowcount > 0


def lookup(
    conn: sqlite3.Connection,
    file_path: str,
    project_root: str,
) -> dict[str, Any] | None:
    """Look up one file's cached AST metadata. Returns None if not indexed."""
    import os

    abs_path = os.path.abspath(file_path)
    try:
        rel = os.path.relpath(abs_path, project_root).replace("\\", "/")
    except ValueError:
        return None
    row = conn.execute("SELECT * FROM ast_index WHERE file_path = ?", (rel,)).fetchone()
    if row is None:
        return None
    return {
        "file": row["file_path"],
        "content_hash": row["content_hash"],
        "language": row["language"],
        "symbols": json.loads(row["symbols_json"]),
        "imports": json.loads(row["imports_json"]),
        "structure": json.loads(row["structure_json"]),
        "indexed_at": row["indexed_at"],
    }


def fts_search(
    conn: sqlite3.Connection,
    query: str,
    language: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """FTS5-backed symbol search. Returns list of symbol dicts."""
    fts_query = (
        " OR ".join(f'"{term}"' for term in query.split() if term) or f'"{query}"'
    )
    join_sql = (
        "SELECT r.name, r.kind, r.file_path, r.language, r.line, r.end_line "
        "FROM ast_symbols_fts f JOIN ast_symbol_rows r ON f.rowid = r.id "
        "WHERE ast_symbols_fts MATCH ? {lang_clause} ORDER BY rank LIMIT ?"
    )
    if language:
        rows = conn.execute(
            join_sql.format(lang_clause="AND r.language = ?"),
            (fts_query, language, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            join_sql.format(lang_clause=""),
            (fts_query, limit),
        ).fetchall()
    return [
        {
            "name": r["name"],
            "kind": r["kind"],
            "file": r["file_path"],
            "language": r["language"],
            "line": r["line"],
            "end_line": r["end_line"],
        }
        for r in rows
    ]


def _normalize_bm25(raw: float, worst: float, best: float | None = None) -> float:
    """Normalize a raw FTS5 BM25 score to [0.0, 1.0].

    BM25 scores from SQLite FTS5 are negative (more negative = better match).
    ``worst`` is the maximum (least-negative) value in a result set.
    ``best``  is the minimum (most-negative) value in a result set.
    When ``best`` is provided, uses min-max normalization so weak matches
    score near 0.0 instead of capping everything at 1.0.
    Returns 0.0 for anomalous (non-negative) inputs.
    """
    if worst >= 0.0 or raw >= 0.0:
        return 0.0
    if best is not None and best < worst:
        # Min-max normalization: best→1.0, worst→0.0
        span = best - worst  # negative number
        return max(0.0, min(1.0, (raw - worst) / span))
    # Fallback: simple ratio (backwards-compatible)
    return min(1.0, raw / worst)


# Kind-priority weights applied after BM25 normalization.
# Definitions (class/function/method/type) rank above incidental mentions
# (constant, other) which rank above import statements.
_KIND_WEIGHT: dict[str, float] = {
    "class": 1.0,
    "function": 1.0,
    "method": 1.0,
    "type": 0.95,
    "constant": 0.9,
    "other": 0.85,
    "import": 0.6,
}
_KIND_WEIGHT_DEFAULT = 0.85  # fallback for unrecognised kind values

# Test-file demotion runs in Python AFTER the SQL fetch, so a production hit
# that BM25 ranks just outside the caller's ``limit`` window would be truncated
# before it can be promoted above test/fixture matches. Over-fetch a wider band
# of candidates, demote, THEN truncate to ``limit`` — so production symbols that
# lose the raw BM25 race to many test matches can still surface first.
_DEMOTION_OVERFETCH_FACTOR = 4
_DEMOTION_OVERFETCH_FLOOR = 50


def fts_search_ranked(
    conn: sqlite3.Connection,
    query: str,
    language: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """BM25-ranked FTS5 symbol search with kind-priority and test-file demotion.

    Returns dicts with keys: name, kind, file, language, line, end_line, relevance_score.
    relevance_score is in [0.0, 1.0] — 1.0 = best match in this result set.
    After BM25 normalization, a kind-weight multiplier is applied so that
    class/function/method definitions rank above import statements even when
    their raw BM25 score is identical.

    Test-file demotion (consistent with semantic_search.SemanticSymbolSearch):
    Production symbols always rank above test/spec/fixture symbols unless the
    query itself contains test-intent keywords (``query_wants_tests``). Within
    each tier the sort is by relevance_score descending, then file + line for
    determinism.

    Returns [] for queries shorter than 2 characters or on SQLite errors.
    """
    if len(query) < 2:
        return []
    fts_query = (
        " OR ".join(f'"{term}"' for term in query.split() if term) or f'"{query}"'
    )
    # Column weights: name (10x) >> file_path (0.5x), kind (0.5x), language (0.1x).
    # Heavily favours exact function/class name matches over imports that happen
    # to contain the token in their import-path or file-path text.
    join_sql = (
        "SELECT r.name, r.kind, r.file_path AS file, r.language, r.line, r.end_line, "
        "bm25(ast_symbols_fts, 10.0, 0.5, 0.5, 0.1) AS bm25_raw "
        "FROM ast_symbols_fts f JOIN ast_symbol_rows r ON f.rowid = r.id "
        "WHERE ast_symbols_fts MATCH ? {lang_clause} ORDER BY bm25_raw LIMIT ?"
    )
    # Over-fetch so the post-fetch test-demotion can promote production hits
    # that BM25 buried just outside the caller's window (Codex P2 on #316).
    fetch_limit = max(
        limit * _DEMOTION_OVERFETCH_FACTOR, limit + _DEMOTION_OVERFETCH_FLOOR
    )
    try:
        if language:
            rows = conn.execute(
                join_sql.format(lang_clause="AND r.language = ?"),
                (fts_query, language, fetch_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                join_sql.format(lang_clause=""),
                (fts_query, fetch_limit),
            ).fetchall()
    except sqlite3.OperationalError:
        logger.debug("fts_search_ranked: OperationalError — FTS5 table not available")
        return []
    if not rows:
        return []
    raw_scores = [r["bm25_raw"] for r in rows if r["bm25_raw"] < 0]
    worst = max(raw_scores) if raw_scores else 0.0
    best = min(raw_scores) if raw_scores else worst
    results = [
        {
            "name": r["name"],
            "kind": r["kind"],
            "file": r["file"],
            "language": r["language"],
            "line": r["line"],
            "end_line": r["end_line"],
            "relevance_score": _normalize_bm25(r["bm25_raw"], worst, best)
            * _KIND_WEIGHT.get(r["kind"], _KIND_WEIGHT_DEFAULT),
        }
        for r in rows
    ]
    # Primary: test-file demotion tier (0 = production, 1 = test/fixture).
    # Production symbols always rank first unless the query asks about tests.
    # Secondary: relevance_score descending (BM25 + kind weight, best first).
    # Tertiary: file + line for a fully deterministic stable order.
    wants_tests = query_wants_tests(query)
    results.sort(
        key=lambda x: (
            rank_tier(str(x["file"]), wants_tests=wants_tests),
            -x["relevance_score"],
            str(x["file"]),
            int(x["line"] or 0),
            str(x["name"]),
        )
    )
    # Truncate to the caller's window only AFTER demotion, so a promoted
    # production hit is not dropped by the over-fetch band.
    return results[:limit]


def search_symbols_linear(
    conn: sqlite3.Connection,
    query: str,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Linear (non-FTS5) symbol search. Returns list of symbol dicts."""
    if language:
        rows = conn.execute(
            "SELECT file_path, symbols_json, language FROM ast_index WHERE language = ?",
            (language,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT file_path, symbols_json, language FROM ast_index"
        ).fetchall()
    results: list[dict[str, Any]] = []
    query_lower = query.lower()
    for row in rows:
        symbols = json.loads(row["symbols_json"])
        fp, lang = row["file_path"], row["language"]
        for sym in symbols.get("symbols", []):
            name = sym.get("name") or sym.get("text", "")
            if query_lower in name.lower():
                results.append({"file": fp, "language": lang, **sym})
    return results


def get_stats(
    conn: sqlite3.Connection,
    fts5_available: bool | None,
    db_path: str,
) -> dict[str, Any]:
    """Return aggregate index statistics.

    Extended with per-kind and per-language symbol breakdowns
    (CodeGraph parity + edges_by_kind lead).

    New fields added (never raise — degrade to empty dicts):
    - ``symbols_by_kind``     dict[str, int] — from ast_symbol_rows GROUP BY kind
    - ``symbols_by_language`` dict[str, int] — from ast_symbol_rows GROUP BY language
    - ``edges_by_kind``       dict[str, int] — from edges GROUP BY kind (if table exists)
    """
    total = conn.execute("SELECT COUNT(*) as c FROM ast_index").fetchone()["c"]
    by_lang = conn.execute(
        "SELECT language, COUNT(*) as c FROM ast_index GROUP BY language ORDER BY c DESC"
    ).fetchall()
    total_symbols: int | None = None
    if fts5_available:
        try:
            total_symbols = conn.execute(
                "SELECT COUNT(*) as c FROM ast_symbol_rows"
            ).fetchone()["c"]
        except sqlite3.OperationalError:
            total_symbols = None
    if total_symbols is None:
        total_symbols = sum(
            len(json.loads(r["symbols_json"]).get("symbols", []))
            for r in conn.execute("SELECT symbols_json FROM ast_index").fetchall()
        )

    # -- CodeGraph parity: per-kind and per-language breakdowns ---------------
    # Both queries target ast_symbol_rows which is only populated when FTS5
    # is available.  If the table is absent (legacy build or FTS5 disabled),
    # or if fts5_available is falsy, we degrade to empty dicts without raising.
    symbols_by_kind: dict[str, int] = {}
    symbols_by_language: dict[str, int] = {}
    if fts5_available:
        try:
            kind_rows = conn.execute(
                "SELECT kind, COUNT(*) as c FROM ast_symbol_rows GROUP BY kind"
            ).fetchall()
            symbols_by_kind = {r["kind"]: r["c"] for r in kind_rows}
        except sqlite3.OperationalError:
            symbols_by_kind = {}
        try:
            lang_rows = conn.execute(
                "SELECT language, COUNT(*) as c FROM ast_symbol_rows GROUP BY language"
            ).fetchall()
            symbols_by_language = {r["language"]: r["c"] for r in lang_rows}
        except sqlite3.OperationalError:
            symbols_by_language = {}

    # -- Beyond CodeGraph: edge-kind breakdown --------------------------------
    # ``edges`` has an indexed ``kind`` column (idx_edges_kind).  Two
    # GROUP-BY queries are effectively free.  Degrade to {} if the table is
    # absent (no-edges build) without raising.
    edges_by_kind: dict[str, int] = {}
    total_edges = 0
    try:
        edge_kind_rows = conn.execute(
            "SELECT kind, COUNT(*) as c FROM edges GROUP BY kind"
        ).fetchall()
        edges_by_kind = {r["kind"]: r["c"] for r in edge_kind_rows}
        # ``total_edges`` sums ALL kinds so it reconciles with ``edges_by_kind``
        # (Codex P2 on #315): consumers can treat status as an all-edge summary
        # where total_edges == sum(edges_by_kind). The call-edge-only count
        # (graph-density / resolution signal) stays in get_cross_file_stats.
        total_edges = sum(edges_by_kind.values())
    except sqlite3.OperationalError:
        edges_by_kind = {}
        total_edges = 0

    stats: dict[str, Any] = {
        "total_files": total,
        "total_symbols": total_symbols,
        "total_edges": total_edges,
        "by_language": {r["language"]: r["c"] for r in by_lang},
        "symbols_by_kind": symbols_by_kind,
        "symbols_by_language": symbols_by_language,
        "edges_by_kind": edges_by_kind,
        "fts5_available": bool(fts5_available),
    }
    stats.update(get_db_storage_stats(conn, db_path))
    if fts5_available:
        stats["fts_indexed_symbols"] = total_symbols
    return stats


def get_cross_file_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return cross-file edge resolution statistics."""
    try:
        total = conn.execute(
            "SELECT COUNT(*) as c FROM edges WHERE kind = 'calls'"
        ).fetchone()["c"]
        resolved = conn.execute(_SQL_COUNT_RESOLVED_EDGES).fetchone()["c"]
        cross_file = conn.execute(_SQL_COUNT_CROSS_FILE_EDGES).fetchone()["c"]
    except sqlite3.OperationalError:
        return {"total": 0, "resolved": 0, "cross_file": 0, "pct": 0.0}
    pct = (cross_file / total * 100) if total > 0 else 0.0
    return {
        "total": total,
        "resolved": resolved,
        "cross_file": cross_file,
        "pct": round(pct, 2),
    }


def backfill_cross_file_edges(cache: Any, conn: sqlite3.Connection) -> dict[str, Any]:
    """Resolve cross-file call edges and persist callee_resolved_file."""
    from .cross_file_resolver import CrossFileResolver

    resolver = CrossFileResolver(cache)
    resolver.build()
    resolved_edges = resolver.resolve_call_edges()
    total = len(resolved_edges)
    resolved = unchanged = errors = 0
    try:
        for edge in resolved_edges:
            if not edge.callee_resolved_file:
                unchanged += 1
                continue
            params = (
                edge.callee_resolved_file,
                edge.caller_file,
                edge.caller_line,
                edge.caller_name,
                edge.caller_line,
            )
            try:
                cursor = conn.execute(_SQL_UPDATE_CALLEE_RESOLVED, params)
                if cursor.rowcount > 0:
                    resolved += 1
                else:
                    unchanged += 1
            except Exception:
                errors += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "total": total,
        "resolved": resolved,
        "unchanged": unchanged,
        "errors": errors,
    }


def query_callers_enhanced(
    cache: Any,
    callee_name: str,
    callee_file: str | None = None,
    max_depth: int = 1,
) -> list[dict[str, Any]]:
    """Enhanced callers lookup with cross-file import resolution."""
    raw: list[dict[str, Any]] = cast(
        list[dict[str, Any]], cache.query_callers(callee_name, callee_file, max_depth)
    )
    if not raw:
        return raw
    resolver = cache.get_cross_file_resolver()
    for entry in raw:
        if not entry.get("caller_name"):
            callee_line = entry.get("callee_line", 0)
            caller_file = entry.get("caller_file", "")
            name, line = resolver.find_caller_function(callee_line, caller_file)
            if name:
                entry["caller_name"] = name
                entry["caller_line"] = line
    return raw


def query_callees_enhanced(
    cache: Any,
    caller_name: str,
    caller_file: str | None = None,
    max_depth: int = 1,
) -> list[dict[str, Any]]:
    """Enhanced callees lookup with cross-file import resolution."""
    raw: list[dict[str, Any]] = cast(
        list[dict[str, Any]], cache.query_callees(caller_name, caller_file, max_depth)
    )
    if not raw:
        return raw
    resolver = cache.get_cross_file_resolver()
    for entry in raw:
        callee_name_val = entry.get("callee_name", "")
        source_file = entry.get("caller_file", "")
        candidates = resolver.resolve_callee(callee_name_val, source_file)
        if candidates:
            entry["callee_resolved_file"] = candidates[0][0]
            entry["confidence"] = candidates[0][1]
    return raw
