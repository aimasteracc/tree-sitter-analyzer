"""Cascade symbol search helpers for :mod:`tree_sitter_analyzer.ast_cache`."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from ..utils.test_detection import query_wants_tests, rank_tier
from .query import fts_search_ranked

_KIND_BONUS = {
    "class": 0.08,
    "function": 0.08,
    "method": 0.08,
    "type": 0.06,
    "constant": 0.04,
    "variable": 0.03,
    "import": -0.08,
}


def search_symbols_cascade(
    conn: sqlite3.Connection,
    query: str,
    language: str | None = None,
    limit: int = 100,
    fts5_available: bool = True,
) -> list[dict[str, Any]]:
    """Cascade symbol search: exact -> FTS5 -> LIKE -> fuzzy edit distance.

    Returned rows include ``match_tier`` plus a rescored ``relevance_score``.
    The fuzzy tier catches small typos and casing/boundary mismatches such as
    ``HandlerFunc`` matching ``handleFunc``.

    Test-file demotion is the PRIMARY sort key (issue #607): the fts5 tier
    feeds from ``fts_search_ranked`` which already demotes test files, but a
    final re-sort by pure relevance_score let long descriptive ``test_*``
    names (better BM25 on conceptual queries) re-bury every production
    symbol below the truncation window. Demotion is skipped when the query
    itself asks about tests (``query_wants_tests``).
    """
    query = query.strip()
    if not query or limit <= 0:
        return []

    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()

    _extend_results(
        results, seen, _exact_rows(conn, query, language), query, "exact", 0.82
    )

    if fts5_available and len(query) >= 2 and len(results) < limit:
        for row in fts_search_ranked(conn, query, language, limit * 2):
            _add_result(
                results,
                seen,
                row,
                query,
                "fts5",
                float(row.get("relevance_score", 0.5)) * 0.75,
            )

    if len(query) >= 2 and len(results) < limit:
        _extend_results(
            results,
            seen,
            _like_rows(conn, query, language, limit * 3),
            query,
            "like",
            0.42,
        )

    if len(query) >= 3 and len(results) < limit:
        _extend_fuzzy_results(
            conn,
            query,
            language,
            limit,
            results,
            seen,
        )

    _apply_file_colocation_bonus(results)
    wants_tests = query_wants_tests(query)
    results.sort(
        key=lambda row: (
            # Negated because of reverse=True: production (tier 0) first.
            -rank_tier(str(row.get("file", "")), wants_tests=wants_tests),
            float(row.get("relevance_score", 0.0)),
            _tier_rank(str(row.get("match_tier", ""))),
            str(row.get("name", "")),
        ),
        reverse=True,
    )
    return results[:limit]


def _exact_rows(
    conn: sqlite3.Connection, query: str, language: str | None
) -> list[sqlite3.Row]:
    if language:
        return conn.execute(
            "SELECT r.name, r.kind, r.file_path AS file, r.language, r.line, r.end_line "
            "FROM ast_symbol_rows r "
            "WHERE r.name = ? AND r.language = ? "
            "ORDER BY CASE r.kind WHEN 'class' THEN 0 WHEN 'function' THEN 1 "
            "WHEN 'method' THEN 2 ELSE 3 END, r.file_path, r.line",
            (query, language),
        ).fetchall()
    return conn.execute(
        "SELECT r.name, r.kind, r.file_path AS file, r.language, r.line, r.end_line "
        "FROM ast_symbol_rows r "
        "WHERE r.name = ? "
        "ORDER BY CASE r.kind WHEN 'class' THEN 0 WHEN 'function' THEN 1 "
        "WHEN 'method' THEN 2 ELSE 3 END, r.file_path, r.line",
        (query,),
    ).fetchall()


def _like_rows(
    conn: sqlite3.Connection,
    query: str,
    language: str | None,
    limit: int,
) -> list[sqlite3.Row]:
    query_lower = query.lower()
    try:
        if language:
            return conn.execute(
                "SELECT r.name, r.kind, r.file_path AS file, r.language, r.line, r.end_line "
                "FROM ast_symbol_rows r "
                "WHERE LOWER(r.name) LIKE ? AND r.language = ? "
                "ORDER BY r.file_path, r.line LIMIT ?",
                (f"%{query_lower}%", language, limit),
            ).fetchall()
        return conn.execute(
            "SELECT r.name, r.kind, r.file_path AS file, r.language, r.line, r.end_line "
            "FROM ast_symbol_rows r "
            "WHERE LOWER(r.name) LIKE ? "
            "ORDER BY r.file_path, r.line LIMIT ?",
            (f"%{query_lower}%", limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def _fuzzy_rows(
    conn: sqlite3.Connection,
    language: str | None,
    limit: int,
) -> list[sqlite3.Row]:
    try:
        if language:
            return conn.execute(
                "SELECT r.name, r.kind, r.file_path AS file, r.language, r.line, r.end_line "
                "FROM ast_symbol_rows r WHERE r.language = ? "
                "ORDER BY r.file_path, r.line LIMIT ?",
                (language, limit),
            ).fetchall()
        return conn.execute(
            "SELECT r.name, r.kind, r.file_path AS file, r.language, r.line, r.end_line "
            "FROM ast_symbol_rows r ORDER BY r.file_path, r.line LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def _extend_results(
    results: list[dict[str, Any]],
    seen: set[tuple[str, str, int]],
    rows: list[sqlite3.Row],
    query: str,
    tier: str,
    base_score: float,
) -> None:
    for row in rows:
        _add_result(results, seen, row, query, tier, base_score)


def _extend_fuzzy_results(
    conn: sqlite3.Connection,
    query: str,
    language: str | None,
    limit: int,
    results: list[dict[str, Any]],
    seen: set[tuple[str, str, int]],
) -> None:
    query_norm = _normalise_symbol(query)
    if not query_norm:
        return
    for row in _fuzzy_rows(conn, language, max(limit * 30, 300)):
        name = str(row["name"])
        distance = _bounded_levenshtein(_normalise_symbol(name), query_norm, 2)
        if distance > 2:
            continue
        score = 0.36 - (distance * 0.08)
        _add_result(results, seen, row, query, "fuzzy", score)
        if len(results) >= limit * 3:
            return


def _add_result(
    results: list[dict[str, Any]],
    seen: set[tuple[str, str, int]],
    row: sqlite3.Row | dict[str, Any],
    query: str,
    tier: str,
    base_score: float,
) -> None:
    line = int(_row_get(row, "line", 0))
    key = (str(_row_get(row, "name", "")), str(_row_get(row, "file", "")), line)
    if key in seen:
        return
    seen.add(key)
    result = {
        "name": _row_get(row, "name", ""),
        "kind": _row_get(row, "kind", ""),
        "file": _row_get(row, "file", ""),
        "language": _row_get(row, "language", ""),
        "line": line,
        "end_line": _row_get(row, "end_line", 0),
        "match_tier": tier,
    }
    result["relevance_score"] = _score_result(result, query, base_score)
    results.append(result)


def _row_get(row: sqlite3.Row | dict[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _score_result(row: dict[str, Any], query: str, base_score: float) -> float:
    query_bonus = _name_match_bonus(str(row["name"]), query)
    score = base_score + _KIND_BONUS.get(str(row["kind"]), 0.0) + query_bonus
    return round(max(0.0, min(1.0, score)), 3)


def _name_match_bonus(name: str, query: str) -> float:
    if not query:
        return 0.0
    name_lower = name.lower()
    query_lower = query.lower()
    if name_lower == query_lower:
        return 0.16
    if name_lower.startswith(query_lower):
        return 0.12
    if query_lower in name_lower:
        return 0.07
    if _camel_initials(name).lower().startswith(query_lower):
        return 0.05
    return 0.0


def _apply_file_colocation_bonus(results: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for row in results:
        file_path = str(row.get("file", ""))
        counts[file_path] = counts.get(file_path, 0) + 1
    for row in results:
        bonus = min(0.06, max(0, counts.get(str(row.get("file", "")), 0) - 1) * 0.02)
        row["relevance_score"] = round(
            max(0.0, min(1.0, float(row.get("relevance_score", 0.0)) + bonus)),
            3,
        )


def _tier_rank(tier: str) -> int:
    return {"exact": 4, "fts5": 3, "like": 2, "fuzzy": 1}.get(tier, 0)


def _normalise_symbol(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _camel_initials(value: str) -> str:
    return "".join(ch for ch in value if ch.isupper())


def _bounded_levenshtein(left: str, right: str, max_distance: int) -> int:
    if abs(len(left) - len(right)) > max_distance:
        return max_distance + 1
    previous = list(range(len(right) + 1))
    for i, left_ch in enumerate(left, 1):
        current = [i]
        row_min = i
        for j, right_ch in enumerate(right, 1):
            cost = 0 if left_ch == right_ch else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > max_distance:
            return max_distance + 1
        previous = current
    return previous[-1]
