"""Local vector-style semantic search over indexed symbols."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")


class SemanticSymbolSearch:
    """Deterministic token-vector search for offline symbol discovery."""

    def __init__(self, cache: Any) -> None:
        self.cache = cache

    # Candidate pool for BM25 pre-filter: 20x the requested limit.
    _BM25_CANDIDATE_MULTIPLIER = 20

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        query_vector = _vectorize(query)
        if not query_vector:
            return []

        # BM25 pre-filter: narrow the candidate pool before cosine reranking.
        # Avoids scanning all 40k+ symbols on every call.  Falls back to the
        # full scan when FTS5 is unavailable or the query is too short.
        candidate_pool = self._candidate_symbols(query, limit)

        scored: list[tuple[float, dict[str, Any]]] = []
        for symbol in candidate_pool:
            haystack = _symbol_text(symbol)
            score = _cosine(query_vector, _vectorize(haystack))
            if score <= 0:
                continue
            result = dict(symbol)
            result["semantic_score"] = round(score, 4)
            scored.append((score, result))

        scored.sort(
            key=lambda item: (
                -item[0],
                str(item[1].get("file", "")),
                int(item[1].get("line", 0) or 0),
                str(item[1].get("name", "")),
            )
        )
        return [item for _score, item in scored[:limit]]

    def _candidate_symbols(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Return a BM25-narrowed candidate pool, or the full symbol set."""
        if len(query) >= 2 and getattr(self.cache, "_fts5_available", False):
            try:
                pool_size = limit * self._BM25_CANDIDATE_MULTIPLIER
                candidates: list[dict[str, Any]] = self.cache.fts_search_ranked(
                    query, limit=pool_size
                )
                if candidates:
                    return candidates
            except Exception:
                pass
        return self._symbols()

    def _symbols(self) -> list[dict[str, Any]]:
        conn = self.cache.get_conn()
        try:
            rows = conn.execute(
                """SELECT name, kind, file_path, language, line, end_line
                   FROM ast_symbol_rows
                   ORDER BY file_path, line, name"""
            ).fetchall()
        except sqlite3.Error:
            return self._symbols_from_json(conn)
        return [
            {
                "name": row["name"],
                "kind": row["kind"],
                "file": row["file_path"],
                "language": row["language"],
                "line": row["line"],
                "end_line": row["end_line"],
            }
            for row in rows
        ]

    def _symbols_from_json(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        try:
            rows = conn.execute(
                "SELECT file_path, symbols_json, language FROM ast_index"
            ).fetchall()
        except sqlite3.Error:
            return []
        symbols: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["symbols_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            for sym in payload.get("symbols", []):
                line = int(sym.get("line", 0) or 0)
                symbols.append(
                    {
                        "name": sym.get("name", sym.get("text", "")),
                        "kind": sym.get("kind", "unknown"),
                        "file": row["file_path"],
                        "language": row["language"],
                        "line": line,
                        "end_line": int(sym.get("end_line", line) or line),
                    }
                )
        return symbols


def _symbol_text(symbol: dict[str, Any]) -> str:
    return " ".join(
        str(symbol.get(key, "")) for key in ("name", "kind", "file", "language")
    )


def _vectorize(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for raw in _TOKEN_RE.findall(_split_identifier_text(text)):
        token = _normalize_token(raw)
        if len(token) < 2:
            continue
        counts[token] += 1
    return counts


def _split_identifier_text(text: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return text.replace("_", " ").replace("-", " ").replace("/", " ").replace(".", " ")


def _normalize_token(token: str) -> str:
    lowered = token.lower()
    for suffix in ("ing", "ers", "er", "ed", "es", "s"):
        if len(lowered) > len(suffix) + 2 and lowered.endswith(suffix):
            return lowered[: -len(suffix)]
    return lowered


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    dot = sum(left[token] * right[token] for token in common)
    if dot == 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm)
