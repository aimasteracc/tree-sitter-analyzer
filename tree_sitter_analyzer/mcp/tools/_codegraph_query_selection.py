"""Selection, filter, prune, and sort utilities for the CodeGraph query DSL.

These helpers mutate or read _QueryState to implement filter(), exclude(),
has(), sort(), and concept-file-matching steps.
"""

from __future__ import annotations

from typing import Any

from . import _codegraph_query_filters as _filters
from ._codegraph_query_dsl import _ChainStep, bool_kw
from ._codegraph_query_state import _QueryState
from ._codegraph_query_symbols import (
    dedupe_symbols as _dedupe_symbols,
)
from ._codegraph_query_symbols import (
    symbol_key as _symbol_key,
)
from ._codegraph_query_symbols import (
    symbol_key_tuple as _symbol_key_tuple,
)

_RELATION_NOISE_SYMBOLS = frozenset(
    {
        # Go builtins frequently appear as callsite pseudo-symbols in call edges.
        "append",
        "cap",
        "clear",
        "close",
        "complex",
        "copy",
        "delete",
        "imag",
        "len",
        "make",
        "new",
        "panic",
        "print",
        "println",
        "real",
        "recover",
        # Python runtime helpers are similarly low-signal for architecture packs.
        "super",
        "super().__init__",
    }
)


def filter_current_selection(
    state: _QueryState,
    step: _ChainStep,
    *,
    invert: bool,
) -> None:
    state.selection_filters.append((step, invert))
    selected = apply_selection_filters(state.current, state.selection_filters)
    replace_current_selection(state, selected)


def replace_current_selection(
    state: _QueryState,
    selected: list[dict[str, Any]],
) -> None:
    state.current = _dedupe_symbols(selected)
    keep_tuples = {_symbol_key_tuple(symbol) for symbol in state.current}
    keep_keys = {_symbol_key(symbol) for symbol in state.current}
    state.symbols = [
        symbol for symbol in state.symbols if _symbol_key_tuple(symbol) in keep_tuples
    ]
    state.reset_seen_symbols(set(keep_tuples))
    state.files = []
    state.concept_files_returned = 0
    prune_relationships(
        state.relationships, keep_tuples=keep_tuples, keep_keys=keep_keys
    )


def apply_selection_filters(
    symbols: list[dict[str, Any]],
    selection_filters: list[tuple[_ChainStep, bool]],
) -> list[dict[str, Any]]:
    selected = list(symbols)
    for step, invert in selection_filters:
        selected = _filters.filter_symbols(selected, step, invert=invert)
    return selected


def filter_concept_entries(
    entries: list[dict[str, Any]],
    selection_filters: list[tuple[_ChainStep, bool]],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    file_only = selection_filters_are_file_only(selection_filters)
    for entry in entries:
        symbol_pairs = [
            (concept_symbol_to_query_symbol(entry, symbol), symbol)
            for symbol in entry.get("symbols", [])
        ]
        kept_symbols = apply_selection_filters(
            [symbol for symbol, _ in symbol_pairs],
            selection_filters,
        )
        file_matches = concept_file_matches(entry, selection_filters, file_only)
        if not file_matches and not kept_symbols:
            continue
        next_entry = dict(entry)
        if not file_matches:
            kept_keys = {_symbol_key_tuple(symbol) for symbol in kept_symbols}
            next_entry["symbols"] = [
                raw
                for symbol, raw in symbol_pairs
                if _symbol_key_tuple(symbol) in kept_keys
            ]
        filtered.append(next_entry)
    return filtered


def concept_file_matches(
    entry: dict[str, Any],
    selection_filters: list[tuple[_ChainStep, bool]],
    file_only: bool,
) -> bool:
    if not file_only:
        return False
    file_marker = {
        "name": "",
        "kind": "file",
        "file": entry.get("file_path", ""),
        "line": 0,
        "language": entry.get("language", ""),
    }
    return bool(apply_selection_filters([file_marker], selection_filters))


def selection_filters_are_file_only(
    selection_filters: list[tuple[_ChainStep, bool]],
) -> bool:
    symbol_fields = {"name", "kind", "language", "regex"}
    return not any(
        symbol_fields.intersection(step.kwargs) for step, _ in selection_filters
    )


def concept_symbol_to_query_symbol(
    entry: dict[str, Any],
    symbol: dict[str, Any],
) -> dict[str, Any]:
    start_line = int(symbol.get("start_line", symbol.get("line", 0)) or 0)
    return {
        "name": symbol.get("name", ""),
        "kind": symbol.get("kind", ""),
        "file": entry.get("file_path", ""),
        "line": start_line,
        "end_line": symbol.get("end_line", start_line),
        "language": entry.get("language", ""),
    }


def prune_relationships(
    relationships: dict[str, dict[str, list[dict[str, Any]]]],
    *,
    keep_tuples: set[tuple[str, int, str]],
    keep_keys: set[str],
) -> None:
    for direction, edge_map in relationships.items():
        pruned: dict[str, list[dict[str, Any]]] = {}
        for source_key, entries in edge_map.items():
            kept_entries = [
                entry for entry in entries if _symbol_key_tuple(entry) in keep_tuples
            ]
            if source_key in keep_keys:
                pruned[source_key] = entries
            elif kept_entries:
                pruned[source_key] = kept_entries
        relationships[direction] = pruned


def is_relation_noise_symbol(symbol: dict[str, Any]) -> bool:
    name = str(symbol.get("name") or "").strip()
    return name in _RELATION_NOISE_SYMBOLS


def sort_state(state: _QueryState, step: _ChainStep) -> None:
    sort_by = str(step.kwargs.get("by") or "name")
    if sort_by == "path":
        sort_by = "file"
    allowed = {"name", "file", "line", "kind", "fan_in", "fan_out", "confidence"}
    if sort_by not in allowed:
        raise ValueError(f"sort() unsupported field: {sort_by}")
    desc = bool_kw(step, "desc", False)
    fan_in = {
        key: len(entries) for key, entries in state.relationships["callers"].items()
    }
    fan_out = {
        key: len(entries) for key, entries in state.relationships["callees"].items()
    }

    def sort_key(symbol: dict[str, Any]) -> Any:
        if sort_by == "fan_in":
            return fan_in.get(_symbol_key(symbol), 0)
        if sort_by == "fan_out":
            return fan_out.get(_symbol_key(symbol), 0)
        if sort_by == "confidence":
            return float(symbol.get("confidence", 0.0))
        return symbol.get(sort_by, "")

    state.current = sorted(state.current, key=sort_key, reverse=desc)
    state.symbols = sorted(state.symbols, key=sort_key, reverse=desc)
