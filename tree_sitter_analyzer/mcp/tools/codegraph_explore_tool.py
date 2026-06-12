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
The ``query`` is whitespace-tokenised:

* Tokens containing ``/`` or a known file extension → file-path hints
  (case-insensitive substring filter applied AFTER symbol resolution).
* Other tokens (length ≥ 2) → symbol names passed to ``SymbolResolver``.
* Multi-term or unresolved symbol queries also get ranked concept matches
  from indexed source files so architecture questions do not fan out into
  raw grep/read loops.
"""

from __future__ import annotations

import os
from collections import defaultdict
from functools import partial
from typing import Any

from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from . import _codegraph_explore_helpers as _h
from ._response_builder import build_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

# Hint strings reused across response builders.
_HINT_NO_ROOT = (
    "project_root not set — call set_project_path(...) "
    "or pass project_root to the tool constructor."
)
_HINT_NO_CACHE = (
    "AST cache empty or unavailable. Build it first: codegraph_autoindex mode=warm."
)
_HINT_NOT_FOUND = (
    "no matches — try codegraph_symbol_search first to "
    "discover symbol names, then re-run codegraph_explore."
)

_EXPLORE_SCHEMA: dict[str, Any] = {
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
        # Wave 1b (audit structure-06): accept the facade's canonical
        # ``symbol`` as an alias for ``query``. Declared here so the facade
        # whitelist does not drop it before this tool can map it.
        "symbol": {
            "type": "string",
            "description": "Alias for query (single symbol name).",
        },
        # #515: the facade documents explore as multi-symbol ("Params:
        # symbols") — accept the list form and join it into the query.
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of symbol names (joined into the query).",
        },
        "maxFiles": {
            "type": "integer",
            "default": 12,
            "minimum": 1,
            "maximum": 30,
            "description": "Max distinct source files to include (default 12, cap 30)",
        },
        "maxSymbols": {
            "type": "integer",
            "default": 20,
            "minimum": 1,
            "maximum": 50,
            "description": "Max symbols to resolve (default 20, cap 50)",
        },
        "includeCode": {
            "type": "boolean",
            "default": True,
            "description": "Include source snippets (set False for outline-only)",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
            "description": "Output format (default: toon)",
        },
    },
    # Wave 1b (audit structure-06): not strictly required — ``query`` may arrive
    # via the ``symbol`` alias, which validate_arguments normalises. A required
    # ``query`` made strict MCP clients reject a valid ``{symbol: X}`` call.
    "required": [],
    "additionalProperties": False,
}


def _empty_stats() -> dict[str, Any]:
    return {
        "query_terms": 0,
        "symbols_resolved": 0,
        "symbols_returned": 0,
        "files_returned": 0,
    }


def _make_stats(
    nterms: int, nresolved: int, nreturned: int, nfiles: int
) -> dict[str, Any]:
    return {
        "query_terms": nterms,
        "symbols_resolved": nresolved,
        "symbols_returned": nreturned,
        "files_returned": nfiles,
    }


def _sym_callees(sym: dict[str, Any]) -> list[str]:
    return sym.get("callees") or []


def _deduped(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in items:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _build_rel_map(
    file_entries: list[dict[str, Any]], kept_names: set[str]
) -> dict[str, list[str]]:
    rel: dict[str, list[str]] = {}
    for entry in file_entries:
        for sym in entry["symbols"]:
            name = sym["name"]
            targets = [c for c in _sym_callees(sym) if c in kept_names and c != name]
            if targets:
                rel[name] = _deduped(targets)
    return rel


def _process_defs(
    defs: list[Any],
    source_lines: list[str],
    file_size: int,
    include_code: bool,
    rel_fn: Any,
    max_file_bytes: int,
    max_snippet_lines: int,
) -> tuple[list[dict[str, Any]], int]:
    symbol_entries: list[dict[str, Any]] = []
    count = 0
    for d in defs:
        entry: dict[str, Any] = {
            "name": d.name,
            "kind": d.kind,
            "start_line": d.line,
            "end_line": d.end_line,
        }
        sig = _h.signature_from(d)
        if sig:
            entry["signature"] = sig
        end_line = d.end_line or d.line
        span = max(0, end_line - d.line)
        if (
            include_code
            and 0 < file_size <= max_file_bytes
            and span <= max_snippet_lines
        ):
            code = _h.extract_snippet_from_lines(source_lines, d.line, end_line)
            if code:
                entry["code"] = code
        callers, callees = rel_fn(d.name, d.file)
        if callers:
            entry["callers"] = callers
        if callees:
            entry["callees"] = callees
        symbol_entries.append(entry)
        count += 1
    return symbol_entries, count


def _build_file_list_results(
    ordered_files: list[str],
    files_map: dict[str, list[Any]],
    include_code: bool,
    source_path_fn: Any,
    rel_fn: Any,
    max_file_bytes: int,
    max_snippet_lines: int,
) -> tuple[list[dict[str, Any]], int, set[str]]:
    file_entries: list[dict[str, Any]] = []
    symbols_returned = 0
    kept_names: set[str] = set()
    for file_path in ordered_files:
        defs = files_map[file_path]
        language = _h.language_of(defs)
        source_path = source_path_fn(file_path)
        file_size = _h.file_size(source_path) if include_code else 0
        source_lines = (
            _h.read_file_lines(source_path)
            if include_code and 0 < file_size <= max_file_bytes
            else []
        )
        sym_entries, sym_count = _process_defs(
            defs,
            source_lines,
            file_size,
            include_code,
            rel_fn,
            max_file_bytes,
            max_snippet_lines,
        )
        kept_names.update(d.name for d in defs)
        file_entries.append(
            {"file_path": file_path, "language": language, "symbols": sym_entries}
        )
        symbols_returned += sym_count
    return file_entries, symbols_returned, kept_names


def _warn_response(
    verdict: str, query: str, stats: dict[str, Any], hint: str, output_format: str
) -> dict[str, Any]:
    result = build_response(
        verdict=verdict,
        query=query,
        files=[],
        relationship_map={},
        stats=stats,
        hint=hint,
    )
    return apply_toon_format_to_response(result, output_format)


def _resolve_error_resp(
    exc: Exception, nterms: int, query: str, output_format: str
) -> dict[str, Any]:
    error_msg = str(exc)
    s = _make_stats(nterms, 0, 0, 0)
    result = build_response(
        verdict="ERROR",
        success=False,
        query=query,
        error=error_msg,
        files=[],
        relationship_map={},
        stats=s,
    )
    return apply_toon_format_to_response(result, output_format)


def _handle_no_resolved(
    concept_entries: list[Any],
    query: str,
    nterms: int,
    output_format: str,
) -> dict[str, Any]:
    if concept_entries:
        payload = _h.concept_response_payload(
            query, concept_entries, query_terms=nterms
        )
        result = build_response(verdict="INFO", **payload)
        return apply_toon_format_to_response(result, output_format)
    s = _make_stats(nterms, 0, 0, 0)
    result = build_response(
        verdict="NOT_FOUND",
        query=query,
        files=[],
        relationship_map={},
        stats=s,
        hint=_HINT_NOT_FOUND,
        # Wave 1b (audit structure-03): also expose the hint as the canonical
        # top-level next_step so the MCP boundary mirrors it into
        # agent_summary.next_step (agents read next_step, not hint).
        next_step=_HINT_NOT_FOUND,
    )
    return apply_toon_format_to_response(result, output_format)


def _init_call_graph(project_root: str, cache: Any) -> Any:
    from ...call_graph import CachedCallGraph, CallGraph

    if cache is not None:
        return CachedCallGraph(project_root, cache=cache)
    return CallGraph(project_root)


def _file_matches_tokens(d: Any, file_tokens: list[str]) -> bool:
    return any(ft.lower() in d.file.lower() for ft in file_tokens)


def _merge_with_concept(
    concept_entries: list[Any],
    file_entries: list[Any],
    concept_paths: set[str],
    max_files: int,
) -> list[Any]:
    merged = concept_entries + [
        e for e in file_entries if e["file_path"] not in concept_paths
    ]
    return merged[:max_files]


def _collect_names(rows: list[Any], key: str, cap: int) -> list[str]:
    names: list[str] = []
    for row in rows:
        name = row.get(key, "")
        if name and name not in names:
            names.append(name)
        if len(names) >= cap:
            break
    return names


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
        return _EXPLORE_SCHEMA

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        # Wave 1b (audit structure-06): map the canonical ``symbol`` alias to
        # ``query`` so ``explore symbol=X`` works instead of raising
        # "query is required" (the facade's core param is ``symbol``).
        # #515: also accept the documented multi-symbol forms — ``symbols``
        # as a list, and a list mistakenly passed via ``symbol``.
        if not arguments.get("query"):
            candidate = arguments.get("symbols") or arguments.get("symbol")
            if isinstance(candidate, list):
                arguments["query"] = " ".join(
                    str(item) for item in candidate if str(item).strip()
                )
            elif candidate:
                arguments["query"] = candidate
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query is required (or pass it as `symbol`/`symbols`)")
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

    def _init_cg_if_needed(self, cache: Any) -> None:
        root = self.project_root or ""
        try:
            self._call_graph = _init_call_graph(root, cache)
        except Exception as exc:
            logger.debug(f"Call graph init failed: {exc}")
            self._call_graph = None

    def _get_call_graph(self, cache: Any) -> Any:
        # Only attempt to build a call graph when the cache is healthy —
        # otherwise the relationship map quietly stays empty.
        if self._call_graph is not None:
            return self._call_graph
        if self.project_root:
            self._init_cg_if_needed(cache)
        return self._call_graph

    # ------------------------------------------------------------------
    # execute
    # ------------------------------------------------------------------

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        query = arguments["query"].strip()
        # Enforce caps regardless of schema (defensive: callers can bypass
        # the JSON-schema validator when invoking directly from tests).
        max_files_raw = arguments.get("maxFiles", 12)
        max_syms_raw = arguments.get("maxSymbols", 20)
        max_files = min(int(max_files_raw), _MAX_FILES_CAP)
        max_symbols = min(int(max_syms_raw), _MAX_SYMBOLS_CAP)
        include_code = bool(arguments.get("includeCode", True))
        output_format = arguments.get("output_format", "toon")

        # --- WARN: project_root unset --------------------------------
        if not self.project_root:
            s = _empty_stats()
            return _warn_response("WARN", query, s, _HINT_NO_ROOT, output_format)

        # --- WARN: AST cache empty -----------------------------------
        cache = self._get_cache()
        if cache is None:
            s = _empty_stats()
            return _warn_response("WARN", query, s, _HINT_NO_CACHE, output_format)

        # --- Tokenise + resolve --------------------------------------
        symbol_tokens, file_tokens = _h.split_query(query)
        nterms = len(symbol_tokens) + len(file_tokens)

        try:
            from ...symbol_resolver import SymbolResolver

            resolver = SymbolResolver(cache)
            resolved = _h.resolve_tokens(resolver, symbol_tokens)
        except Exception as exc:  # noqa: BLE001 — emit as ERROR envelope
            logger.warning(f"codegraph_explore resolve failed: {exc}")
            return _resolve_error_resp(exc, nterms, query, output_format)

        # File-hint filter — case-insensitive substring match. Skipped
        # when no file tokens, otherwise drops definitions in unrelated
        # files so e.g. `query="parse foo.py"` doesn't surface every
        # `parse` in the repo.
        if file_tokens:
            resolved = [d for d in resolved if _file_matches_tokens(d, file_tokens)]

        # Stable ordering keeps the response deterministic across runs.
        resolved.sort(key=lambda d: (d.file, d.line))
        concept_entries = []
        if not resolved or len(symbol_tokens) > 1:
            concept_entries = _h.concept_search(
                cache, symbol_tokens, file_tokens, self.project_root, max_files
            )

        # --- NOT_FOUND: zero matches ---------------------------------
        if not resolved:
            return _handle_no_resolved(concept_entries, query, nterms, output_format)

        symbols_resolved = len(resolved)

        # --- Cap symbols + group by file -----------------------------
        capped = resolved[:max_symbols]
        files_map = defaultdict(list)
        for d in capped:
            files_map[d.file].append(d)

        # Cap distinct files. Use insertion order (dict preserves it
        # since 3.7) so the kept files are the ones with the earliest
        # symbols in the sorted list.
        ordered_files = list(files_map.keys())[:max_files]

        # --- Build file entries --------------------------------------
        rel_fn = partial(self._relationship_names, cache)
        file_entries, symbols_returned, kept_names = _build_file_list_results(
            ordered_files,
            files_map,
            include_code,
            self._source_path,
            rel_fn,
            _MAX_FILE_BYTES,
            _MAX_SNIPPET_LINES,
        )

        if concept_entries:
            concept_paths = {entry["file_path"] for entry in concept_entries}
            file_entries = _merge_with_concept(
                concept_entries, file_entries, concept_paths, max_files
            )

        # --- Relationship map: only edges where BOTH ends are in result
        relationship_map = _build_rel_map(file_entries, kept_names)

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
            hint: str | None = "all matches dropped by maxSymbols cap"
        elif include_code and not any_code:
            # Symbols resolved but every snippet was skipped (too large
            # / file missing). Still INFO — the relationship map is
            # useful even without source.
            verdict = "INFO"
            hint = "matched symbols but no source extracted (files too large or symbols span >200 lines)"
        else:
            verdict = "INFO"
            hint = None

        stats = {
            "query_terms": nterms,
            "symbols_resolved": symbols_resolved,
            "symbols_returned": symbols_returned,
            "files_returned": len(file_entries),
            "concept_files_returned": len(concept_entries),
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

    def _source_path(self, file_path: str) -> str:
        if os.path.isabs(file_path) or not self.project_root:
            return file_path
        return os.path.join(self.project_root, file_path)

    def _relationship_names(
        self,
        cache: Any,
        symbol_name: str,
        file_path: str,
    ) -> tuple[list[str], list[str]]:
        """Return capped callers/callees via SQL-native cache lookups.

        Avoids constructing ``CachedCallGraph`` for every explore call.
        On large repos that full build reads all function rows, all import
        JSON, and all call edges even when the response only contains a
        handful of symbols.
        """
        callers: list[str] = []
        callees: list[str] = []
        try:
            caller_rows = cache.query_callers(symbol_name, file_path, max_depth=1) or []
            callers = _collect_names(caller_rows, "caller_name", _MAX_REL_PER_SYMBOL)
        except Exception as exc:
            logger.debug(f"SQL caller lookup failed for {symbol_name}: {exc}")
        try:
            callee_rows = cache.query_callees(symbol_name, file_path, max_depth=1) or []
            callees = _collect_names(callee_rows, "callee_name", _MAX_REL_PER_SYMBOL)
        except Exception as exc:
            logger.debug(f"SQL callee lookup failed for {symbol_name}: {exc}")
        return callers, callees
