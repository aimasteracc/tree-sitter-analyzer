#!/usr/bin/env python3
"""
CodeGraph Visualize MCP Tool — Mermaid call graph rendering.

Exports the project call graph as a Mermaid flowchart diagram for
visual rendering in Markdown, GitHub, or any Mermaid-compatible viewer.

Modes:
  - full:     All call edges across the project (clamped to max_edges)
  - file:     Call graph scoped to a single file (callers + callees)
  - function: Transitive call chain from a seed function (depth-bounded)

CodeGraph parity: equivalent to CodeGraph's visual graph rendering.
Unlike CodeGraph, produces Mermaid (text) that works in GitHub PRs,
READMEs, and any Markdown context without a running server.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from ...call_graph import CachedCallGraph, CallGraph
from ...utils import setup_logger
from ..utils.auto_index_guard import ensure_indexed
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_MAX_EDGES_DEFAULT = 150
_MAX_DEPTH_DEFAULT = 3
_MAX_NODES_FULL = 80


def _safe_node_id(name: str, file_path: str) -> str:
    raw = f"{file_path}::{name}"
    return "".join(c if c.isalnum() or c == "_" else "_" for c in raw)


def _short_label(name: str, file_path: str) -> str:
    parts = Path(file_path).parts
    short_file = parts[-1] if parts else file_path
    return f"{short_file}::{name}"


def _render_mermaid(
    edges: list[tuple[str, str, str, str]],
    direction: str = "TD",
) -> str:
    lines: list[str] = [f"flowchart {direction}"]

    node_ids = set()
    for src_id, _, dst_id, _ in edges:
        node_ids.add(src_id)
        node_ids.add(dst_id)

    if not node_ids:
        lines.append("    empty[\"No call edges found\"]")
        return "\n".join(lines)

    id_to_label: dict[str, str] = {}
    for src_id, src_label, dst_id, dst_label in edges:
        id_to_label[src_id] = src_label
        id_to_label[dst_id] = dst_label

    seen_ids: set[str] = set()
    for nid, label in sorted(id_to_label.items()):
        if nid not in seen_ids:
            seen_ids.add(nid)
            escaped = label.replace('"', "'")
            lines.append(f'    {nid}["{escaped}"]')

    seen_edges: set[tuple[str, str]] = set()
    for src_id, _, dst_id, _ in edges:
        pair = (src_id, dst_id)
        if pair not in seen_edges:
            seen_edges.add(pair)
            lines.append(f"    {src_id} --> {dst_id}")

    return "\n".join(lines)


class CodeGraphVisualizeTool(BaseMCPTool):
    """MCP Tool for Mermaid call graph visualization (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._call_graph: CallGraph | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._call_graph = None

    def _get_call_graph(self) -> CallGraph | None:
        if self._call_graph is not None:
            return self._call_graph
        cache = ensure_indexed(self.project_root)
        if cache is not None:
            self._call_graph = CachedCallGraph(self.project_root, cache)
            return self._call_graph
        if self.project_root:
            cg = CallGraph(self.project_root)
            cg.build()
            self._call_graph = cg
            return cg
        return None

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_visualize",
            "description": (
                "Export the project call graph as a Mermaid flowchart diagram "
                "(CodeGraph parity). Renders caller→callee edges as a text "
                "diagram that works in GitHub READMEs, PRs, and Markdown. "
                "Modes: 'full' (all edges), 'file' (single-file scope), "
                "'function' (transitive chain from seed). "
                "No other tool produces visual call graph diagrams."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["full", "file", "function"],
                    "default": "full",
                    "description": (
                        "full=all call edges; "
                        "file=edges touching one file; "
                        "function=transitive chain from seed function"
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": "File path for mode=file (required for that mode)",
                },
                "function": {
                    "type": "string",
                    "description": "Seed function name for mode=function (required for that mode)",
                },
                "depth": {
                    "type": "integer",
                    "default": 3,
                    "description": "Max transitive depth for mode=function (default: 3)",
                },
                "max_edges": {
                    "type": "integer",
                    "default": 150,
                    "description": "Max edges to render (default: 150, clamps output size)",
                },
                "direction": {
                    "type": "string",
                    "enum": ["TD", "LR", "BT", "RL"],
                    "default": "TD",
                    "description": "Mermaid flowchart direction (default: TD=top-down)",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "full")
        if mode == "file" and not arguments.get("file_path"):
            raise ValueError("file_path is required when mode=file")
        if mode == "function" and not arguments.get("function"):
            raise ValueError("function is required when mode=function")
        max_edges = arguments.get("max_edges", _MAX_EDGES_DEFAULT)
        if not isinstance(max_edges, int) or max_edges < 1:
            raise ValueError("max_edges must be a positive integer")
        depth = arguments.get("depth", _MAX_DEPTH_DEFAULT)
        if not isinstance(depth, int) or depth < 1:
            raise ValueError("depth must be a positive integer")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        mode = arguments.get("mode", "full")
        file_path = arguments.get("file_path")
        function = arguments.get("function")
        depth = arguments.get("depth", _MAX_DEPTH_DEFAULT)
        max_edges = arguments.get("max_edges", _MAX_EDGES_DEFAULT)
        direction = arguments.get("direction", "TD")
        output_format = arguments.get("output_format", "toon")

        cg = self._get_call_graph()
        if cg is None:
            return apply_toon_format_to_response(
                {
                    "success": False,
                    "error": "No project root set or project has no source files.",
                    "verdict": "ERROR",
                },
                output_format,
            )

        if mode == "full":
            edges = self._edges_full(cg, max_edges)
        elif mode == "file":
            edges = self._edges_file(cg, file_path, max_edges)
        else:
            edges = self._edges_function(cg, function, file_path, depth, max_edges)

        mermaid = _render_mermaid(edges, direction)

        stats = {
            "mode": mode,
            "node_count": len({e[0] for e in edges} | {e[2] for e in edges}),
            "edge_count": len(edges),
        }

        response: dict[str, Any] = {
            "success": True,
            "verdict": "OK",
            "mermaid": mermaid,
            "stats": stats,
        }

        if mode == "function":
            response["seed_function"] = function
        elif mode == "file":
            response["file_path"] = file_path

        return apply_toon_format_to_response(response, output_format)

    def _edges_full(
        self, cg: CallGraph, max_edges: int
    ) -> list[tuple[str, str, str, str]]:
        cg.build()
        edges: list[tuple[str, str, str, str]] = []
        file_callers: dict[Any, list[Any]] = defaultdict(list)
        file_callees: dict[Any, list[Any]] = defaultdict(list)
        for func in cg._functions:
            for caller in cg._callers.get(func, []):
                file_callers[func].append(caller)
            for callee in cg._callees.get(func, []):
                file_callees[func].append(callee)

        seen: set[tuple[str, str]] = set()
        for func in cg._functions:
            for caller in cg._callers.get(func, []):
                pair = (
                    _safe_node_id(caller.name, caller.file_path),
                    _safe_node_id(func.name, func.file_path),
                )
                if pair not in seen and len(seen) < max_edges:
                    seen.add(pair)
                    edges.append((
                        pair[0],
                        _short_label(caller.name, caller.file_path),
                        pair[1],
                        _short_label(func.name, func.file_path),
                    ))
        return edges

    def _edges_file(
        self, cg: CallGraph, file_path: str | None, max_edges: int
    ) -> list[tuple[str, str, str, str]]:
        if not file_path:
            return []
        cg.build()
        normalized = file_path.replace("\\", "/")
        edges: list[tuple[str, str, str, str]] = []
        seen: set[tuple[str, str]] = set()

        funcs = cg._func_by_file.get(normalized, [])
        for func in funcs:
            fid = _safe_node_id(func.name, func.file_path)
            flabel = _short_label(func.name, func.file_path)
            for callee in cg._callees.get(func, []):
                cid = _safe_node_id(callee.name, callee.file_path)
                pair = (fid, cid)
                if pair not in seen and len(seen) < max_edges:
                    seen.add(pair)
                    edges.append((
                        fid, flabel,
                        cid, _short_label(callee.name, callee.file_path),
                    ))
            for caller in cg._callers.get(func, []):
                cid = _safe_node_id(caller.name, caller.file_path)
                pair = (cid, fid)
                if pair not in seen and len(seen) < max_edges:
                    seen.add(pair)
                    edges.append((
                        cid, _short_label(caller.name, caller.file_path),
                        fid, flabel,
                    ))
        return edges

    def _edges_function(
        self,
        cg: CallGraph,
        function: str | None,
        file_path: str | None,
        depth: int,
        max_edges: int,
    ) -> list[tuple[str, str, str, str]]:
        if not function:
            return []
        cg.build()
        targets = cg._resolve_targets(function, file_path)
        if not targets:
            return []

        edges: list[tuple[str, str, str, str]] = []
        seen_edges: set[tuple[str, str]] = set()
        visited: set[str] = set()

        from collections import deque

        queue: deque[tuple[Any, int]] = deque()
        for t in targets:
            queue.append((t, 0))

        while queue and len(seen_edges) < max_edges:
            current, d = queue.popleft()
            qname = current.qualified_name()
            if qname in visited:
                continue
            visited.add(qname)

            cur_id = _safe_node_id(current.name, current.file_path)
            cur_label = _short_label(current.name, current.file_path)

            if d < depth:
                for callee in cg._callees.get(current, []):
                    cid = _safe_node_id(callee.name, callee.file_path)
                    pair = (cur_id, cid)
                    if pair not in seen_edges and len(seen_edges) < max_edges:
                        seen_edges.add(pair)
                        edges.append((
                            cur_id, cur_label,
                            cid, _short_label(callee.name, callee.file_path),
                        ))
                        queue.append((callee, d + 1))

                for caller in cg._callers.get(current, []):
                    cid = _safe_node_id(caller.name, caller.file_path)
                    pair = (cid, cur_id)
                    if pair not in seen_edges and len(seen_edges) < max_edges:
                        seen_edges.add(pair)
                        edges.append((
                            cid, _short_label(caller.name, caller.file_path),
                            cur_id, cur_label,
                        ))
                        if d + 1 < depth:
                            queue.append((caller, d + 1))

        return edges
