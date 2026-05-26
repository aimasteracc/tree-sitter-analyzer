"""Runtime helpers for the codegraph_query fluent DSL."""

from __future__ import annotations

import os
from typing import Any

from ...utils import setup_logger
from . import _codegraph_explore_helpers as _h
from ._codegraph_query_dsl import _ChainStep, int_kw, step_to_dict

logger = setup_logger(__name__)

MAX_SYMBOLS_CAP = 50
MAX_FILES_CAP = 30
MAX_REL_PER_SYMBOL = 20
MAX_SNIPPET_LINES = 160
MAX_FILE_BYTES = 1_000_000


class QueryState:
    """Mutable selection state for a chained graph query."""

    def __init__(self) -> None:
        self.current: list[dict[str, Any]] = []
        self.symbols: list[dict[str, Any]] = []
        self.files: list[dict[str, Any]] = []
        self.last_query = ""
        self.intent = ""
        self.include_plan = False
        self.answer_requested = False
        self.query_plan: list[dict[str, Any]] = []
        self.relationships: dict[str, dict[str, list[dict[str, Any]]]] = {
            "callers": {},
            "callees": {},
        }
        self._seen_symbols: set[tuple[str, int, str]] = set()
        self._history: list[
            tuple[
                list[dict[str, Any]],
                list[dict[str, Any]],
                list[dict[str, Any]],
                set[tuple[str, int, str]],
            ]
        ] = []

    def add_symbols(self, symbols: list[dict[str, Any]]) -> None:
        for symbol in symbols:
            key = symbol_key_tuple(symbol)
            if key in self._seen_symbols:
                continue
            self._seen_symbols.add(key)
            self.symbols.append(symbol)

    def push_selection(self) -> None:
        self._history.append(
            (
                list(self.current),
                list(self.symbols),
                list(self.files),
                set(self._seen_symbols),
            )
        )

    def restore_selection(self) -> bool:
        if not self._history:
            return False
        self.current, self.symbols, self.files, self._seen_symbols = self._history.pop()
        return True

    def rebuild_seen(self) -> None:
        self._seen_symbols = {symbol_key_tuple(symbol) for symbol in self.symbols}

    def counts(self) -> dict[str, int]:
        return {
            "current": len(self.current),
            "symbols": len(self.symbols),
            "files": len(self.files),
            "caller_edges": sum(len(v) for v in self.relationships["callers"].values()),
            "callee_edges": sum(len(v) for v in self.relationships["callees"].values()),
        }

    def record_step(
        self, step: _ChainStep, before: dict[str, int], warning: str = ""
    ) -> None:
        entry: dict[str, Any] = {
            "step": step_to_dict(step),
            "before": before,
            "after": self.counts(),
        }
        if warning:
            entry["warning"] = warning
        self.query_plan.append(entry)


def resolve_query(cache: Any, query: str, limit: int) -> list[dict[str, Any]]:
    from ...symbol_resolver import SymbolResolver

    resolver = SymbolResolver(cache)
    symbol_tokens, file_tokens = _h.split_query(query)
    if not symbol_tokens:
        symbol_tokens = [query]

    resolved: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for token in symbol_tokens:
        try:
            defs = resolver.resolve(token).definitions
        except Exception as exc:
            logger.debug("codegraph_query resolve(%r) failed: %s", token, exc)
            continue
        for definition in defs:
            if file_tokens and not any(
                file_token.lower() in definition.file.lower()
                for file_token in file_tokens
            ):
                continue
            item = definition.to_dict()
            key = symbol_key_tuple(item)
            if key in seen:
                continue
            seen.add(key)
            resolved.append(item)
            if len(resolved) >= limit:
                return resolved
    return resolved


def relation_step(
    cache: Any,
    state: QueryState,
    *,
    direction: str,
    step: _ChainStep,
) -> list[dict[str, Any]]:
    depth = int_kw(step, "depth", 1, 5)
    limit = int_kw(step, "limit", MAX_REL_PER_SYMBOL, MAX_SYMBOLS_CAP)
    related: list[dict[str, Any]] = []
    for symbol in state.current:
        name = str(symbol.get("name") or "")
        file_path = str(symbol.get("file") or "")
        if not name:
            continue
        if direction == "callers":
            rows = cache.query_callers(name, file_path or None, max_depth=depth) or []
            entries = [
                row_symbol(row, "caller_name", "caller_file", "caller_line")
                for row in rows[:limit]
            ]
        else:
            rows = cache.query_callees(name, file_path or None, max_depth=depth) or []
            entries = [
                row_symbol(row, "callee_name", "callee_file", "callee_line")
                for row in rows[:limit]
            ]
        entries = [entry for entry in entries if entry["name"]]
        source_key = symbol_key(symbol)
        state.relationships[direction][source_key] = entries
        related.extend(entries)
    deduped = dedupe_symbols(related)
    state.add_symbols(deduped)
    return deduped


def row_symbol(
    row: dict[str, Any],
    name_key: str,
    file_key: str,
    line_key: str,
) -> dict[str, Any]:
    return {
        "name": row.get(name_key, ""),
        "kind": "function",
        "file": row.get(file_key, ""),
        "line": row.get(line_key, 0),
        "end_line": row.get(line_key, 0),
        "language": "",
        "depth": row.get("depth", 1),
    }


def build_file_entries(
    *,
    project_root: str,
    symbols: list[dict[str, Any]],
    max_files: int,
    include_code: bool,
) -> list[dict[str, Any]]:
    by_file: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        file_path = str(symbol.get("file") or "")
        if not file_path:
            continue
        by_file.setdefault(file_path, []).append(symbol)

    entries: list[dict[str, Any]] = []
    for file_path, file_symbols in list(by_file.items())[:max_files]:
        abs_path = (
            file_path
            if os.path.isabs(file_path)
            else os.path.join(project_root, file_path)
        )
        size = _h.file_size(abs_path) if include_code else 0
        lines = (
            _h.read_file_lines(abs_path)
            if include_code and 0 < size <= MAX_FILE_BYTES
            else []
        )
        symbol_entries: list[dict[str, Any]] = []
        for symbol in file_symbols:
            entry = {
                "name": symbol.get("name", ""),
                "kind": symbol.get("kind", ""),
                "start_line": symbol.get("line", 0),
                "end_line": symbol.get("end_line", 0),
            }
            start_line = int(symbol.get("line", 0) or 0)
            end_line = int(symbol.get("end_line", start_line) or start_line)
            if include_code and lines:
                snippet_end = min(end_line, start_line + MAX_SNIPPET_LINES - 1)
                code = _h.extract_snippet_from_lines(lines, start_line, snippet_end)
                if code:
                    entry["code"] = code
                    if snippet_end < end_line:
                        entry["truncated"] = True
                        entry["truncated_end_line"] = snippet_end
            symbol_entries.append(entry)
        entries.append(
            {
                "file_path": file_path,
                "language": next(
                    (
                        str(sym.get("language"))
                        for sym in file_symbols
                        if sym.get("language")
                    ),
                    "",
                ),
                "symbols": symbol_entries,
            }
        )
    return entries


def build_concept_file_entries(
    *,
    cache: Any,
    query: str,
    project_root: str,
    max_files: int,
) -> list[dict[str, Any]]:
    symbol_tokens, file_tokens = _h.split_query(query)
    query_terms = symbol_tokens or [query]
    return _h.concept_search(
        cache=cache,
        query_terms=query_terms,
        file_tokens=file_tokens,
        project_root=project_root,
        max_files=max_files,
        max_matches_per_file=8,
    )


def is_broad_query(query: str) -> bool:
    symbol_tokens, _file_tokens = _h.split_query(query)
    return len(symbol_tokens) > 1


def merge_file_entries(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
    max_files: int,
) -> list[dict[str, Any]]:
    merged = list(primary)
    seen = {str(entry.get("file_path") or "") for entry in merged}
    for entry in secondary:
        file_path = str(entry.get("file_path") or "")
        if file_path in seen:
            continue
        merged.append(entry)
        seen.add(file_path)
        if len(merged) >= max_files:
            break
    return merged[:max_files]


def apply_where_filter(state: QueryState, criteria: dict[str, Any]) -> None:
    state.push_selection()
    state.current = filter_symbols(state.current, criteria)
    state.symbols = filter_symbols(state.symbols, criteria)
    state.files = filter_files(state.files, criteria)
    state.rebuild_seen()


def apply_path_filter(state: QueryState, raw_patterns: str) -> None:
    criteria = {"path": raw_patterns}
    state.push_selection()
    state.current = filter_symbols(state.current, criteria)
    state.symbols = filter_symbols(state.symbols, criteria)
    state.files = filter_files(state.files, criteria)
    state.rebuild_seen()


def apply_exclude_tests(state: QueryState) -> None:
    state.push_selection()
    state.current = [s for s in state.current if not is_test_path(str(s.get("file")))]
    state.symbols = [s for s in state.symbols if not is_test_path(str(s.get("file")))]
    state.files = [
        entry
        for entry in state.files
        if not is_test_path(str(entry.get("file_path") or ""))
    ]
    state.rebuild_seen()


def apply_prefer_filter(state: QueryState, criteria: dict[str, Any]) -> None:
    merged = {
        key: value
        for key, value in criteria.items()
        if key in {"kind", "language", "name", "path", "file"}
    }
    if criteria.get("paths") is not None:
        merged["path"] = criteria["paths"]
    if criteria.get("exclude_tests"):
        merged["exclude_tests"] = True
    if not merged:
        return
    state.push_selection()
    state.current = filter_symbols(state.current, merged)
    state.symbols = filter_symbols(state.symbols, merged)
    state.files = filter_files(state.files, merged)
    state.rebuild_seen()


def filter_symbols(
    symbols: list[dict[str, Any]],
    criteria: dict[str, Any],
) -> list[dict[str, Any]]:
    return [symbol for symbol in symbols if symbol_matches(symbol, criteria)]


def filter_files(
    files: list[dict[str, Any]],
    criteria: dict[str, Any],
) -> list[dict[str, Any]]:
    return [entry for entry in files if file_matches(entry, criteria)]


def symbol_matches(symbol: dict[str, Any], criteria: dict[str, Any]) -> bool:
    file_path = str(symbol.get("file") or "")
    if criteria.get("exclude_tests") and is_test_path(file_path):
        return False
    if not matches_value(symbol.get("kind"), criteria.get("kind"), exact=True):
        return False
    if not matches_value(symbol.get("language"), criteria.get("language"), exact=True):
        return False
    if not matches_value(symbol.get("name"), criteria.get("name"), exact=False):
        return False
    return matches_value(file_path, criteria.get("path") or criteria.get("file"))


def file_matches(entry: dict[str, Any], criteria: dict[str, Any]) -> bool:
    file_path = str(entry.get("file_path") or "")
    if criteria.get("exclude_tests") and is_test_path(file_path):
        return False
    if not matches_value(entry.get("language"), criteria.get("language"), exact=True):
        return False
    return matches_value(file_path, criteria.get("path") or criteria.get("file"))


def matches_value(value: Any, expected: Any, *, exact: bool = False) -> bool:
    if expected is None:
        return True
    value_text = str(value or "").lower()
    expected_values = expected_tokens(expected)
    if not expected_values:
        return True
    if exact:
        return value_text in expected_values
    return any(token in value_text for token in expected_values)


def expected_tokens(expected: Any) -> list[str]:
    if isinstance(expected, list | tuple):
        raw_values = [str(item) for item in expected]
    else:
        raw_values = str(expected).replace(",", " ").split()
    return [item.strip().lower() for item in raw_values if item.strip()]


def is_test_path(path: str) -> bool:
    lowered = path.lower()
    basename = os.path.basename(lowered)
    return (
        "/test/" in f"/{lowered}"
        or "/tests/" in f"/{lowered}"
        or "/fixtures/" in f"/{lowered}"
        or basename.startswith("test_")
        or basename.endswith("_test.py")
        or basename.endswith("_test.go")
        or basename.endswith(".test.ts")
        or basename.endswith(".spec.ts")
        or basename.endswith(".test.tsx")
        or basename.endswith(".spec.tsx")
    )


def dedupe_symbols(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int, str]] = set()
    out: list[dict[str, Any]] = []
    for symbol in symbols:
        key = symbol_key_tuple(symbol)
        if key in seen:
            continue
        seen.add(key)
        out.append(symbol)
    return out


def symbol_key(symbol: dict[str, Any]) -> str:
    return f"{symbol.get('file', '')}:{symbol.get('line', 0)}:{symbol.get('name', '')}"


def symbol_key_tuple(symbol: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(symbol.get("file") or ""),
        int(symbol.get("line", 0) or 0),
        str(symbol.get("name") or ""),
    )
