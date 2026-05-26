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

from ..utils.format_helper import apply_toon_format_to_response
from ._codegraph_query_dsl import (
    _ChainStep,
    bool_kw,
    first_int,
    first_str,
    int_kw,
    parse_chain,
    step_to_dict,
)
from ._codegraph_query_runtime import (
    MAX_FILES_CAP,
    MAX_SYMBOLS_CAP,
    QueryState,
    apply_exclude_tests,
    apply_path_filter,
    apply_prefer_filter,
    apply_where_filter,
    build_answer_pack,
    build_concept_file_entries,
    build_file_entries,
    dedupe_symbols,
    is_broad_query,
    merge_file_entries,
    relation_step,
    resolve_query,
)
from ._response_builder import build_response
from .base_tool import BaseMCPTool


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
                "jQuery-style chained code graph query. Compose intent macros "
                "flow(), impact(), ownership() with search(), prefer(), where(), "
                "paths(), exclude_tests(), explore(), callers(), callees(), "
                "related(), take(), end(), why(), and answer() in one statement. "
                "Example: flow('request routing').prefer(paths='src app')."
                "exclude_tests().callees().answer()."
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
                        "Chain DSL, e.g. flow('request routing').prefer("
                        "paths='src app').exclude_tests().callees(depth=1)."
                        "answer(), or impact('CommandService').answer(). "
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
        max_symbols = min(int(arguments.get("max_symbols", 20) or 20), MAX_SYMBOLS_CAP)
        max_files = min(int(arguments.get("max_files", 8) or 8), MAX_FILES_CAP)
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

        state = QueryState()
        warnings: list[str] = []

        for step in steps:
            before = state.counts()
            warning = ""
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
                warning = str(exc)
                warnings.append(warning)
            finally:
                state.record_step(step, before, warning)

        extra_fields: dict[str, Any] = {}
        if state.include_plan or state.answer_requested:
            extra_fields["query_plan"] = state.query_plan
        if state.answer_requested:
            extra_fields["answer_pack"] = build_answer_pack(
                state=state,
                query=query,
                warnings=warnings,
            )

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
                "caller_edges": state.counts()["caller_edges"],
                "callee_edges": state.counts()["callee_edges"],
            },
            warnings=warnings or None,
            **extra_fields,
        )
        return apply_toon_format_to_response(result, output_format)

    def _apply_step(
        self,
        *,
        cache: Any,
        state: QueryState,
        step: _ChainStep,
        default_max_symbols: int,
        default_max_files: int,
        default_include_code: bool,
    ) -> None:
        if step.name == "flow":
            query = _flow_query(first_str(step, required=True))
            state.intent = "flow"
            state.last_query = query
            state.current = resolve_query(cache, query, default_max_symbols)
            state.add_symbols(state.current)
            state.files = _explore_current(
                cache=cache,
                state=state,
                project_root=self.project_root or "",
                max_files=default_max_files,
                max_symbols=default_max_symbols,
                include_code=default_include_code,
            )
            return

        if step.name == "impact":
            query = first_str(step, required=True)
            state.intent = "impact"
            state.last_query = query
            state.current = resolve_query(cache, query, default_max_symbols)
            state.add_symbols(state.current)
            state.files = _explore_current(
                cache=cache,
                state=state,
                project_root=self.project_root or "",
                max_files=default_max_files,
                max_symbols=default_max_symbols,
                include_code=default_include_code,
            )
            relation_step(cache, state, direction="callers", step=step)
            state.current = resolve_query(cache, query, default_max_symbols)
            relation_step(cache, state, direction="callees", step=step)
            return

        if step.name == "ownership":
            query = first_str(step, required=True)
            state.intent = "ownership"
            state.last_query = query
            state.current = resolve_query(cache, query, default_max_symbols)
            state.add_symbols(state.current)
            state.files = _explore_current(
                cache=cache,
                state=state,
                project_root=self.project_root or "",
                max_files=default_max_files,
                max_symbols=default_max_symbols,
                include_code=default_include_code,
            )
            return

        if step.name == "search":
            query = first_str(step, required=True)
            limit = int_kw(step, "limit", default_max_symbols, MAX_SYMBOLS_CAP)
            state.last_query = query
            state.current = resolve_query(cache, query, limit)
            state.add_symbols(state.current)
            return

        if step.name == "prefer":
            apply_prefer_filter(state, step.kwargs)
            return

        if step.name == "where":
            apply_where_filter(state, step.kwargs)
            return

        if step.name == "paths":
            apply_path_filter(state, first_str(step, required=True))
            return

        if step.name == "exclude_tests":
            apply_exclude_tests(state)
            return

        if step.name == "explore":
            query = first_str(step, required=False)
            if query:
                state.last_query = query
                limit = int_kw(
                    step, "max_symbols", default_max_symbols, MAX_SYMBOLS_CAP
                )
                state.current = resolve_query(cache, query, limit)
                state.add_symbols(state.current)
            max_files = int_kw(step, "max_files", default_max_files, MAX_FILES_CAP)
            max_symbols = int_kw(
                step, "max_symbols", default_max_symbols, MAX_SYMBOLS_CAP
            )
            include_code = bool_kw(step, "include_code", default_include_code)
            state.files = build_file_entries(
                project_root=self.project_root or "",
                symbols=state.current[:max_symbols],
                max_files=max_files,
                include_code=include_code,
            )
            if state.last_query and (
                not state.files or is_broad_query(state.last_query)
            ):
                concept_files = build_concept_file_entries(
                    cache=cache,
                    query=state.last_query,
                    project_root=self.project_root or "",
                    max_files=max_files,
                )
                state.files = merge_file_entries(state.files, concept_files, max_files)
            return

        if step.name == "callers":
            state.push_selection()
            state.current = relation_step(cache, state, direction="callers", step=step)
            return

        if step.name == "callees":
            state.push_selection()
            state.current = relation_step(cache, state, direction="callees", step=step)
            return

        if step.name == "related":
            state.push_selection()
            callers = relation_step(cache, state, direction="callers", step=step)
            original = list(state.current)
            state.current = original
            callees = relation_step(cache, state, direction="callees", step=step)
            state.current = dedupe_symbols([*callers, *callees])
            return

        if step.name == "take":
            state.push_selection()
            limit = first_int(step, default_max_symbols)
            state.current = state.current[:limit]
            state.symbols = state.symbols[:limit]
            state.rebuild_seen()
            return

        if step.name == "end":
            if not state.restore_selection():
                raise ValueError("end() has no previous selection to restore")
            return

        if step.name == "why":
            state.include_plan = True
            return

        if step.name == "answer":
            state.answer_requested = True
            return

        raise ValueError(f"unsupported chain step: {step.name}")


def _explore_current(
    *,
    cache: Any,
    state: QueryState,
    project_root: str,
    max_files: int,
    max_symbols: int,
    include_code: bool,
) -> list[dict[str, Any]]:
    files = build_file_entries(
        project_root=project_root,
        symbols=state.current[:max_symbols],
        max_files=max_files,
        include_code=include_code,
    )
    if state.last_query and (not files or is_broad_query(state.last_query)):
        concept_files = build_concept_file_entries(
            cache=cache,
            query=state.last_query,
            project_root=project_root,
            max_files=max_files,
        )
        files = merge_file_entries(files, concept_files, max_files)
    return files


def _flow_query(intent: str) -> str:
    lowered = intent.lower()
    terms = [intent]
    if any(
        token in lowered for token in ("request", "route", "routing", "handler", "http")
    ):
        terms.append(
            "ServeHTTP handleHTTPRequest route router routes handler middleware "
            "dispatch request response context getValue nodeValue"
        )
    if any(token in lowered for token in ("cli", "command", "subcommand")):
        terms.append("main command subcommand handler parser arguments execute run")
    if any(token in lowered for token in ("event", "message", "queue", "worker")):
        terms.append("event message queue worker dispatch handle process consumer")
    return " ".join(terms)


__all__ = ["CodeGraphQueryTool", "parse_chain"]
