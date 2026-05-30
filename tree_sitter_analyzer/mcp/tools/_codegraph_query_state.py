"""Shared state container for the CodeGraph query DSL execution engine."""

from __future__ import annotations

from typing import Any

from ...codegraph_query_backend import CodeGraphQueryBackend
from ._codegraph_query_dsl import _ChainStep
from ._codegraph_query_symbols import symbol_key_tuple as _symbol_key_tuple

_RelMap = dict[str, dict[str, list[dict[str, Any]]]]


class _QueryState:
    def __init__(
        self,
        *,
        compact: bool = False,
        backend: CodeGraphQueryBackend | None = None,
    ) -> None:
        self.current: list[dict[str, Any]] = []
        self.symbols: list[dict[str, Any]] = []
        self.files: list[dict[str, Any]] = []
        self.relationships: _RelMap = {
            "callers": {},
            "callees": {},
        }
        self.facets: dict[str, Any] = {}
        self._seen_symbols: set[tuple[str, int, str]] = set()
        self.compact = compact
        self.seed_queries: list[str] = []
        self.concept_files_returned = 0
        self.relation_cache: dict[
            tuple[str, str, str, int, int], list[dict[str, Any]]
        ] = {}
        self.selection_filters: list[tuple[_ChainStep, bool]] = []
        self.backend = backend

    def reset_seen_symbols(self, seen: set[tuple[str, int, str]]) -> None:
        """Replace the seen-symbols set (for pruning operations)."""
        self._seen_symbols = seen

    def add_symbols(self, symbols: list[dict[str, Any]]) -> None:
        for symbol in symbols:
            key = _symbol_key_tuple(symbol)
            if key in self._seen_symbols:
                continue
            self._seen_symbols.add(key)
            self.symbols.append(symbol)
