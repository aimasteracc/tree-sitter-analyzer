#!/usr/bin/env python3
"""CodeGraph Query MCP Tool — jQuery-style chained code queries.

This tool is the one-call "answer pack" surface for agents. Instead of
spawning many CLI processes for search → explore → callers → callees, callers
can compose those steps in a tiny chain DSL:

    search("CommandService").explore(max_files=4).callees(depth=1).callers()

The parser is deliberately small and safe: it accepts method calls with literal
positional / keyword arguments only and never evals user input.
"""

from __future__ import annotations

import os
from typing import Any

from ...codegraph_query_backend import CodeGraphQueryBackend
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from . import _codegraph_explore_helpers as _h
from . import _codegraph_query_concepts as _concepts
from . import _codegraph_query_filters as _filters
from ._codegraph_query_dsl import (
    _ChainStep,
    bool_kw,
    first_int,
    int_kw,
    parse_chain,
    step_to_dict,
    string_args,
)
from ._response_builder import build_response
from .base_tool import BaseMCPTool
from .codegraph_visualization_hub import query_flow_uml_facet

logger = setup_logger(__name__)

_MAX_SYMBOLS_CAP = 50
_MAX_FILES_CAP = 30
_MAX_REL_PER_SYMBOL = 20
_MAX_SNIPPET_LINES = 160
_MAX_FILE_BYTES = 1_000_000
_DECLARATION_QUERY_KINDS = frozenset({"class", "enum", "interface", "type"})
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


class CodeGraphQueryTool(BaseMCPTool):
    """MCP Tool: one chained query over the pre-indexed code graph."""

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._cache = None

    def _get_cache(self) -> Any:
        if self._cache is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            from ...ast_cache import ASTCache

            self._cache = ASTCache(self.project_root)
        return self._cache

    def get_cache(self) -> Any:
        """Public alias for _get_cache() — use this instead of accessing _cache directly."""
        return self._get_cache()

    @property
    def cache_initialized(self) -> bool:
        """True if the AST cache has been lazily initialized (i.e. cached)."""
        return self._cache is not None

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_query",
            "description": (
                "jQuery-style chained code graph query. Compose search(), "
                "semantic(), explore(), callers(), callees(), related(), filter(), exclude(), has(), "
                "include(), uml(), sort(), take(), and answer() in one statement so agents "
                "get an answer pack without 40 separate CLI calls. Example: "
                "search(['Router', 'Handler']).has(callees=True, name='authorize')"
                ".explore().include(callers=True, "
                "complexity=True).uml().sort(by='fan_in', desc=True).answer()."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Chain DSL, e.g. search('CommandService').explore("
                        "max_files=4).callees(depth=1).callers(depth=1). "
                        "A plain string is treated as explore('<query>').related()."
                    ),
                },
                "max_symbols": {
                    "type": "integer",
                    "default": 20,
                    "description": "Default symbol cap for search/explore steps",
                },
                "max_files": {
                    "type": "integer",
                    "default": 8,
                    "description": "Default file cap for explore output",
                },
                "include_code": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include source snippets in explore output",
                },
                "compact": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Return a compact answer-pack shape that removes duplicate "
                        "source payloads and trims empty relationship fields"
                    ),
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": "Output format (default: toon)",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        query = str(arguments["query"]).strip()
        output_format = arguments.get("output_format", "toon")
        max_symbols = min(int(arguments.get("max_symbols", 20) or 20), _MAX_SYMBOLS_CAP)
        max_files = min(int(arguments.get("max_files", 8) or 8), _MAX_FILES_CAP)
        include_code = bool(arguments.get("include_code", True))
        compact = bool(arguments.get("compact", False))

        cache = self._get_cache()
        try:
            steps = parse_chain(query)
        except (SyntaxError, ValueError) as exc:
            result = build_response(
                verdict="ERROR",
                success=False,
                query=query,
                error=str(exc),
                normalized_chain=[],
                symbols=[],
                files=[],
                relationships={"callers": {}, "callees": {}},
            )
            return apply_toon_format_to_response(result, output_format)

        state = _QueryState(
            compact=compact,
            backend=CodeGraphQueryBackend(cache),
        )
        warnings: list[str] = []

        for step in steps:
            try:
                self._apply_step(
                    cache=cache,
                    state=state,
                    step=step,
                    default_max_symbols=max_symbols,
                    default_max_files=max_files,
                    default_include_code=include_code,
                )
            except ValueError as exc:
                warnings.append(str(exc))

        files_payload = state.files[:max_files]
        facets_payload = state.facets or None
        relationships_payload = state.relationships
        symbols_payload = state.symbols[:max_symbols]
        if state.compact:
            if state.facets.get("source"):
                files_payload = []
            facets_payload = _compact_facets(state.facets) or None
            relationships_payload = _compact_relationships(state.relationships)
            symbols_payload = [
                _compact_symbol(symbol) for symbol in state.symbols[:max_symbols]
            ]

        has_evidence = bool(state.symbols or state.files)
        result = build_response(
            verdict="INFO" if has_evidence else "NOT_FOUND",
            query=query,
            normalized_chain=[step_to_dict(step) for step in steps],
            symbols=symbols_payload,
            files=files_payload,
            relationships=relationships_payload,
            facets=facets_payload,
            stats={
                "steps": len(steps),
                "symbols_returned": len(state.symbols),
                "files_returned": len(state.files),
                "concept_files_returned": state.concept_files_returned,
                "facets_returned": len(state.facets),
                "compact": state.compact,
                "caller_edges": sum(
                    len(v) for v in state.relationships["callers"].values()
                ),
                "callee_edges": sum(
                    len(v) for v in state.relationships["callees"].values()
                ),
            },
            warnings=warnings or None,
        )
        return apply_toon_format_to_response(result, output_format)

    def _apply_step(
        self,
        *,
        cache: Any,
        state: _QueryState,
        step: _ChainStep,
        default_max_symbols: int,
        default_max_files: int,
        default_include_code: bool,
    ) -> None:
        if step.name == "search":
            queries = string_args(step, required=True)
            limit = int_kw(step, "limit", default_max_symbols, _MAX_SYMBOLS_CAP)
            state.seed_queries = queries
            state.current = _resolve_queries_with_backend(
                _state_backend(state, cache), queries, limit
            )
            state.add_symbols(state.current)
            return

        if step.name == "semantic":
            queries = string_args(step, required=True)
            limit = int_kw(step, "limit", default_max_symbols, _MAX_SYMBOLS_CAP)
            state.seed_queries = queries
            state.current = _semantic_queries_with_backend(
                _state_backend(state, cache), queries, limit
            )
            state.add_symbols(state.current)
            return

        if step.name == "explore":
            queries = string_args(step, required=False)
            if queries:
                limit = int_kw(
                    step, "max_symbols", default_max_symbols, _MAX_SYMBOLS_CAP
                )
                state.seed_queries = queries
                state.current = _resolve_queries_with_backend(
                    _state_backend(state, cache), queries, limit
                )
                state.add_symbols(state.current)
            max_files = int_kw(step, "max_files", default_max_files, _MAX_FILES_CAP)
            max_symbols = int_kw(
                step, "max_symbols", default_max_symbols, _MAX_SYMBOLS_CAP
            )
            include_code = bool_kw(step, "include_code", default_include_code)
            if not state.current:
                _apply_concept_fallback(
                    cache=cache,
                    project_root=self.project_root or "",
                    state=state,
                    max_files=max_files,
                    max_symbols=max_symbols,
                )
            if state.files and state.concept_files_returned:
                return
            state.files = _build_file_entries(
                project_root=self.project_root or "",
                symbols=state.current[:max_symbols],
                max_files=max_files,
                include_code=include_code,
            )
            return

        if step.name == "callers":
            state.current = _relation_step(cache, state, direction="callers", step=step)
            return

        if step.name == "callees":
            state.current = _relation_step(cache, state, direction="callees", step=step)
            return

        if step.name == "related":
            callers = _relation_step(cache, state, direction="callers", step=step)
            original = list(state.current)
            state.current = original
            callees = _relation_step(cache, state, direction="callees", step=step)
            state.current = _dedupe_symbols([*callers, *callees])
            return

        if step.name in {"filter", "where"}:
            _filter_current_selection(state, step, invert=False)
            return

        if step.name in {"exclude", "not"}:
            _filter_current_selection(state, step, invert=True)
            return

        if step.name == "has":
            _filter_selection_by_related_symbols(cache, state, step)
            return

        if step.name == "take":
            limit = first_int(step, default_max_symbols)
            state.current = state.current[:limit]
            state.symbols = state.symbols[:limit]
            return

        if step.name == "sort":
            _sort_state(state, step)
            return

        if step.name in {"include", "with"}:
            _include_facets(
                cache=cache,
                project_root=self.project_root or "",
                state=state,
                step=step,
                default_max_symbols=default_max_symbols,
                default_max_files=default_max_files,
                default_include_code=default_include_code,
            )
            return

        if step.name == "uml":
            direction = str(step.kwargs.get("direction") or "LR")
            max_edges = int_kw(
                step,
                "max_edges",
                int_kw(step, "limit", _MAX_REL_PER_SYMBOL, _MAX_SYMBOLS_CAP),
                _MAX_SYMBOLS_CAP,
            )
            state.facets["uml"] = _uml_facet(
                state,
                direction=direction,
                max_edges=max_edges,
            )
            return

        if step.name == "answer":
            state.compact = bool_kw(step, "compact", state.compact)
            return

        raise ValueError(f"unsupported chain step: {step.name}")


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
        self.relationships: dict[str, dict[str, list[dict[str, Any]]]] = {
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


def _resolve_query(cache: Any, query: str, limit: int) -> list[dict[str, Any]]:
    return _resolve_query_with_backend(
        CodeGraphQueryBackend(cache),
        query,
        limit,
    )


def _state_backend(state: _QueryState, cache: Any) -> CodeGraphQueryBackend:
    if state.backend is None:
        state.backend = CodeGraphQueryBackend(cache)
    return state.backend


def _resolve_query_with_backend(
    backend: CodeGraphQueryBackend, query: str, limit: int
) -> list[dict[str, Any]]:
    _, file_tokens = _h.split_query(query)
    symbol_tokens = _concepts.symbol_candidate_tokens(query)

    resolved: list[tuple[int, dict[str, Any]]] = []
    seen: set[tuple[str, int, str]] = set()
    for token_order, token in enumerate(symbol_tokens):
        try:
            defs = backend.resolve_definitions(token)
        except Exception as exc:
            logger.debug("codegraph_query resolve(%r) failed: %s", token, exc)
            continue
        for item in defs:
            if file_tokens and not any(
                file_token.lower() in str(item.get("file", "")).lower()
                for file_token in file_tokens
            ):
                continue
            key = _symbol_key_tuple(item)
            if key in seen:
                continue
            seen.add(key)
            resolved.append((token_order, item))
    resolved.sort(key=lambda item: (item[0], _source_preference_key(item[1])))
    symbols = [item for _, item in resolved]
    symbols = _filter_declaration_query_symbols(query, symbols)
    if not file_tokens:
        symbols = _drop_test_shadow_symbols(symbols)
    return symbols[:limit]


def _filter_declaration_query_symbols(
    query: str, symbols: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    declared_type = _concepts.declared_type_name(query)
    if not declared_type or not symbols:
        return symbols

    exact_name = declared_type.lower()
    declaration_symbols = [
        symbol
        for symbol in symbols
        if str(symbol.get("name") or "").lower() == exact_name
        and str(symbol.get("kind") or "") in _DECLARATION_QUERY_KINDS
    ]
    if declaration_symbols:
        return declaration_symbols

    if any(str(symbol.get("name") or "").lower() == exact_name for symbol in symbols):
        return []
    return symbols


def _apply_concept_fallback(
    *,
    cache: Any,
    project_root: str,
    state: _QueryState,
    max_files: int,
    max_symbols: int,
) -> None:
    if not state.seed_queries:
        return
    entries = _concepts.concept_entries_for_queries(
        cache,
        state.seed_queries,
        project_root=project_root,
        max_files=max_files,
    )
    if state.selection_filters:
        entries = _filter_concept_entries(entries, state.selection_filters)
    if not entries:
        return
    state.files = entries
    state.concept_files_returned = len(entries)
    state.current = _concepts.symbols_from_concept_entries(
        entries,
        limit=max_symbols,
    )
    state.current = _apply_selection_filters(state.current, state.selection_filters)
    state.add_symbols(state.current)


def _resolve_queries(
    cache: Any, queries: list[str], limit: int
) -> list[dict[str, Any]]:
    backend = CodeGraphQueryBackend(cache)
    return _resolve_queries_with_backend(backend, queries, limit)


def _resolve_queries_with_backend(
    backend: CodeGraphQueryBackend, queries: list[str], limit: int
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for query in queries:
        remaining = limit - len(resolved)
        if remaining <= 0:
            break
        resolved.extend(_resolve_query_with_backend(backend, query, remaining))
        resolved = _dedupe_symbols(resolved)
    return resolved[:limit]


def _semantic_queries_with_backend(
    backend: CodeGraphQueryBackend, queries: list[str], limit: int
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for query in queries:
        remaining = limit - len(resolved)
        if remaining <= 0:
            break
        try:
            resolved.extend(backend.semantic_symbols(query, limit=remaining))
        except Exception as exc:
            logger.debug("codegraph_query semantic(%r) failed: %s", query, exc)
        resolved = _dedupe_symbols(resolved)
    return resolved[:limit]


def _relation_step(
    cache: Any,
    state: _QueryState,
    *,
    direction: str,
    step: _ChainStep,
) -> list[dict[str, Any]]:
    depth = int_kw(step, "depth", 1, 5)
    limit = int_kw(step, "limit", _MAX_REL_PER_SYMBOL, _MAX_SYMBOLS_CAP)
    related: list[dict[str, Any]] = []
    for symbol in state.current:
        entries = _relation_entries_for_symbol(
            cache=cache,
            state=state,
            direction=direction,
            symbol=symbol,
            depth=depth,
            limit=limit,
        )
        if not entries:
            continue
        source_key = _symbol_key(symbol)
        state.relationships[direction][source_key] = list(entries)
        related.extend(entries)
    deduped = _dedupe_symbols(related)
    state.add_symbols(deduped)
    return deduped


def _relation_entries_for_symbol(
    *,
    cache: Any,
    state: _QueryState,
    direction: str,
    symbol: dict[str, Any],
    depth: int,
    limit: int,
) -> list[dict[str, Any]]:
    name = str(symbol.get("name") or "")
    file_path = str(symbol.get("file") or "")
    if not name:
        return []
    cache_key = (direction, name, file_path, depth, limit)
    entries = state.relation_cache.get(cache_key)
    if entries is None:
        entries = _query_relation_entries(
            cache=cache,
            backend=state.backend,
            direction=direction,
            name=name,
            file_path=file_path,
            depth=depth,
            limit=limit,
        )
        state.relation_cache[cache_key] = entries
    return entries


def _query_relation_entries(
    *,
    cache: Any,
    backend: CodeGraphQueryBackend | None = None,
    direction: str,
    name: str,
    file_path: str,
    depth: int,
    limit: int,
) -> list[dict[str, Any]]:
    query_backend = backend or CodeGraphQueryBackend(cache)
    entries = query_backend.relation_entries(
        direction=direction,
        name=name,
        file_path=file_path,
        depth=depth,
        limit=limit,
    )
    return _source_first_symbols(
        entry
        for entry in entries
        if entry["name"] and not _is_relation_noise_symbol(entry)
    )[:limit]


def _filter_current_selection(
    state: _QueryState,
    step: _ChainStep,
    *,
    invert: bool,
) -> None:
    state.selection_filters.append((step, invert))
    selected = _apply_selection_filters(state.current, state.selection_filters)
    _replace_current_selection(state, selected)


def _filter_selection_by_related_symbols(
    cache: Any,
    state: _QueryState,
    step: _ChainStep,
) -> None:
    directions: list[str] = []
    if bool_kw(step, "callers", False):
        directions.append("callers")
    if bool_kw(step, "callees", False):
        directions.append("callees")
    if not directions:
        raise ValueError("has() requires callers=True or callees=True")

    depth = int_kw(step, "depth", 1, 5)
    limit = int_kw(step, "limit", _MAX_REL_PER_SYMBOL, _MAX_SYMBOLS_CAP)
    selected: list[dict[str, Any]] = []
    for symbol in state.current:
        source_key = _symbol_key(symbol)
        matched_any = False
        for direction in directions:
            entries = _relation_entries_for_symbol(
                cache=cache,
                state=state,
                direction=direction,
                symbol=symbol,
                depth=depth,
                limit=limit,
            )
            matches = _filters.filter_symbols(entries, step)
            if matches:
                state.relationships[direction][source_key] = matches
                matched_any = True
        if matched_any:
            selected.append(symbol)

    _replace_current_selection(state, selected)


def _replace_current_selection(
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
    _prune_relationships(
        state.relationships, keep_tuples=keep_tuples, keep_keys=keep_keys
    )


def _apply_selection_filters(
    symbols: list[dict[str, Any]],
    selection_filters: list[tuple[_ChainStep, bool]],
) -> list[dict[str, Any]]:
    selected = list(symbols)
    for step, invert in selection_filters:
        selected = _filters.filter_symbols(selected, step, invert=invert)
    return selected


def _filter_concept_entries(
    entries: list[dict[str, Any]],
    selection_filters: list[tuple[_ChainStep, bool]],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    file_only = _selection_filters_are_file_only(selection_filters)
    for entry in entries:
        symbol_pairs = [
            (_concept_symbol_to_query_symbol(entry, symbol), symbol)
            for symbol in entry.get("symbols", [])
        ]
        kept_symbols = _apply_selection_filters(
            [symbol for symbol, _ in symbol_pairs],
            selection_filters,
        )
        file_matches = _concept_file_matches(entry, selection_filters, file_only)
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


def _concept_file_matches(
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
    return bool(_apply_selection_filters([file_marker], selection_filters))


def _selection_filters_are_file_only(
    selection_filters: list[tuple[_ChainStep, bool]],
) -> bool:
    symbol_fields = {"name", "kind", "language", "regex"}
    return not any(
        symbol_fields.intersection(step.kwargs) for step, _ in selection_filters
    )


def _concept_symbol_to_query_symbol(
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


def _prune_relationships(
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


def _is_relation_noise_symbol(symbol: dict[str, Any]) -> bool:
    name = str(symbol.get("name") or "").strip()
    return name in _RELATION_NOISE_SYMBOLS


def _sort_state(state: _QueryState, step: _ChainStep) -> None:
    sort_by = str(step.kwargs.get("by") or "name")
    if sort_by == "path":
        sort_by = "file"
    allowed = {"name", "file", "line", "kind", "fan_in", "fan_out"}
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
        return symbol.get(sort_by, "")

    state.current = sorted(state.current, key=sort_key, reverse=desc)
    state.symbols = sorted(state.symbols, key=sort_key, reverse=desc)


def _include_facets(
    *,
    cache: Any,
    project_root: str,
    state: _QueryState,
    step: _ChainStep,
    default_max_symbols: int,
    default_max_files: int,
    default_include_code: bool,
) -> None:
    max_files = int_kw(step, "max_files", default_max_files, _MAX_FILES_CAP)
    max_symbols = int_kw(step, "max_symbols", default_max_symbols, _MAX_SYMBOLS_CAP)
    include_code = bool_kw(step, "include_code", default_include_code)
    limit = int_kw(step, "limit", max_symbols, _MAX_SYMBOLS_CAP)

    if bool_kw(step, "callers", False):
        _relation_step(
            cache,
            state,
            direction="callers",
            step=_ChainStep("callers", [], {"limit": limit}),
        )
        state.facets["callers"] = {
            "status": "included",
            "edges": state.relationships["callers"],
        }
    if bool_kw(step, "callees", False):
        _relation_step(
            cache,
            state,
            direction="callees",
            step=_ChainStep("callees", [], {"limit": limit}),
        )
        state.facets["callees"] = {
            "status": "included",
            "edges": state.relationships["callees"],
        }
    if bool_kw(step, "source", False):
        if not state.files:
            if not state.current:
                _apply_concept_fallback(
                    cache=cache,
                    project_root=project_root,
                    state=state,
                    max_files=max_files,
                    max_symbols=max_symbols,
                )
            if not state.files or not state.concept_files_returned:
                state.files = _build_file_entries(
                    project_root=project_root,
                    symbols=state.current[:max_symbols],
                    max_files=max_files,
                    include_code=include_code,
                )
        state.facets["source"] = {
            "status": "included",
            "file_count": len(state.files),
            "files": state.files[:max_files],
        }
    if bool_kw(step, "complexity", False):
        state.facets["complexity"] = _complexity_facet(
            cache, project_root, state.current[:max_symbols], max_files
        )
    if bool_kw(step, "health", False):
        state.facets["health"] = _health_facet(
            project_root, state.current[:max_symbols], max_files
        )
    if bool_kw(step, "affected_tests", False):
        state.facets["affected_tests"] = _affected_tests_facet(state)
    if bool_kw(step, "risk", False):
        state.facets["risk"] = _risk_facet(state)


def _complexity_facet(
    cache: Any, project_root: str, symbols: list[dict[str, Any]], max_files: int
) -> dict[str, Any]:
    try:
        from ...complexity_heatmap import analyze_file_complexity_from_cache
    except Exception as exc:
        return {"status": "missing", "reason": str(exc)}

    entries: list[dict[str, Any]] = []
    for file_path in _unique_symbol_files(symbols)[:max_files]:
        abs_path = _absolute_path(project_root, file_path)
        try:
            functions = analyze_file_complexity_from_cache(cache, abs_path)
        except Exception as exc:
            entries.append({"file": file_path, "status": "error", "error": str(exc)})
            continue
        if not functions:
            entries.append({"file": file_path, "status": "no_functions"})
            continue
        hotspots = sorted(functions, key=lambda item: item.complexity, reverse=True)[:5]
        entries.append(
            {
                "file": file_path,
                "status": "included",
                "function_count": len(functions),
                "max_complexity": max(item.complexity for item in functions),
                "total_complexity": sum(item.complexity for item in functions),
                "hotspots": [
                    {
                        "name": item.name,
                        "line": item.line,
                        "complexity": item.complexity,
                    }
                    for item in hotspots
                ],
            }
        )
    return {"status": "included", "files": entries}


def _health_facet(
    project_root: str, symbols: list[dict[str, Any]], max_files: int
) -> dict[str, Any]:
    try:
        from ...health_scorer import HealthScorer
    except Exception as exc:
        return {"status": "missing", "reason": str(exc)}

    scorer = HealthScorer()
    entries: list[dict[str, Any]] = []
    for file_path in _unique_symbol_files(symbols)[:max_files]:
        abs_path = _absolute_path(project_root, file_path)
        try:
            score = scorer.score_file(abs_path, fast_dependencies=True)
        except Exception as exc:
            entries.append({"file": file_path, "status": "error", "error": str(exc)})
            continue
        entries.append(
            {
                "file": file_path,
                "status": "included",
                "total": score.total,
                "grade": score.grade,
                "dimensions": score.dimensions,
            }
        )
    return {"status": "included", "files": entries}


def _affected_tests_facet(state: _QueryState) -> dict[str, Any]:
    files = _unique_symbol_files(state.symbols)
    tests = [
        file_path
        for file_path in files
        if "test" in os.path.basename(file_path).lower()
        or "/test" in file_path.replace("\\", "/").lower()
    ]
    return {
        "status": "included" if tests else "missing",
        "files": tests,
        "reason": None if tests else "no test files appeared in the current chain",
    }


def _risk_facet(state: _QueryState) -> dict[str, Any]:
    reasons: list[str] = []
    complexity = state.facets.get("complexity", {})
    for entry in complexity.get("files", []):
        max_complexity = int(entry.get("max_complexity") or 0)
        if max_complexity >= 20:
            reasons.append(f"{entry.get('file')}: critical complexity {max_complexity}")
        elif max_complexity >= 11:
            reasons.append(f"{entry.get('file')}: high complexity {max_complexity}")

    health = state.facets.get("health", {})
    for entry in health.get("files", []):
        if entry.get("grade") in {"D", "F"}:
            reasons.append(f"{entry.get('file')}: health grade {entry.get('grade')}")

    caller_edges = sum(len(v) for v in state.relationships["callers"].values())
    if caller_edges >= 10:
        reasons.append(f"fan-in {caller_edges} across current symbols")

    return {
        "status": "included",
        "level": "review" if reasons else "info",
        "reasons": reasons,
    }


def _uml_facet(
    state: _QueryState,
    *,
    direction: str,
    max_edges: int,
) -> dict[str, Any]:
    return query_flow_uml_facet(
        symbols=state.symbols,
        current=state.current,
        relationships=state.relationships,
        direction=direction,
        max_edges=max_edges,
    )


def _compact_symbol(symbol: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": symbol.get("name", ""),
        "file": symbol.get("file", ""),
        "line": symbol.get("line", 0),
    }
    if symbol.get("kind"):
        entry["kind"] = symbol["kind"]
    if symbol.get("depth"):
        entry["depth"] = symbol["depth"]
    return entry


def _compact_relationships(
    relationships: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {
        direction: _compact_edge_map(edges)
        for direction, edges in relationships.items()
        if edges
    }


def _compact_edge_map(
    edges: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        source_key: [_compact_symbol(entry) for entry in entries]
        for source_key, entries in edges.items()
        if entries
    }


def _compact_facets(facets: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for name, facet in facets.items():
        if name == "source":
            compacted[name] = {
                "status": facet.get("status"),
                "file_count": facet.get("file_count", 0),
                "files": [
                    _compact_file_entry(entry) for entry in facet.get("files", [])
                ],
            }
        elif name in {"callers", "callees"}:
            compacted[name] = {
                "status": facet.get("status"),
                "edges": _compact_edge_map(facet.get("edges", {})),
            }
        elif name == "complexity":
            compacted[name] = _compact_complexity_facet(facet)
        elif name == "health":
            compacted[name] = _compact_health_facet(facet)
        else:
            compacted[name] = facet
    return compacted


def _compact_file_entry(entry: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {
        "file": entry.get("file_path", ""),
        "symbols": [],
    }
    if entry.get("language"):
        compacted["lang"] = entry["language"]
    if entry.get("matches"):
        compacted["matches"] = [
            {
                "line": match.get("line", 0),
                "text": match.get("text", ""),
                "terms": match.get("terms", []),
            }
            for match in entry.get("matches", [])[:5]
        ]
    for symbol in entry.get("symbols", []):
        start_line = int(symbol.get("start_line", 0) or 0)
        end_line = int(symbol.get("end_line", start_line) or start_line)
        symbol_entry: dict[str, Any] = {
            "name": symbol.get("name", ""),
            "lines": f"{start_line}-{end_line}"
            if end_line != start_line
            else start_line,
        }
        if symbol.get("kind"):
            symbol_entry["kind"] = symbol["kind"]
        if symbol.get("code"):
            symbol_entry["code"] = symbol["code"]
        if symbol.get("code_truncated"):
            symbol_entry["code_truncated"] = True
        if symbol.get("code_lines"):
            symbol_entry["code_lines"] = symbol["code_lines"]
        compacted["symbols"].append(symbol_entry)
    return compacted


def _compact_complexity_facet(facet: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": facet.get("status"),
        "files": [
            {
                "file": entry.get("file"),
                "status": entry.get("status"),
                "max": entry.get("max_complexity"),
                "total": entry.get("total_complexity"),
                "hotspots": [
                    {
                        "name": hotspot.get("name"),
                        "line": hotspot.get("line"),
                        "cc": hotspot.get("complexity"),
                    }
                    for hotspot in entry.get("hotspots", [])
                ],
            }
            for entry in facet.get("files", [])
        ],
    }


def _compact_health_facet(facet: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": facet.get("status"),
        "files": [
            {
                "file": entry.get("file"),
                "status": entry.get("status"),
                "total": entry.get("total"),
                "grade": entry.get("grade"),
            }
            for entry in facet.get("files", [])
        ],
    }


def _row_symbol(
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


def _build_file_entries(
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


def _dedupe_symbols(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int, str]] = set()
    out: list[dict[str, Any]] = []
    for symbol in symbols:
        key = _symbol_key_tuple(symbol)
        if key in seen:
            continue
        seen.add(key)
        out.append(symbol)
    return out


def _source_first_symbols(symbols: Any) -> list[dict[str, Any]]:
    return sorted(symbols, key=_source_preference_key)


def _drop_test_shadow_symbols(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_names = {
        str(symbol.get("name") or "").lower()
        for symbol in symbols
        if symbol.get("name")
        and not _is_test_or_fixture_path(str(symbol.get("file") or "").lower())
    }
    if not source_names:
        return symbols
    return [
        symbol
        for symbol in symbols
        if not (
            str(symbol.get("name") or "").lower() in source_names
            and _is_test_or_fixture_path(str(symbol.get("file") or "").lower())
        )
    ]


def _source_preference_key(symbol: dict[str, Any]) -> tuple[int, int, str, int, str]:
    path = str(symbol.get("file") or "")
    normalized = path.replace("\\", "/").lower()
    return (
        1 if _is_test_or_fixture_path(normalized) else 0,
        1 if _is_generated_or_vendor_path(normalized) else 0,
        normalized,
        int(symbol.get("line", 0) or 0),
        str(symbol.get("name") or ""),
    )


def _is_test_or_fixture_path(path: str) -> bool:
    return _filters.is_test_or_fixture_path(path)


def _is_generated_or_vendor_path(path: str) -> bool:
    return _filters.is_generated_or_vendor_path(path)


def _unique_symbol_files(symbols: list[dict[str, Any]]) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        file_path = str(symbol.get("file") or "")
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)
        files.append(file_path)
    return files


def _absolute_path(project_root: str, file_path: str) -> str:
    if os.path.isabs(file_path):
        return file_path
    return os.path.join(project_root, file_path)


def _symbol_key(symbol: dict[str, Any]) -> str:
    return f"{symbol.get('file', '')}:{symbol.get('line', 0)}:{symbol.get('name', '')}"


def _symbol_key_tuple(symbol: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(symbol.get("file") or ""),
        int(symbol.get("line", 0) or 0),
        str(symbol.get("name") or ""),
    )


__all__ = ["CodeGraphQueryTool", "parse_chain"]
