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

from typing import Any

from ...codegraph_query_backend import CodeGraphQueryBackend
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from . import _codegraph_explore_helpers as _h
from . import _codegraph_query_concepts as _concepts
from . import _codegraph_query_filters as _filters
from ._codegraph_query_compact import (
    compact_facets as _compact_facets,
)
from ._codegraph_query_compact import (
    compact_relationships as _compact_relationships,
)
from ._codegraph_query_compact import (
    compact_symbol as _compact_symbol,
)
from ._codegraph_query_dsl import (
    _ChainStep,
    bool_kw,
    first_int,
    int_kw,
    parse_chain,
    step_to_dict,
    string_args,
)
from ._codegraph_query_facets import (
    affected_tests_facet as _affected_tests_facet,
)
from ._codegraph_query_facets import (
    complexity_facet as _complexity_facet,
)
from ._codegraph_query_facets import (
    health_facet as _health_facet,
)
from ._codegraph_query_facets import (
    risk_facet as _risk_facet,
)
from ._codegraph_query_facets import (
    uml_facet as _uml_facet,
)
from ._codegraph_query_selection import (
    apply_selection_filters as _apply_selection_filters,
)
from ._codegraph_query_selection import (
    filter_concept_entries as _filter_concept_entries,
)
from ._codegraph_query_selection import (
    filter_current_selection as _filter_current_selection,
)
from ._codegraph_query_selection import (
    is_relation_noise_symbol as _is_relation_noise_symbol,
)
from ._codegraph_query_selection import (
    replace_current_selection as _replace_current_selection,
)
from ._codegraph_query_selection import (
    sort_state as _sort_state,
)
from ._codegraph_query_state import _QueryState
from ._codegraph_query_symbols import (
    absolute_path as _absolute_path,  # noqa: F401 — re-exported for tests
)
from ._codegraph_query_symbols import (
    build_file_entries as _build_file_entries,
)
from ._codegraph_query_symbols import (
    dedupe_symbols as _dedupe_symbols,
)
from ._codegraph_query_symbols import (
    drop_test_shadow_symbols as _drop_test_shadow_symbols,
)
from ._codegraph_query_symbols import (
    source_first_symbols as _source_first_symbols,
)
from ._codegraph_query_symbols import (
    source_preference_key as _source_preference_key,
)
from ._codegraph_query_symbols import (
    symbol_key as _symbol_key,
)
from ._codegraph_query_symbols import (
    symbol_key_tuple as _symbol_key_tuple,
)
from ._codegraph_query_symbols import (
    unique_symbol_files as _unique_symbol_files,  # noqa: F401 — re-exported for tests
)
from ._response_builder import build_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_MAX_SYMBOLS_CAP = 50
_MAX_FILES_CAP = 30
_MAX_REL_PER_SYMBOL = 20
_DECLARATION_QUERY_KINDS = frozenset({"class", "enum", "interface", "type"})


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
                "complexity=True).uml().sort(by='fan_in', desc=True).answer(). "
                "sort() accepts: name, file (alias: path), line, kind, fan_in, fan_out, confidence. "
                "confidence reflects BM25 relevance (use desc=True for most-relevant first). "
                "fan_in/fan_out require callers()/callees() to have run first — otherwise 0."
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


# Type alias to avoid deep generic nesting in annotations
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
            if file_tokens:
                item_file = str(item.get("file", "")).lower()
                if not any(ft.lower() in item_file for ft in file_tokens):
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


__all__ = ["CodeGraphQueryTool", "parse_chain"]
