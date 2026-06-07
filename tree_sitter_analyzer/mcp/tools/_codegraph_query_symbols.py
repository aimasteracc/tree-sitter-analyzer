"""Symbol and file-entry utilities for CodeGraph query results."""

from __future__ import annotations

import os
from typing import Any

from . import _codegraph_explore_helpers as _h
from . import _codegraph_query_filters as _filters

# Inline-body cap per symbol in chain/explore output. 160 lines made the
# jQuery-chain explore ~6 KB/symbol — the single biggest driver of the chain
# arm's per-call payload (and the agent-cost gap vs codegraph). 24 lines gives
# the signature + head; the response carries a ``code_lines: a-b of N`` hint so
# the agent reads the exact rest only if it must (matches nav context, #293).
_MAX_SNIPPET_LINES = 24
_MAX_FILE_BYTES = 1_000_000


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
            if include_code and 0 < size <= _MAX_FILE_BYTES
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
                snippet_end = min(
                    end_line, len(lines), start_line + _MAX_SNIPPET_LINES - 1
                )
                code = _h.extract_snippet_from_lines(lines, start_line, snippet_end)
                if code:
                    entry["code"] = code
                if snippet_end < end_line:
                    entry["code_truncated"] = True
                    entry["code_lines"] = f"{start_line}-{snippet_end} of {end_line}"
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


def source_first_symbols(symbols: Any) -> list[dict[str, Any]]:
    return sorted(symbols, key=source_preference_key)


def drop_test_shadow_symbols(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_names = {
        str(symbol.get("name") or "").lower()
        for symbol in symbols
        if symbol.get("name")
        and not _filters.is_test_or_fixture_path(str(symbol.get("file") or "").lower())
    }
    if not source_names:
        return symbols
    return [
        symbol
        for symbol in symbols
        if not (
            str(symbol.get("name") or "").lower() in source_names
            and _filters.is_test_or_fixture_path(str(symbol.get("file") or "").lower())
        )
    ]


def source_preference_key(symbol: dict[str, Any]) -> tuple[int, int, str, int, str]:
    path = str(symbol.get("file") or "")
    normalized = path.replace("\\", "/").lower()
    return (
        1 if _filters.is_test_or_fixture_path(normalized) else 0,
        1 if _filters.is_generated_or_vendor_path(normalized) else 0,
        normalized,
        int(symbol.get("line", 0) or 0),
        str(symbol.get("name") or ""),
    )


def unique_symbol_files(symbols: list[dict[str, Any]]) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        file_path = str(symbol.get("file") or "")
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)
        files.append(file_path)
    return files


def absolute_path(project_root: str, file_path: str) -> str:
    if os.path.isabs(file_path):
        return file_path
    return os.path.join(project_root, file_path)


def symbol_key(symbol: dict[str, Any]) -> str:
    return f"{symbol.get('file', '')}:{symbol.get('line', 0)}:{symbol.get('name', '')}"


def symbol_key_tuple(symbol: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(symbol.get("file") or ""),
        int(symbol.get("line", 0) or 0),
        str(symbol.get("name") or ""),
    )
