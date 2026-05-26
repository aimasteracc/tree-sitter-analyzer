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

from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from . import _codegraph_explore_helpers as _h
from ._codegraph_query_dsl import (
    _ChainStep,
    bool_kw,
    first_int,
    first_str,
    int_kw,
    parse_chain,
    step_to_dict,
)
from ._response_builder import build_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_MAX_SYMBOLS_CAP = 50
_MAX_FILES_CAP = 30
_MAX_REL_PER_SYMBOL = 20
_MAX_SNIPPET_LINES = 160
_MAX_FILE_BYTES = 1_000_000


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

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_query",
            "description": (
                "jQuery-style chained code graph query. Compose search(), "
                "explore(), callers(), callees(), related(), and take() in one "
                "statement so agents get an answer pack without 40 separate "
                "CLI calls. Example: search('CommandService').explore().callees()."
                "callers()."
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

        state = _QueryState()
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

        result = build_response(
            verdict="INFO" if state.symbols or state.files else "NOT_FOUND",
            query=query,
            normalized_chain=[step_to_dict(step) for step in steps],
            symbols=state.symbols[:max_symbols],
            files=state.files[:max_files],
            relationships=state.relationships,
            stats={
                "steps": len(steps),
                "symbols_returned": len(state.symbols),
                "files_returned": len(state.files),
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
            query = first_str(step, required=True)
            limit = int_kw(step, "limit", default_max_symbols, _MAX_SYMBOLS_CAP)
            state.last_query = query
            state.current = _resolve_query(cache, query, limit)
            state.add_symbols(state.current)
            return

        if step.name == "explore":
            query = first_str(step, required=False)
            if query:
                state.last_query = query
                limit = int_kw(
                    step, "max_symbols", default_max_symbols, _MAX_SYMBOLS_CAP
                )
                state.current = _resolve_query(cache, query, limit)
                state.add_symbols(state.current)
            max_files = int_kw(step, "max_files", default_max_files, _MAX_FILES_CAP)
            max_symbols = int_kw(
                step, "max_symbols", default_max_symbols, _MAX_SYMBOLS_CAP
            )
            include_code = bool_kw(step, "include_code", default_include_code)
            state.files = _build_file_entries(
                project_root=self.project_root or "",
                symbols=state.current[:max_symbols],
                max_files=max_files,
                include_code=include_code,
            )
            if state.last_query and (
                not state.files or _is_broad_query(state.last_query)
            ):
                concept_files = _build_concept_file_entries(
                    cache=cache,
                    query=state.last_query,
                    project_root=self.project_root or "",
                    max_files=max_files,
                )
                state.files = _merge_file_entries(state.files, concept_files, max_files)
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

        if step.name == "take":
            limit = first_int(step, default_max_symbols)
            state.current = state.current[:limit]
            state.symbols = state.symbols[:limit]
            return

        raise ValueError(f"unsupported chain step: {step.name}")


class _QueryState:
    def __init__(self) -> None:
        self.current: list[dict[str, Any]] = []
        self.symbols: list[dict[str, Any]] = []
        self.files: list[dict[str, Any]] = []
        self.last_query = ""
        self.relationships: dict[str, dict[str, list[dict[str, Any]]]] = {
            "callers": {},
            "callees": {},
        }
        self._seen_symbols: set[tuple[str, int, str]] = set()

    def add_symbols(self, symbols: list[dict[str, Any]]) -> None:
        for symbol in symbols:
            key = _symbol_key_tuple(symbol)
            if key in self._seen_symbols:
                continue
            self._seen_symbols.add(key)
            self.symbols.append(symbol)


def _resolve_query(cache: Any, query: str, limit: int) -> list[dict[str, Any]]:
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
            key = _symbol_key_tuple(item)
            if key in seen:
                continue
            seen.add(key)
            resolved.append(item)
            if len(resolved) >= limit:
                return resolved
    return resolved


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
        name = str(symbol.get("name") or "")
        file_path = str(symbol.get("file") or "")
        if not name:
            continue
        if direction == "callers":
            rows = cache.query_callers(name, file_path or None, max_depth=depth) or []
            entries = [
                _row_symbol(row, "caller_name", "caller_file", "caller_line")
                for row in rows[:limit]
            ]
        else:
            rows = cache.query_callees(name, file_path or None, max_depth=depth) or []
            entries = [
                _row_symbol(row, "callee_name", "callee_file", "callee_line")
                for row in rows[:limit]
            ]
        entries = [entry for entry in entries if entry["name"]]
        source_key = _symbol_key(symbol)
        state.relationships[direction][source_key] = entries
        related.extend(entries)
    deduped = _dedupe_symbols(related)
    state.add_symbols(deduped)
    return deduped


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
                snippet_end = min(end_line, start_line + _MAX_SNIPPET_LINES - 1)
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


def _build_concept_file_entries(
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


def _is_broad_query(query: str) -> bool:
    symbol_tokens, _file_tokens = _h.split_query(query)
    return len(symbol_tokens) > 1


def _merge_file_entries(
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


def _symbol_key(symbol: dict[str, Any]) -> str:
    return f"{symbol.get('file', '')}:{symbol.get('line', 0)}:{symbol.get('name', '')}"


def _symbol_key_tuple(symbol: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(symbol.get("file") or ""),
        int(symbol.get("line", 0) or 0),
        str(symbol.get("name") or ""),
    )


__all__ = ["CodeGraphQueryTool", "parse_chain"]
