"""Concept-search fallback helpers for chained CodeGraph queries."""

from __future__ import annotations

from typing import Any

from . import _codegraph_explore_helpers as _h


def concept_entries_for_queries(
    cache: Any,
    queries: list[str],
    *,
    project_root: str,
    max_files: int,
) -> list[dict[str, Any]]:
    """Return file-level concept matches for unresolved chain seeds."""
    query_terms, file_tokens = _split_seed_queries(queries)
    if not query_terms and not file_tokens:
        return []
    return _h.concept_search(
        cache,
        query_terms,
        file_tokens,
        project_root,
        max_files,
    )


def symbols_from_concept_entries(
    entries: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Lift nearby concept-search symbols into the query chain state."""
    symbols: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for entry in entries:
        file_path = str(entry.get("file_path") or "")
        language = str(entry.get("language") or "")
        for symbol in entry.get("symbols", []):
            line = int(symbol.get("start_line", 0) or 0)
            name = str(symbol.get("name") or "")
            if not file_path or not line or not name:
                continue
            key = (file_path, line, name)
            if key in seen:
                continue
            seen.add(key)
            symbols.append(
                {
                    "name": name,
                    "kind": symbol.get("kind", "unknown"),
                    "file": file_path,
                    "line": line,
                    "end_line": int(symbol.get("end_line", line) or line),
                    "language": language,
                }
            )
            if len(symbols) >= limit:
                return symbols
    return symbols


def _split_seed_queries(queries: list[str]) -> tuple[list[str], list[str]]:
    query_terms: list[str] = []
    file_tokens: list[str] = []
    seen_terms: set[str] = set()
    seen_files: set[str] = set()
    for query in queries:
        symbols, files = _h.split_query(query)
        for symbol in symbols or [query]:
            token = symbol.strip()
            if token and token not in seen_terms:
                seen_terms.add(token)
                query_terms.append(token)
        for file_token in files:
            token = file_token.strip()
            if token and token not in seen_files:
                seen_files.add(token)
                file_tokens.append(token)
    return query_terms, file_tokens


__all__ = ["concept_entries_for_queries", "symbols_from_concept_entries"]
