"""Bounded legacy symbol aggregation for index snapshot readers."""

from __future__ import annotations

import json
import sqlite3


def fallback_symbol_counts(
    conn: sqlite3.Connection,
    byte_budget: int,
    row_budget: int,
) -> tuple[int, dict[str, int], dict[str, int]]:
    """Count legacy/no-FTS symbols from bounded primary index JSON rows."""
    total = bytes_seen = 0
    by_kind: dict[str, int] = {}
    by_language: dict[str, int] = {}
    for row in conn.execute(
        "SELECT symbols_json, language FROM ast_index ORDER BY file_path"
    ):
        raw = str(row[0])
        bytes_seen += len(raw.encode("utf-8", "surrogatepass"))
        if bytes_seen > byte_budget:
            raise RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET")
        payload = json.loads(raw)
        symbols = payload.get("symbols", []) if isinstance(payload, dict) else []
        if not isinstance(symbols, list):
            raise ValueError("CORRUPT_INDEX")
        language = str(row[1])
        for symbol in symbols:
            total += 1
            if total > row_budget:
                raise RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET")
            kind = (
                str(symbol.get("kind", "unknown"))
                if isinstance(symbol, dict)
                else "unknown"
            )
            by_kind[kind] = by_kind.get(kind, 0) + 1
            by_language[language] = by_language.get(language, 0) + 1
    return total, dict(sorted(by_kind.items())), dict(sorted(by_language.items()))
