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
    int_kw,
    parse_chain,
    step_to_dict,
    string_args,
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
                "explore(), callers(), callees(), related(), include(), sort(), "
                "take(), and answer() in one statement so agents get an answer "
                "pack without 40 separate CLI calls. Example: "
                "search(['Router', 'Handler']).explore().include(callers=True, "
                "complexity=True).sort(by='fan_in', desc=True).answer()."
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
            verdict="INFO" if state.symbols else "NOT_FOUND",
            query=query,
            normalized_chain=[step_to_dict(step) for step in steps],
            symbols=state.symbols[:max_symbols],
            files=state.files[:max_files],
            relationships=state.relationships,
            facets=state.facets or None,
            stats={
                "steps": len(steps),
                "symbols_returned": len(state.symbols),
                "files_returned": len(state.files),
                "facets_returned": len(state.facets),
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
            state.current = _resolve_queries(cache, queries, limit)
            state.add_symbols(state.current)
            return

        if step.name == "explore":
            queries = string_args(step, required=False)
            if queries:
                limit = int_kw(
                    step, "max_symbols", default_max_symbols, _MAX_SYMBOLS_CAP
                )
                state.current = _resolve_queries(cache, queries, limit)
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

        if step.name == "answer":
            return

        raise ValueError(f"unsupported chain step: {step.name}")


class _QueryState:
    def __init__(self) -> None:
        self.current: list[dict[str, Any]] = []
        self.symbols: list[dict[str, Any]] = []
        self.files: list[dict[str, Any]] = []
        self.relationships: dict[str, dict[str, list[dict[str, Any]]]] = {
            "callers": {},
            "callees": {},
        }
        self.facets: dict[str, Any] = {}
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


def _resolve_queries(
    cache: Any, queries: list[str], limit: int
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for query in queries:
        remaining = limit - len(resolved)
        if remaining <= 0:
            break
        resolved.extend(_resolve_query(cache, query, remaining))
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
            if include_code and lines and end_line - start_line <= _MAX_SNIPPET_LINES:
                code = _h.extract_snippet_from_lines(lines, start_line, end_line)
                if code:
                    entry["code"] = code
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
