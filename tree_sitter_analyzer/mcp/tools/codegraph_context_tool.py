#!/usr/bin/env python3
"""One-call code graph context tool.

This tool is the graph-first answer for broad questions such as
"how does request routing work" or focused traces such as
"trace handle_request to get_user". It deliberately stays self-contained:
symbol search, call graph expansion, and source snippets are gathered in one
MCP call so agents do not burn turns chaining search, callers, callees, and
raw file reads.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

from ...utils.test_detection import is_test_file as _shared_is_test_file
from ...utils.test_detection import query_wants_tests as _task_wants_tests
from ._codegraph_explore_helpers import extract_snippet_from_lines, read_file_lines
from .base_tool import BaseMCPTool

_STOP_WORDS = frozenset(
    "a an and are as at by call calls does flow for from how in into is of on "
    "or through to trace what when where which why with work works".split()
)

# RFC-0009 C: generic single-word verbs that frequently appear in trace questions
# ("how does X dispatch / handle a request") but ALSO name many unrelated symbols
# (event dispatchers, request handlers). When the task carries a more specific
# candidate (a snake_case / CamelCase / quoted symbol), these BARE verbs are
# dropped — they only spend entry-point slots on wrong symbols. They are KEPT
# when they are the only signal in the task, so "find the dispatch function"
# still works. Conservative: precision over recall on entry-point selection.
# Note: snake_case/CamelCase names like ``resolve_callee`` are NOT affected —
# only bare lowercase verb tokens match this set.
_GENERIC_VERBS = frozenset(
    "dispatch dispatcher handle handler process processor run runner execute "
    "executor get set send receive emit notify invoke route resolve register "
    "lookup parse load store update fetch".split()
)

# Inline-body cap per code block for TANGENTIAL nodes (pulled in by call-graph
# expansion, not the task's named symbols). These get signature + head; the agent
# rarely needs their full body, so RFC-0006's thrift is preserved where it costs
# no turn.
_MAX_BLOCK_LINES = 16

# RFC-0009: ENTRY-POINT / task-relevant symbols get their FULL body inlined up to
# this budget so the agent answers in ONE call instead of a follow-up Read. The
# blanket 16-line cap was net-negative — it traded a smaller first response for
# extra turns, and turns dominate end-to-end cost. 160 covers the motivating
# target (resolve_java_callee, 127 lines) with headroom; tuned against the
# turn-count measurement in RFC-0009's acceptance criteria.
_MAX_ENTRY_BODY_LINES = 160

# Cap on edges echoed in the response. Edges are graph wiring for visualization;
# an answering agent rarely needs the full adjacency list, and 60+ raw edge
# tuples were a large fraction of the response. The full set is still used to
# RANK code blocks before the cap is applied.
_MAX_INLINE_EDGES = 12

# Cap on nodes echoed in the response. The full expanded node set (used for
# call-graph ranking + code-block selection) does not all need to be echoed —
# the agent answers from entry_points + code_blocks, and a long flat node dump
# was a large fraction of the payload vs peers that return a compact related-
# symbol list.
_MAX_INLINE_NODES = 12

# Cap on entry_points echoed. They overlap the node set; a focused handful of
# the best-ranked entry points is enough to orient the agent.
_MAX_INLINE_ENTRY_POINTS = 6


class CodeGraphContextTool(BaseMCPTool):
    """MCP tool for one-call architecture context and trace expansion."""

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: Any = None
        self._call_graph: Any = None
        self._edge_store: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._cache = None
        self._call_graph = None
        self._edge_store = None

    def _get_cache(self) -> Any:
        if self._cache is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            from ...ast_cache import ASTCache

            self._cache = ASTCache(self.project_root)
        return self._cache

    def _get_edge_store(self) -> Any:
        if self._edge_store is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            from ...graph.edge_store import EdgeStore

            cache = self._get_cache()
            conn = cache.get_conn() if hasattr(cache, "get_conn") else None
            if conn is not None:
                self._edge_store = EdgeStore(conn, ensure_schema=False)
        return self._edge_store

    def _get_call_graph(self) -> Any:
        if self._call_graph is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            try:
                from ...graph.edge_store import EdgeKind

                store = self._get_edge_store()
                if store is not None and store.has_edges(EdgeKind.CALLS):
                    self._call_graph = store
                    return self._call_graph
            except Exception:
                pass
            from ...call_graph import CachedCallGraph

            cache = self._get_cache()
            graph = CachedCallGraph(self.project_root, cache=cache, fallback=False)
            graph.build()
            self._call_graph = graph
        return self._call_graph

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_context",
            "description": (
                "PRIMARY for understanding an area or tracing a flow. One call "
                "returns entry points, a compact related-symbols list, and source "
                "code blocks from a natural-language task (default lean mode). "
                "Add include_graph=true to also get the full nodes/edges adjacency "
                "graph for visualization or impact analysis. Use before chaining "
                "codegraph_symbol_search, callers, callees, and file reads."
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
                "task": {
                    "type": "string",
                    "description": (
                        "Natural-language task, for example "
                        "'how does request routing work' or "
                        "'trace handle_request to get_user'"
                    ),
                },
                "max_nodes": {
                    "type": "integer",
                    "description": "Maximum graph nodes to return (default: 30)",
                    "default": 30,
                },
                "max_code_blocks": {
                    "type": "integer",
                    "description": "Maximum source snippets to return (default: 5)",
                    "default": 5,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": (
                        "Output format: 'toon' (default, token-efficient) or 'json'"
                    ),
                    "default": "toon",
                },
                "include_graph": {
                    "type": "boolean",
                    "description": (
                        "When false (default) return a compact related-symbols list "
                        "instead of the full nodes/edges graph — ~60% smaller payload. "
                        "Set true to get the complete nodes + edges adjacency graph "
                        "for visualization or detailed impact analysis. "
                        "stats.nodes_total and stats.edges_total are always reported "
                        "so you know the full graph is available."
                    ),
                    "default": False,
                },
            },
            "required": ["task"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not str(arguments.get("task", "")).strip():
            raise ValueError("task is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        started = time.perf_counter()

        task = str(arguments["task"]).strip()
        max_nodes = _bounded_int(arguments.get("max_nodes", 30), 1, 100)
        max_code_blocks = _bounded_int(arguments.get("max_code_blocks", 5), 0, 25)
        output_format = arguments.get("output_format", "toon")
        # RFC-0006: progressive disclosure. Default lean (no nodes/edges in
        # response); full graph available via include_graph=true. Coerce
        # JS-style string booleans so include_graph="false"/"0" stays lean.
        include_graph = _coerce_bool(arguments.get("include_graph", False))

        candidates = _extract_symbol_candidates(task)
        wants_tests = _task_wants_tests(task)
        entry_points = self._resolve_entry_points(
            candidates, max(5, max_nodes // 3), wants_tests
        )
        nodes = _nodes_from_hits(entry_points, max_nodes)
        edges: list[dict[str, Any]] = []

        if nodes:
            nodes = self._expand_nodes(nodes, task, max_nodes)
            edges = self._build_edges(nodes)

        code_blocks = _build_code_blocks(
            nodes=nodes,
            edges=edges,
            max_code_blocks=max_code_blocks,
            project_root=self.project_root or "",
        )
        related_files = _unique_files(nodes)

        # Totals always computed from the FULL set before any capping so the
        # agent knows how much graph is available even in lean mode.
        total_nodes = len(nodes)
        total_edges = len(edges)
        total_entry_points = len(entry_points)

        # Compact related-symbols list (RFC-0006): always built, tiny cost.
        # Groups the full node set by file as "name:line" entries — mirrors
        # CG's Related Symbols format without the heavy per-node dict.
        related_symbols = _build_related_symbols(nodes)

        verdict = "INFO" if entry_points else "NOT_FOUND"

        # Cap entry_points for echo (same as before).
        entry_points = entry_points[:_MAX_INLINE_ENTRY_POINTS]

        if include_graph:
            # Full graph path — identical to old default behaviour.
            # The inline caps scale with max_nodes so agents that request more
            # nodes actually receive them. _MAX_INLINE_NODES / _MAX_INLINE_EDGES
            # are the floor defaults; larger max_nodes raises the cap
            # proportionally.
            inline_node_cap = max(_MAX_INLINE_NODES, max_nodes)
            inline_edge_cap = max(_MAX_INLINE_EDGES, max_nodes * 2)
            inline_nodes = nodes[:inline_node_cap]
            _echoed_ids = {n.get("id") for n in inline_nodes}
            inline_edges = [
                e
                for e in edges
                if e.get("source") in _echoed_ids and e.get("target") in _echoed_ids
            ][:inline_edge_cap]
            result: dict[str, Any] = {
                "success": True,
                "verdict": verdict,
                "task": task,
                "candidates": candidates,
                "entry_points": entry_points,
                "nodes": inline_nodes,
                "edges": inline_edges,
                "related_symbols": related_symbols,
                "code_blocks": code_blocks,
                "related_files": related_files,
                "stats": {
                    "entry_points": len(entry_points),
                    "entry_points_total": total_entry_points,
                    "nodes": len(inline_nodes),
                    "nodes_total": total_nodes,
                    "edges": len(inline_edges),
                    "edges_total": total_edges,
                    "code_blocks": len(code_blocks),
                },
                "agent_summary": {
                    "summary_line": (
                        f"codegraph_context: {len(entry_points)} entry points, "
                        f"{len(inline_nodes)} nodes, {len(inline_edges)} edges, "
                        f"{len(code_blocks)} code blocks"
                    ),
                    "verdict": verdict,
                    "next_step": _next_step(bool(code_blocks), bool(entry_points)),
                },
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            }
        else:
            # Lean path (default, RFC-0006): omit nodes/edges, expose totals.
            # ~60% smaller payload — matches CG's compact related-symbols
            # format. The agent answers from entry_points + code_blocks; the
            # full graph is available on re-request with include_graph=true.
            result = {
                "success": True,
                "verdict": verdict,
                "task": task,
                "candidates": candidates,
                "entry_points": entry_points,
                "related_symbols": related_symbols,
                "code_blocks": code_blocks,
                "related_files": related_files,
                "stats": {
                    "entry_points": len(entry_points),
                    "entry_points_total": total_entry_points,
                    "nodes_total": total_nodes,
                    "edges_total": total_edges,
                    "code_blocks": len(code_blocks),
                },
                "agent_summary": {
                    "summary_line": (
                        f"codegraph_context: {len(entry_points)} entry points, "
                        f"{total_nodes} symbols, "
                        f"{len(code_blocks)} code blocks"
                    ),
                    "verdict": verdict,
                    "next_step": _next_step_lean(bool(code_blocks), bool(entry_points)),
                },
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _resolve_entry_points(
        self, candidates: list[str], limit: int, wants_tests: bool = False
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        try:
            cache = self._get_cache()
        except Exception:
            return []

        # Aggregate hits across ALL candidates before ranking. A symbol that
        # matches more task words (e.g. ``applyIndexOperationOnPrimary`` for
        # task "IndexShard apply index operation") must outrank one matching a
        # single generic word (``ScriptedSimilarityProvider.apply``). The old
        # code broke out of the candidate loop once ``limit`` raw hits were
        # collected and ranked by file name, so generic same-name symbols won
        # on alphabetical tie-break — the root cause of the dogfood loss.
        fetch = max(limit * 3, limit)
        agg: dict[tuple[str, str, int], dict[str, Any]] = {}

        def _absorb(raw_hits: list[Any]) -> int:
            """Merge raw hits into ``agg``; return the count of USABLE hits.

            A usable hit is one that is not skipped (non-empty name, not an
            ``import``). The count drives the cascade fallback below: raw FTS
            rows may be non-empty yet entirely unusable (e.g. only import-path
            rows), which would otherwise suppress the substring fallback and
            still yield NOT_FOUND.
            """
            usable = 0
            for bm25_rank, raw in enumerate(raw_hits):
                hit = _normalise_hit(raw)
                if not hit["name"] or hit["kind"] == "import":
                    continue
                usable += 1
                key = (hit["name"], hit["file"], hit["line"])
                entry = agg.get(key)
                if entry is None:
                    agg[key] = {
                        "hit": hit,
                        "matches": 1,
                        "best_rank": bm25_rank,
                    }
                else:
                    entry["matches"] += 1
                    if bm25_rank < entry["best_rank"]:
                        entry["best_rank"] = bm25_rank
            return usable

        cascade = getattr(cache, "search_symbols_cascade", None)

        # Single-word recall: FTS5 BM25 over each task word. When a word yields
        # no USABLE hits, fall back to the substring cascade. This is the cost
        # root cause: FTS5 tokenizes camelCase/compound identifiers as ONE
        # token, so a natural-language word like ``route`` matches neither
        # ``addRoute`` nor ``updateRouteTree``. Without this fallback the whole
        # query returns NOT_FOUND and the agent abandons the index to Read raw
        # files (the gin file_r=5-vs-2 gap). The substring cascade resolves
        # ``route`` -> {addRoute, updateRouteTree, NoRoute, Routes}, so a
        # conceptual query still returns inline source from the index.
        #
        # The fallback is gated on USABLE hits, not raw FTS rows (Codex P2 on
        # #288): FTS can return only ``kind == "import"`` rows that ``_absorb``
        # discards — a non-empty-but-useless result that must NOT suppress the
        # cascade.
        for candidate in candidates[:10]:
            try:
                raw_hits = cache.fts_search_ranked(candidate, limit=fetch) or []
            except Exception:
                try:
                    raw_hits = cache.fts_search(candidate, limit=fetch) or []
                except Exception:
                    raw_hits = []
            if _absorb(raw_hits) == 0 and callable(cascade):
                try:
                    cascade_hits = cascade(candidate, limit=fetch) or []
                except Exception:
                    cascade_hits = []
                _absorb(cascade_hits)

        # Compound recall: camelCase word pairs (applyIndex, indexOperation)
        # reach multi-word methods that single-word FTS tokenization misses —
        # the cascade substring tier resolves them. This is the fix for the
        # dogfood loss where 'apply' only matched generic same-name methods.
        if callable(cascade):
            for compound in _compound_candidates(candidates):
                try:
                    raw_hits = cascade(compound, limit=limit) or []
                except Exception:
                    raw_hits = []
                _absorb(raw_hits)

        ranked = sorted(
            agg.values(),
            key=lambda e: _entry_rank_v2(e, candidates, wants_tests),
        )
        return [e["hit"] for e in ranked[:limit]]

    def _expand_nodes(
        self, seed_nodes: list[dict[str, Any]], task: str, max_nodes: int
    ) -> list[dict[str, Any]]:
        try:
            graph = self._get_call_graph()
        except Exception:
            return seed_nodes

        nodes = list(seed_nodes)
        seen = {(n["name"], n.get("file", "")) for n in nodes}
        trace_mode = _looks_like_trace(task)
        is_edge_store = hasattr(graph, "query_callees")

        def add_ref(ref: dict[str, Any]) -> None:
            if len(nodes) >= max_nodes:
                return
            node = _node_from_ref(ref)
            if not node["name"]:
                return
            key = (node["name"], node.get("file", ""))
            if key in seen:
                return
            seen.add(key)
            nodes.append(node)

        def _edge_store_callees(
            name: str, file_path: str | None, depth: int = 1
        ) -> list[dict[str, Any]]:
            try:
                return graph.query_callees(name, file_path, max_depth=depth) or []
            except Exception:
                return []

        def _edge_store_callers(
            name: str, file_path: str | None
        ) -> list[dict[str, Any]]:
            try:
                return graph.query_callers(name, file_path) or []
            except Exception:
                return []

        for node in list(seed_nodes):
            if len(nodes) >= max_nodes:
                break
            name = node["name"]
            file_path = node.get("file") or None
            if is_edge_store:
                depth = 4 if trace_mode else 1
                for ref in _edge_store_callees(name, file_path, depth)[:10]:
                    add_ref(_callee_ref_to_hit(ref))
                for ref in _edge_store_callers(name, file_path)[:10]:
                    add_ref(_caller_ref_to_hit(ref))
            else:
                for ref in _safe_refs(graph.callees_of, name, file_path)[:10]:
                    add_ref(ref)
                for ref in _safe_refs(graph.callers_of, name, file_path)[:10]:
                    add_ref(ref)
                if trace_mode:
                    for hop in _safe_chain(graph, name, file_path, depth=4):
                        callee = hop.get("callee")
                        if isinstance(callee, dict):
                            add_ref(callee)

        return nodes[:max_nodes]

    def _build_edges(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            graph = self._get_call_graph()
        except Exception:
            return []

        by_key = {(n["name"], n.get("file", "")): n for n in nodes}
        by_name: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            by_name.setdefault(node["name"], []).append(node)

        edges: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for node in nodes:
            is_edge_store = hasattr(graph, "query_callees")
            if is_edge_store:
                callees = (
                    graph.query_callees(node["name"], node.get("file") or None) or []
                )
                for ref in callees:
                    callee = _callee_ref_to_hit(ref)
                    target = by_key.get((callee["name"], callee["file"]))
                    if target is None:
                        target_matches = by_name.get(callee["name"], [])
                        target = target_matches[0] if target_matches else None
                    if target is None or target["id"] == node["id"]:
                        continue
                    edge_key = (node["id"], target["id"])
                    if edge_key in seen:
                        continue
                    seen.add(edge_key)
                    edges.append(
                        {
                            "source": node["id"],
                            "target": target["id"],
                            "kind": "calls",
                            "line": ref.get("callee_line", 0),
                        }
                    )
            else:
                for ref in _safe_refs(
                    graph.callees_of, node["name"], node.get("file") or None
                ):
                    callee = _normalise_hit(ref)
                    target = by_key.get((callee["name"], callee["file"]))
                    if target is None:
                        target_matches = by_name.get(callee["name"], [])
                        target = target_matches[0] if target_matches else None
                    if target is None or target["id"] == node["id"]:
                        continue
                    edge_key = (node["id"], target["id"])
                    if edge_key in seen:
                        continue
                    seen.add(edge_key)
                    edges.append(
                        {
                            "source": node["id"],
                            "target": target["id"],
                            "kind": "calls",
                            "line": node.get("line", 0),
                        }
                    )
        return edges


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))


_FALSEY_STRINGS = frozenset({"false", "0", "no", "off", "none", "null", ""})


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """Coerce an MCP/CLI argument to bool, honouring JS-style string booleans.

    Agents (and the chain DSL) may pass ``include_graph`` as the string
    ``"false"`` / ``"0"`` — ``bool("false")`` is ``True``, which would wrongly
    take the full-graph path. Recognised falsey tokens map to ``False``; any
    other non-empty string is truthy. Real bools pass through unchanged.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in _FALSEY_STRINGS
    return bool(value)


def _extract_symbol_candidates(task: str) -> list[str]:
    tokens = re.findall(
        r"`[^`]+`|\"[^\"]+\"|'[^']+'|[A-Za-z_][A-Za-z0-9_.]*",
        task,
    )
    seen: set[str] = set()
    out: list[str] = []
    quoted: set[str] = set()
    for raw in tokens:
        # A token written in back-ticks / quotes is an EXPLICIT symbol name the
        # user chose deliberately — even a lowercase generic verb (`` `dispatch` ``)
        # should then count as specific and never be dropped by the C filter below
        # (Codex P2 #333). The regex captures the quotes, so detect before strip.
        was_quoted = bool(raw) and raw[0] in "`\"'"
        raw = raw.strip("`\"'")
        for part in re.split(r"[.:\->]+", raw):
            token = part.strip("_.,;:!?()[]{}")
            if not token:
                continue
            lowered = token.lower()
            if lowered in _STOP_WORDS or len(token) < 3:
                continue
            if not (
                "_" in token or any(ch.isupper() for ch in token) or len(token) >= 4
            ):
                continue
            if was_quoted:
                quoted.add(token)
            if token not in seen:
                seen.add(token)
                out.append(token)

    # RFC-0009 C: when the task names a specific symbol (snake_case / CamelCase /
    # explicitly quoted), drop bare generic-verb candidates ("dispatch", "handle")
    # — they only match unrelated event dispatchers / handlers and waste
    # entry-point slots. Keep them when they are the ONLY signal (no specific
    # candidate present) or when the user quoted them explicitly.
    def _is_specific(tok: str) -> bool:
        return "_" in tok or any(ch.isupper() for ch in tok) or tok in quoted

    if any(_is_specific(tok) for tok in out):
        out = [
            tok for tok in out if _is_specific(tok) or tok.lower() not in _GENERIC_VERBS
        ]
    return out


def _normalise_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": hit.get("name", ""),
        "kind": hit.get("kind", "unknown"),
        "file": hit.get("file") or hit.get("file_path", ""),
        "line": int(hit.get("line", 0) or 0),
        "end_line": int(hit.get("end_line", 0) or 0),
        "language": hit.get("language", ""),
    }


def _nodes_from_hits(
    hits: list[dict[str, Any]], max_nodes: int
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for hit in hits:
        if len(nodes) >= max_nodes:
            break
        node = _node_from_ref(hit)
        # RFC-0009: these are the task's named entry points (vs nodes added later
        # by call-graph expansion). Mark them so _build_code_blocks ranks them
        # first and inlines their full body.
        node["is_entry"] = True
        key = (node["name"], node.get("file", ""), node.get("line", 0))
        if key in seen:
            continue
        seen.add(key)
        nodes.append(node)
    return nodes


def _node_from_ref(ref: dict[str, Any]) -> dict[str, Any]:
    hit = _normalise_hit(ref)
    node: dict[str, Any] = {
        "id": _node_id(hit["name"], hit["file"], hit["line"]),
        "name": hit["name"],
        "kind": hit["kind"],
        "file": hit["file"],
        "line": hit["line"],
    }
    if hit["end_line"] >= hit["line"] > 0:
        node["end_line"] = hit["end_line"]
    if hit["language"]:
        node["language"] = hit["language"]
    return node


def _node_id(name: str, file_path: str, line: int) -> str:
    return f"{os.path.basename(file_path)}:{name}:{line}"


def _safe_refs(
    callable_obj: Any, name: str, file_path: str | None
) -> list[dict[str, Any]]:
    try:
        return callable_obj(name, file_path) or []
    except Exception:
        try:
            return callable_obj(name) or []
        except Exception:
            return []


def _callee_ref_to_hit(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": ref.get("callee_name", ""),
        "kind": "function",
        "file": ref.get("callee_file", ""),
        "line": int(ref.get("callee_line", 0) or 0),
        "end_line": 0,
        "language": "",
    }


def _caller_ref_to_hit(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": ref.get("caller_name", ""),
        "kind": "function",
        "file": ref.get("caller_file", ""),
        "line": int(ref.get("caller_line", 0) or 0),
        "end_line": 0,
        "language": "",
    }


def _safe_chain(
    graph: Any, name: str, file_path: str | None, depth: int
) -> list[dict[str, Any]]:
    try:
        return graph.call_chain(name, file_path=file_path, depth=depth) or []
    except Exception:
        try:
            return graph.call_chain(name, depth=depth) or []
        except Exception:
            return []


def _build_code_blocks(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    max_code_blocks: int,
    project_root: str,
) -> list[dict[str, Any]]:
    if max_code_blocks <= 0:
        return []
    degrees = _edge_degrees(nodes, edges)
    # RFC-0009: rank the task's named entry points FIRST (before graph-centrality),
    # so the answer symbol always gets a block ahead of a high-degree hub like a
    # cache accessor. Within each tier, fall back to edge-degree then line.
    ranked = sorted(
        nodes,
        key=lambda n: (
            not n.get("is_entry", False),
            -degrees.get(n["id"], 0),
            n.get("line", 0),
        ),
    )
    blocks: list[dict[str, Any]] = []
    seen_files_lines: set[tuple[str, int]] = set()
    for node in ranked:
        if len(blocks) >= max_code_blocks:
            break
        file_path = node.get("file", "")
        start_line = int(node.get("line", 0) or 0)
        if not file_path or start_line < 1:
            continue
        dedupe_key = (file_path, start_line)
        if dedupe_key in seen_files_lines:
            continue
        seen_files_lines.add(dedupe_key)
        abs_path = (
            file_path
            if os.path.isabs(file_path)
            else os.path.join(project_root, file_path)
        )
        lines = read_file_lines(abs_path)
        if not lines:
            continue
        raw_end = int(node.get("end_line", 0) or 0)
        end_known = raw_end >= start_line
        # RFC-0009: entry-point / task-relevant symbols inline their FULL body up
        # to _MAX_ENTRY_BODY_LINES so the agent answers in one call; tangential
        # (expansion) nodes keep the small _MAX_BLOCK_LINES cap (RFC-0006 thrift).
        block_cap = _MAX_ENTRY_BODY_LINES if node.get("is_entry") else _MAX_BLOCK_LINES
        # Nodes from call-graph expansion (callees/callers) often have no
        # end_line; fall back to the cap window for those.
        full_end = raw_end if end_known else start_line + block_cap - 1
        # Long bodies still get a truncation marker pointing at the rest, so the
        # agent can read on for the rare over-budget function.
        capped_end = min(full_end, start_line + block_cap - 1)
        capped_end = min(capped_end, len(lines))
        content = extract_snippet_from_lines(lines, start_line, capped_end)
        if not content:
            continue
        if end_known:
            real_end = min(full_end, len(lines))
            if real_end > capped_end:
                content = (
                    content.rstrip("\n")
                    + f"\n    # … {real_end - capped_end} more lines "
                    f"({file_path}:{capped_end + 1}-{real_end})\n"
                )
        elif capped_end < len(lines):
            # End line unknown (call-graph node) AND we stopped at the cap before
            # EOF — the function may continue. Emit an explicit hint so the agent
            # knows to read onward rather than assuming the snippet is complete
            # (Codex P2 on #293: the old fallback silently dropped lines 25+).
            content = (
                content.rstrip("\n")
                + f"\n    # … snippet capped at {block_cap} lines; "
                f"end unknown — read {file_path}:{capped_end + 1}+ if needed\n"
            )
        blocks.append(
            {
                "file": file_path,
                "name": node["name"],
                "start_line": start_line,
                "end_line": capped_end,
                "content": content,
            }
        )
    return blocks


def _edge_degrees(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> dict[str, int]:
    degrees = {node["id"]: 0 for node in nodes}
    for edge in edges:
        if edge["source"] in degrees:
            degrees[edge["source"]] += 1
        if edge["target"] in degrees:
            degrees[edge["target"]] += 1
    return degrees


def _unique_files(nodes: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for node in nodes:
        file_path = node.get("file", "")
        if file_path and file_path not in seen:
            seen.add(file_path)
            out.append(file_path)
    return out


def _is_test_file(file_path: str) -> int:
    """Rank-tier wrapper: 1 for test files, 0 otherwise.

    Thin shim over the shared, canonical ``utils.test_detection.is_test_file``
    so every ranking path agrees on what counts as a test (see that module).
    Detected by FILE path only, never by symbol name, so a production class
    named ``TestRunner`` is never demoted.
    """
    return 1 if _shared_is_test_file(file_path) else 0


def _entry_rank(hit: dict[str, Any]) -> tuple[int, int, str, int]:
    file_path = hit.get("file", "")
    is_test = _is_test_file(file_path)
    kind_rank = 0 if hit.get("kind") in {"class", "function", "method"} else 1
    return (is_test, kind_rank, hit.get("file", ""), int(hit.get("line", 0) or 0))


def _name_match_score(name: str, candidates: list[str]) -> int:
    """Count how many task candidates appear inside a symbol name.

    Relevance signal for entry-point ranking: a symbol matching more task
    words is more on-topic. ``applyIndexOperationOnPrimary`` matches
    apply+index+operation (3); ``apply`` matches only apply (1). Case-
    insensitive substring match; candidates shorter than 3 chars are ignored
    to avoid spurious hits.
    """
    if not name:
        return 0
    lowered = name.lower()
    score = 0
    for cand in candidates:
        c = cand.lower()
        if len(c) >= 3 and c in lowered:
            score += 1
    return score


def _compound_candidates(candidates: list[str]) -> list[str]:
    """Build camelCase joins of ordered task-word pairs.

    Single-word FTS tokenizes ``applyIndexOperationOnPrimary`` as one opaque
    token, so the plain word ``apply`` never recalls it. Joining task words
    pairwise (``apply`` + ``index`` -> ``applyIndex``) produces substrings the
    cascade LIKE tier matches precisely against multi-word method names, with
    far less noise than a bare ``%apply%`` scan. Capped to keep the number of
    cascade queries bounded on large indexes.
    """
    words = [c for c in candidates if len(c) >= 3][:6]
    out: list[str] = []
    seen: set[str] = set()
    existing = {c.lower() for c in candidates}
    for i, a in enumerate(words):
        for j, b in enumerate(words):
            if i == j:
                continue
            joined = a[0].lower() + a[1:] + b[0].upper() + b[1:]
            low = joined.lower()
            if low in seen or low in existing:
                continue
            seen.add(low)
            out.append(joined)
    return out[:12]


def _entry_rank_v2(
    entry: dict[str, Any],
    candidates: list[str],
    wants_tests: bool = False,
) -> tuple[int, int, int, int, int, str, int]:
    """Relevance-aware ranking key for an aggregated entry-point hit.

    Order of precedence: non-test before test, definition kinds before refs,
    MORE matched task words first, MORE candidate hits first, better BM25
    rank, then file/line for a stable tie-break.

    When ``wants_tests`` is set (the task itself asks about tests/specs), the
    test-demotion tier is disabled so relevant test symbols are not pushed
    past the result limit — codegraph_context takes natural-language tasks,
    and "X tests" must be allowed to return test code (Codex P2 #291).
    """
    hit = entry["hit"]
    test_tier = 0 if wants_tests else _is_test_file(hit.get("file", ""))
    kind_rank = 0 if hit.get("kind") in {"class", "function", "method"} else 1
    name_match = _name_match_score(hit.get("name", ""), candidates)
    return (
        test_tier,
        kind_rank,
        -name_match,
        -int(entry.get("matches", 0)),
        int(entry.get("best_rank", 0)),
        hit.get("file", ""),
        int(hit.get("line", 0) or 0),
    )


def _looks_like_trace(task: str) -> bool:
    lowered = task.lower()
    return any(
        word in lowered for word in ("trace", "flow", "through", "pipeline", "how does")
    )


def _next_step(has_code: bool, has_entry_points: bool) -> str:
    if has_code:
        return (
            "Answer from code_blocks and the graph now. Only call a narrower "
            "codegraph tool if a specific edge or symbol is missing."
        )
    if has_entry_points:
        return "Use the nodes and edges to answer; code snippets were not available."
    return "Try codegraph_symbol_search with an exact symbol name or broaden the task."


def _next_step_lean(has_code: bool, has_entry_points: bool) -> str:
    """Next-step hint for the lean (default) response path.

    Always names the ``include_graph=true`` flag so the agent knows the full
    call graph is available on re-request — the progressive-disclosure contract.
    """
    if has_code:
        return (
            "Answer from code_blocks now. "
            "For the full call graph (nodes/edges) add include_graph=true."
        )
    if has_entry_points:
        return (
            "Entry points found; code snippets were not available. "
            "For the full call graph add include_graph=true."
        )
    return "Try codegraph_symbol_search with an exact symbol name or broaden the task."


def _build_related_symbols(
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a compact CG-style related-symbols list grouped by file.

    Each entry is ``{"file": str, "symbols": ["name:line", ...]}``, sorted by
    file path then by line number within each file. Nodes without a file or
    without a name are skipped. This mirrors CodeGraph's "Related Symbols"
    format (``file: name:line, name:line``) at a fraction of the per-node
    dict cost — no language, no kind, no end_line, no id.
    """
    by_file: dict[str, list[tuple[int, str]]] = {}
    for node in nodes:
        file_path = node.get("file", "")
        name = node.get("name", "")
        if not file_path or not name:
            continue
        line = int(node.get("line", 0) or 0)
        by_file.setdefault(file_path, []).append((line, name))

    groups: list[dict[str, Any]] = []
    for file_path in sorted(by_file):
        entries = sorted(by_file[file_path])  # sort by (line, name)
        symbols = [f"{name}:{line}" for line, name in entries]
        groups.append({"file": file_path, "symbols": symbols})
    return groups
