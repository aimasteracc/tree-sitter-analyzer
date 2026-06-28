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

import os as _os
import time
from typing import Any

from ...utils.test_detection import query_wants_tests as _task_wants_tests
from ._codegraph_explore_helpers import (
    extract_snippet_from_lines,
    read_file_lines,
)
from .base_tool import BaseMCPTool
from .utils.codegraph_context_formatter import (
    _build_related_symbols,
    _looks_like_trace,
    _next_step,
    _next_step_lean,
)
from .utils.codegraph_context_helpers import (
    _MAX_BLOCK_LINES,
    _MAX_ENTRY_BODY_LINES,
    _MAX_INLINE_EDGES,
    _MAX_INLINE_ENTRY_POINTS,
    _MAX_INLINE_NODES,
    _bounded_int,
    _build_edges_from_graph,
    _callee_ref_to_hit,
    _caller_ref_to_hit,
    _coerce_bool,
    _edge_degrees,
    _extract_symbol_candidates,
    _node_from_ref,
    _nodes_from_hits,
    _resolve_entry_points_from_cache,
    _safe_chain,
    _safe_refs,
    _unique_files,
)


def _build_code_blocks(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    max_code_blocks: int,
    project_root: str,
) -> list[dict[str, Any]]:
    """Build code blocks for a response — uses module-level extract_snippet_from_lines."""
    if max_code_blocks <= 0:
        return []
    degrees = _edge_degrees(nodes, edges)
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
            if _os.path.isabs(file_path)
            else _os.path.join(project_root, file_path)
        )
        lines = read_file_lines(abs_path)
        if not lines:
            continue
        raw_end = int(node.get("end_line", 0) or 0)
        end_known = raw_end >= start_line
        block_cap = _MAX_ENTRY_BODY_LINES if node.get("is_entry") else _MAX_BLOCK_LINES
        full_end = raw_end if end_known else start_line + block_cap - 1
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

        total_nodes = len(nodes)
        total_edges = len(edges)
        total_entry_points = len(entry_points)

        related_symbols = _build_related_symbols(nodes)

        verdict = "INFO" if entry_points else "NOT_FOUND"
        entry_points = entry_points[:_MAX_INLINE_ENTRY_POINTS]

        if include_graph:
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
                    "next_step": _next_step_lean(
                        bool(code_blocks), bool(entry_points), entry_points
                    ),
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
        return _resolve_entry_points_from_cache(cache, candidates, limit, wants_tests)

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
        return _build_edges_from_graph(graph, nodes)
