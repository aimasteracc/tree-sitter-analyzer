#!/usr/bin/env python3
"""
CodeGraph Explore MCP Tool — Bulk-fetch related symbols in one call.

Closes the CodeGraph parity gap for ``codegraph_explore``: instead of
chaining N ``codegraph_navigate`` / ``analyze_code_structure`` calls,
agents pass a space-separated query of symbol names (and optional file
hints) and receive ALL their source snippets, grouped by file, plus a
relationship map showing which returned symbols call which other returned
symbols — all in a single capped response.

Why this tool exists
--------------------
Surveying an unfamiliar area today costs ~8 individual tool calls
(symbol_search → for each hit: codegraph_node + analyze_code_structure).
That's 8× the context cost and 8× the round-trip latency. ``codegraph_explore``
collapses that into one tool call with hard caps so the response never
blows up context: ``maxSymbols=20`` (cap 50), ``maxFiles=12`` (cap 30),
and a 200-line limit per snippet.

Query semantics
---------------
The ``query`` is NOT a natural-language sentence. It's whitespace-tokenised:

* Tokens containing ``/`` or a known file extension → file-path hints
  (case-insensitive substring filter applied AFTER symbol resolution).
* Other tokens (length ≥ 2) → symbol names passed to ``SymbolResolver``.

Verdict semantics
-----------------
The canonical envelope (``_response_builder``) only accepts:
``{SAFE, REVIEW, CAUTION, UNSAFE, INFO, WARN, ERROR, NOT_FOUND}``. The
brief asked for a ``PASS`` verdict on the happy path; since that string
is not canonical, we map success→``INFO`` (the canonicaliser already maps
``"success"``/``"ok"``→``INFO``/``SAFE``, so this matches the established
convention). Other verdicts:

* ``WARN`` — project_root unset or AST cache empty (degraded — hint surfaced).
* ``NOT_FOUND`` — zero symbols matched any query token.
* ``INFO`` — symbols resolved (with or without extractable source).
* ``ERROR`` — exception during resolution (caught and re-emitted).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from . import _codegraph_explore_helpers as _h
from ._response_builder import build_response
from .base_tool import BaseMCPTool

# Helpers live in a sibling module so this file stays under the 500-line
# cap; aliased to the original underscore names so existing test imports
# (`from codegraph_explore_tool import _split_query`) keep working.
_split_query = _h.split_query
_resolve_tokens = _h.resolve_tokens
_language_of = _h.language_of
_signature_from = _h.signature_from
_file_size = _h.file_size
_extract_snippet = _h.extract_snippet

logger = setup_logger(__name__)

# Hard caps — the contract requires these be enforced even if the
# schema's "maximum" is violated by a caller bypassing validation.
_MAX_FILES_CAP = 30
_MAX_SYMBOLS_CAP = 50
_MAX_SNIPPET_LINES = 200  # symbols larger than this get an outline-only entry
_MAX_FILE_BYTES = 1_000_000  # 1MB — skip code extraction for huge files
_MAX_REL_PER_SYMBOL = 5  # cap callers/callees per symbol in the rel map


class CodeGraphExploreTool(BaseMCPTool):
    """MCP Tool: bulk-fetch N related symbols' source + relationship map."""

    def __init__(self, project_root: str | None = None) -> None:
        # Lazy holders — recreated on project_root rebind via the hook.
        self._cache: Any = None
        self._call_graph: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        # Rebinding invalidates any cached AST handle: the new root may
        # point at a totally different SQLite file.
        self._cache = None
        self._call_graph = None

    # ------------------------------------------------------------------
    # MCP definition / schema
    # ------------------------------------------------------------------

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_explore",
            "description": (
                "BULK FETCH N related symbols' source + relationship map in "
                "ONE call (CodeGraph parity). Replaces 8+ chained "
                "codegraph_node / analyze_code_structure calls for "
                "'survey this area' workflows. Query is whitespace-tokenised: "
                "symbol names + optional file-path hints. Capped at "
                "maxSymbols=20 (≤50) and maxFiles=12 (≤30) so the response "
                "never blows up context. Requires ast_cache index "
                "(run codegraph_autoindex mode=warm first)."
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
                        "Space-separated symbol names, file paths, or code "
                        "terms. Examples: 'CodeGraphNavigateTool execute "
                        "call_graph_tool.py', 'ASTCache get_stats "
                        "SymbolResolver'. Use codegraph_symbol_search first "
                        "to find names — query is NOT a natural-language "
                        "sentence."
                    ),
                },
                "maxFiles": {
                    "type": "integer",
                    "default": 12,
                    "minimum": 1,
                    "maximum": 30,
                    "description": (
                        "Max distinct source files to include (default 12, cap 30)"
                    ),
                },
                "maxSymbols": {
                    "type": "integer",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 50,
                    "description": ("Max symbols to resolve (default 20, cap 50)"),
                },
                "includeCode": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Include source snippets (set False for outline-only)"
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

    # ------------------------------------------------------------------
    # Lazy cache helpers (mirror codegraph_navigate_tool pattern)
    # ------------------------------------------------------------------

    def _try_get_cache(self) -> Any:
        # Soft-fail on every degraded condition — the caller sees a WARN
        # verdict with a hint instead of an exception.
        try:
            from ...ast_cache import ASTCache

            if self.project_root is None:
                return None
            cache = ASTCache(self.project_root)
            stats = cache.get_stats()
            if stats.get("total_files", 0) > 0:
                return cache
            # Empty index — close to release the SQLite handle.
            try:
                cache.close()
            except Exception:
                pass
        except Exception as exc:
            logger.debug(f"ASTCache open failed: {exc}")
        return None

    def _get_cache(self) -> Any:
        if self._cache is None:
            self._cache = self._try_get_cache()
        return self._cache

    def _get_call_graph(self, cache: Any) -> Any:
        # Only attempt to build a call graph when the cache is healthy —
        # otherwise the relationship map quietly stays empty.
        if self._call_graph is not None:
            return self._call_graph
        try:
            from ...call_graph import CachedCallGraph, CallGraph

            if cache is not None and self.project_root:
                self._call_graph = CachedCallGraph(self.project_root, cache=cache)
            elif self.project_root:
                self._call_graph = CallGraph(self.project_root)
        except Exception as exc:
            logger.debug(f"Call graph init failed: {exc}")
            self._call_graph = None
        return self._call_graph

    # ------------------------------------------------------------------
    # execute
    # ------------------------------------------------------------------

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        query = arguments["query"].strip()
        # Enforce caps regardless of schema (defensive: callers can bypass
        # the JSON-schema validator when invoking directly from tests).
        max_files = min(int(arguments.get("maxFiles", 12)), _MAX_FILES_CAP)
        max_symbols = min(int(arguments.get("maxSymbols", 20)), _MAX_SYMBOLS_CAP)
        include_code = bool(arguments.get("includeCode", True))
        output_format = arguments.get("output_format", "toon")

        # --- WARN: project_root unset --------------------------------
        if not self.project_root:
            result = build_response(
                verdict="WARN",
                query=query,
                files=[],
                relationship_map={},
                stats={
                    "query_terms": 0,
                    "symbols_resolved": 0,
                    "symbols_returned": 0,
                    "files_returned": 0,
                },
                hint=(
                    "project_root not set — call set_project_path(...) "
                    "or pass project_root to the tool constructor."
                ),
            )
            return apply_toon_format_to_response(result, output_format)

        # --- WARN: AST cache empty -----------------------------------
        cache = self._get_cache()
        if cache is None:
            result = build_response(
                verdict="WARN",
                query=query,
                files=[],
                relationship_map={},
                stats={
                    "query_terms": 0,
                    "symbols_resolved": 0,
                    "symbols_returned": 0,
                    "files_returned": 0,
                },
                hint=(
                    "AST cache empty or unavailable. Build it first: "
                    "codegraph_autoindex mode=warm."
                ),
            )
            return apply_toon_format_to_response(result, output_format)

        # --- Tokenise + resolve --------------------------------------
        symbol_tokens, file_tokens = _split_query(query)

        try:
            from ...symbol_resolver import SymbolResolver

            resolver = SymbolResolver(cache)
            resolved = _resolve_tokens(resolver, symbol_tokens)
        except Exception as exc:  # noqa: BLE001 — emit as ERROR envelope
            logger.warning(f"codegraph_explore resolve failed: {exc}")
            result = build_response(
                verdict="ERROR",
                success=False,
                query=query,
                error=str(exc),
                files=[],
                relationship_map={},
                stats={
                    "query_terms": len(symbol_tokens) + len(file_tokens),
                    "symbols_resolved": 0,
                    "symbols_returned": 0,
                    "files_returned": 0,
                },
            )
            return apply_toon_format_to_response(result, output_format)

        # File-hint filter — case-insensitive substring match. Skipped
        # when no file tokens, otherwise drops definitions in unrelated
        # files so e.g. `query="parse foo.py"` doesn't surface every
        # `parse` in the repo.
        if file_tokens:
            resolved = [
                d
                for d in resolved
                if any(ft.lower() in d.file.lower() for ft in file_tokens)
            ]

        # Stable ordering keeps the response deterministic across runs.
        resolved.sort(key=lambda d: (d.file, d.line))

        # --- NOT_FOUND: zero matches ---------------------------------
        if not resolved:
            result = build_response(
                verdict="NOT_FOUND",
                query=query,
                files=[],
                relationship_map={},
                stats={
                    "query_terms": len(symbol_tokens) + len(file_tokens),
                    "symbols_resolved": 0,
                    "symbols_returned": 0,
                    "files_returned": 0,
                },
                hint=(
                    "no matches — try codegraph_symbol_search first to "
                    "discover symbol names, then re-run codegraph_explore."
                ),
            )
            return apply_toon_format_to_response(result, output_format)

        symbols_resolved = len(resolved)

        # --- Cap symbols + group by file -----------------------------
        capped = resolved[:max_symbols]
        files_map: dict[str, list[Any]] = defaultdict(list)
        for d in capped:
            files_map[d.file].append(d)

        # Cap distinct files. Use insertion order (dict preserves it
        # since 3.7) so the kept files are the ones with the earliest
        # symbols in the sorted list.
        ordered_files = list(files_map.keys())[:max_files]
        kept_symbol_keys: set[tuple[str, int]] = set()

        # Call graph powers the relationship_map AND the per-symbol
        # callers/callees fields — it's useful regardless of includeCode,
        # so we always attempt it. _get_call_graph caches the instance
        # and triggers build() lazily on first lookup; failures degrade
        # silently to an empty relationship_map.
        graph = self._get_call_graph(cache)
        if graph is not None:
            try:
                graph.build()
            except Exception as exc:
                logger.debug(f"call_graph.build failed: {exc}")
                graph = None

        # --- Build file entries --------------------------------------
        file_entries: list[dict[str, Any]] = []
        symbols_returned = 0
        kept_names: set[str] = set()

        for file_path in ordered_files:
            defs = files_map[file_path]
            language = _language_of(defs)
            file_size = _file_size(file_path) if include_code else 0

            symbol_entries: list[dict[str, Any]] = []
            for d in defs:
                kept_symbol_keys.add((d.file, d.line))
                kept_names.add(d.name)
                entry: dict[str, Any] = {
                    "name": d.name,
                    "kind": d.kind,
                    "start_line": d.line,
                    "end_line": d.end_line,
                }
                signature = _signature_from(d)
                if signature:
                    entry["signature"] = signature

                span = max(0, d.end_line - d.line)
                if (
                    include_code
                    and 0 < file_size <= _MAX_FILE_BYTES
                    and span <= _MAX_SNIPPET_LINES
                ):
                    code = _extract_snippet(d.file, d.line, d.end_line)
                    if code:
                        entry["code"] = code

                # Relationship info: callers/callees pulled from graph
                # ONLY if cheap and only the first N. Failures here must
                # not crash the whole response.
                if graph is not None:
                    try:
                        callers = graph.callers_of(d.name, d.file) or []
                        callees = graph.callees_of(d.name, d.file) or []
                    except Exception as exc:
                        logger.debug(f"graph lookup failed for {d.name}: {exc}")
                        callers = []
                        callees = []
                    if callers:
                        entry["callers"] = [
                            c.get("name", "") for c in callers[:_MAX_REL_PER_SYMBOL]
                        ]
                    if callees:
                        entry["callees"] = [
                            c.get("name", "") for c in callees[:_MAX_REL_PER_SYMBOL]
                        ]

                symbol_entries.append(entry)
                symbols_returned += 1

            file_entries.append(
                {
                    "file_path": file_path,
                    "language": language,
                    "symbols": symbol_entries,
                }
            )

        # --- Relationship map: only edges where BOTH ends are in result
        relationship_map: dict[str, list[str]] = {}
        if graph is not None:
            for entry in file_entries:
                for sym in entry["symbols"]:
                    name = sym["name"]
                    targets = [
                        c
                        for c in (sym.get("callees") or [])
                        if c in kept_names and c != name
                    ]
                    if targets:
                        # Preserve order, dedupe.
                        seen: set[str] = set()
                        deduped: list[str] = []
                        for t in targets:
                            if t not in seen:
                                seen.add(t)
                                deduped.append(t)
                        relationship_map[name] = deduped

        # --- Verdict --------------------------------------------------
        # Contract calls for "PASS" on the happy path, but the canonical
        # envelope rejects PASS — see module docstring. We use INFO,
        # which the verdict canonicaliser already maps "success" / "ok"
        # to, keeping us inside the canonical vocabulary.
        any_code = any("code" in s for entry in file_entries for s in entry["symbols"])
        if symbols_returned == 0:
            # Shouldn't happen given the NOT_FOUND check above, but
            # belt-and-braces: schema caps could pin maxSymbols=0.
            verdict = "NOT_FOUND"
            hint = "all matches dropped by maxSymbols cap"
        elif include_code and not any_code:
            # Symbols resolved but every snippet was skipped (too large
            # / file missing). Still INFO — the relationship map is
            # useful even without source.
            verdict = "INFO"
            hint = (
                "matched symbols but no source extracted "
                "(files too large or symbols span >200 lines)"
            )
        else:
            verdict = "INFO"
            hint = None

        stats = {
            "query_terms": len(symbol_tokens) + len(file_tokens),
            "symbols_resolved": symbols_resolved,
            "symbols_returned": symbols_returned,
            "files_returned": len(file_entries),
        }

        fields: dict[str, Any] = {
            "query": query,
            "files": file_entries,
            "relationship_map": relationship_map,
            "stats": stats,
        }
        if hint:
            fields["hint"] = hint

        result = build_response(verdict=verdict, **fields)
        return apply_toon_format_to_response(result, output_format)
