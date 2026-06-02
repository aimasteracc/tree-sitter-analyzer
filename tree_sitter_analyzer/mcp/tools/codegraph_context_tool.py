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

from ._codegraph_explore_helpers import extract_snippet_from_lines, read_file_lines
from .base_tool import BaseMCPTool

_STOP_WORDS = frozenset(
    "a an and are as at by call calls does flow for from how in into is of on "
    "or through to trace what when where which why with work works".split()
)


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
                "returns entry points, related call graph nodes, edges, and source "
                "code blocks from a natural-language task. Use before chaining "
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
                    "description": "Maximum source snippets to return (default: 8)",
                    "default": 8,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": (
                        "Output format: 'toon' (default, token-efficient) or 'json'"
                    ),
                    "default": "toon",
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
        max_code_blocks = _bounded_int(arguments.get("max_code_blocks", 8), 0, 25)
        output_format = arguments.get("output_format", "toon")

        candidates = _extract_symbol_candidates(task)
        entry_points = self._resolve_entry_points(candidates, max(5, max_nodes // 3))
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
        verdict = "INFO" if entry_points else "NOT_FOUND"
        result: dict[str, Any] = {
            "success": True,
            "verdict": verdict,
            "task": task,
            "candidates": candidates,
            "entry_points": entry_points,
            "nodes": nodes,
            "edges": edges,
            "code_blocks": code_blocks,
            "related_files": related_files,
            "stats": {
                "entry_points": len(entry_points),
                "nodes": len(nodes),
                "edges": len(edges),
                "code_blocks": len(code_blocks),
            },
            "agent_summary": {
                "summary_line": (
                    f"codegraph_context: {len(entry_points)} entry points, "
                    f"{len(nodes)} nodes, {len(edges)} edges, "
                    f"{len(code_blocks)} code blocks"
                ),
                "verdict": verdict,
                "next_step": _next_step(bool(code_blocks), bool(entry_points)),
            },
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _resolve_entry_points(
        self, candidates: list[str], limit: int
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        try:
            cache = self._get_cache()
        except Exception:
            return []

        seen: set[tuple[str, str, int]] = set()
        hits: list[dict[str, Any]] = []
        for candidate in candidates[:10]:
            try:
                raw_hits = cache.fts_search_ranked(candidate, limit=limit) or []
            except Exception:
                try:
                    raw_hits = cache.fts_search(candidate, limit=limit) or []
                except Exception:
                    raw_hits = []
            for raw in raw_hits:
                hit = _normalise_hit(raw)
                if not hit["name"] or hit["kind"] == "import":
                    continue
                key = (hit["name"], hit["file"], hit["line"])
                if key in seen:
                    continue
                seen.add(key)
                hits.append(hit)
                if len(hits) >= limit:
                    break
            if len(hits) >= limit:
                break

        return sorted(hits, key=_entry_rank)[:limit]

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


def _extract_symbol_candidates(task: str) -> list[str]:
    tokens = re.findall(
        r"`[^`]+`|\"[^\"]+\"|'[^']+'|[A-Za-z_][A-Za-z0-9_.]*",
        task,
    )
    seen: set[str] = set()
    out: list[str] = []
    for raw in tokens:
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
            if token not in seen:
                seen.add(token)
                out.append(token)
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
    ranked = sorted(nodes, key=lambda n: (-degrees.get(n["id"], 0), n.get("line", 0)))
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
        end_line = int(node.get("end_line", 0) or 0)
        if end_line < start_line:
            end_line = start_line + 39
        else:
            end_line = min(end_line, start_line + 39)
        content = extract_snippet_from_lines(lines, start_line, end_line)
        if not content:
            continue
        blocks.append(
            {
                "file": file_path,
                "name": node["name"],
                "start_line": start_line,
                "end_line": min(end_line, len(lines)),
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


def _entry_rank(hit: dict[str, Any]) -> tuple[int, int, str, int]:
    file_path = hit.get("file", "").replace("\\", "/")
    is_test = int("/tests/" in file_path or file_path.startswith("tests/"))
    kind_rank = 0 if hit.get("kind") in {"class", "function", "method"} else 1
    return (is_test, kind_rank, hit.get("file", ""), int(hit.get("line", 0) or 0))


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
