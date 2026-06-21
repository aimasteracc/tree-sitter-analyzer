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

from pathlib import Path
from typing import Any

from ...call_graph import CallGraph, FunctionRef
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_error, build_response
from .base_tool import BaseMCPTool
from .codegraph_visualization_hub import (
    CodeGraphVisualizationHub,
)
from .codegraph_visualization_hub import (
    render_call_flowchart as _render_mermaid,
)
from .codegraph_visualization_hub import (
    safe_node_id as _safe_node_id,
)
from .codegraph_visualization_hub import (
    short_label as _short_label,
)

logger = setup_logger(__name__)

_MAX_EDGES_DEFAULT = 150
_MAX_DEPTH_DEFAULT = 3
_VISUALIZATION_FORMATS = {"mermaid", "sigma"}


class CodeGraphVisualizeTool(BaseMCPTool):
    """MCP Tool for Mermaid call graph visualization (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._visualization_hub = CodeGraphVisualizationHub(project_root)
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._visualization_hub.reset(project_root)

    def _get_call_graph(self) -> CallGraph | None:
        return self._visualization_hub.call_graph()

    def get_call_graph(self) -> CallGraph | None:
        """Public alias for _get_call_graph() — use this instead of patching _get_call_graph."""
        return self._get_call_graph()

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
                "visualization_format": {
                    "type": "string",
                    "enum": sorted(_VISUALIZATION_FORMATS),
                    "default": "mermaid",
                    "description": (
                        "mermaid=text flowchart; sigma=Graphology-compatible "
                        "JSON payload for Sigma.js/WebGL clients"
                    ),
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
        visualization_format = arguments.get("visualization_format", "mermaid")
        if visualization_format not in _VISUALIZATION_FORMATS:
            raise ValueError(
                "visualization_format must be one of: "
                f"{', '.join(sorted(_VISUALIZATION_FORMATS))}"
            )
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        mode = arguments.get("mode", "full")
        file_path = arguments.get("file_path")
        function = arguments.get("function")
        depth = arguments.get("depth", _MAX_DEPTH_DEFAULT)
        max_edges = arguments.get("max_edges", _MAX_EDGES_DEFAULT)
        direction = arguments.get("direction", "TD")
        visualization_format = arguments.get("visualization_format", "mermaid")
        output_format = arguments.get("output_format", "toon")

        cg = self.get_call_graph()
        if cg is None:
            return apply_toon_format_to_response(
                build_error(
                    error="No project root set or project has no source files.",
                ),
                output_format,
            )

        if mode == "full":
            edges, truncated = self._edges_full(cg, max_edges)
        elif mode == "file":
            edges, truncated = self._edges_file(cg, file_path, max_edges)
        else:
            edges, truncated = self._edges_function(
                cg, function, file_path, depth, max_edges
            )

        stats: dict[str, Any] = {
            "mode": mode,
            "visualization_format": visualization_format,
            "node_count": len(
                {edge[0] for edge in edges} | {edge[1] for edge in edges}
            ),
            "edge_count": len(edges),
        }
        # Bug #786 fix: when edge collection was capped at max_edges, signal
        # truncation explicitly so agents don't assume the graph is complete.
        if truncated:
            stats["truncated"] = True
            stats["max_edges"] = max_edges

        extra: dict[str, Any] = {}
        if mode == "function":
            extra["seed_function"] = function
        elif mode == "file":
            extra["file_path"] = file_path

        if visualization_format == "sigma":
            response = build_response(
                verdict="INFO",
                graph=_build_sigma_graph(edges),
                stats=stats,
                **extra,
            )
        else:
            response = build_response(
                verdict="INFO",
                mermaid=_render_mermaid(
                    [_mermaid_edge(edge) for edge in edges], direction
                ),
                stats=stats,
                **extra,
            )

        return apply_toon_format_to_response(response, output_format)

    def _edges_full(
        self, cg: CallGraph, max_edges: int
    ) -> tuple[list[tuple[FunctionRef, FunctionRef]], bool]:
        """Return (edges, truncated) for mode=full.

        ``truncated`` is True when the edge cap was reached and there may be
        more edges in the graph that were not included.
        """
        cg.build()
        edges: list[tuple[FunctionRef, FunctionRef]] = []
        seen: set[tuple[str, str]] = set()
        for func in cg.function_refs():
            if len(seen) >= max_edges:
                break
            for caller in cg.caller_refs_of(func):
                pair = (
                    _safe_node_id(caller.name, caller.file_path),
                    _safe_node_id(func.name, func.file_path),
                )
                if pair not in seen and len(seen) < max_edges:
                    seen.add(pair)
                    edges.append((caller, func))
                if len(seen) >= max_edges:
                    break
        truncated = len(seen) >= max_edges
        return edges, truncated

    def _edges_file(
        self, cg: CallGraph, file_path: str | None, max_edges: int
    ) -> tuple[list[tuple[FunctionRef, FunctionRef]], bool]:
        """Return (edges, truncated) for mode=file."""
        if not file_path:
            return [], False
        cg.build()
        normalized = file_path.replace("\\", "/")
        edges: list[tuple[FunctionRef, FunctionRef]] = []
        seen: set[tuple[str, str]] = set()

        funcs = cg.function_refs_in_file(normalized)
        for func in funcs:
            fid = _safe_node_id(func.name, func.file_path)
            for callee in cg.callee_refs_of(func):
                cid = _safe_node_id(callee.name, callee.file_path)
                pair = (fid, cid)
                if pair not in seen and len(seen) < max_edges:
                    seen.add(pair)
                    edges.append((func, callee))
            for caller in cg.caller_refs_of(func):
                cid = _safe_node_id(caller.name, caller.file_path)
                pair = (cid, fid)
                if pair not in seen and len(seen) < max_edges:
                    seen.add(pair)
                    edges.append((caller, func))
        truncated = len(seen) >= max_edges
        return edges, truncated

    def _edges_function(
        self,
        cg: CallGraph,
        function: str | None,
        file_path: str | None,
        depth: int,
        max_edges: int,
    ) -> tuple[list[tuple[FunctionRef, FunctionRef]], bool]:
        """Return (edges, truncated) for mode=function."""
        if not function:
            return [], False
        cg.build()
        targets = cg.resolve_targets(function, file_path)
        if not targets:
            return [], False

        edges: list[tuple[FunctionRef, FunctionRef]] = []
        seen_edges: set[tuple[str, str]] = set()
        visited: set[str] = set()

        from collections import deque

        queue: deque[tuple[FunctionRef, int]] = deque()
        for t in targets:
            queue.append((t, 0))

        while queue and len(seen_edges) < max_edges:
            current, d = queue.popleft()
            qname = current.qualified_name()
            if qname in visited:
                continue
            visited.add(qname)

            cur_id = _safe_node_id(current.name, current.file_path)

            if d < depth:
                for callee in cg.callee_refs_of(current):
                    cid = _safe_node_id(callee.name, callee.file_path)
                    pair = (cur_id, cid)
                    if pair not in seen_edges and len(seen_edges) < max_edges:
                        seen_edges.add(pair)
                        edges.append((current, callee))
                        queue.append((callee, d + 1))

                for caller in cg.caller_refs_of(current):
                    cid = _safe_node_id(caller.name, caller.file_path)
                    pair = (cid, cur_id)
                    if pair not in seen_edges and len(seen_edges) < max_edges:
                        seen_edges.add(pair)
                        edges.append((caller, current))
                        if d + 1 < depth:
                            queue.append((caller, d + 1))

        truncated = len(seen_edges) >= max_edges
        return edges, truncated


def _mermaid_edge(edge: tuple[FunctionRef, FunctionRef]) -> tuple[str, str, str, str]:
    source, target = edge
    return (
        _safe_node_id(source.name, source.file_path),
        _short_label(source.name, source.file_path),
        _safe_node_id(target.name, target.file_path),
        _short_label(target.name, target.file_path),
    )


def _build_sigma_graph(edges: list[tuple[FunctionRef, FunctionRef]]) -> dict[str, Any]:
    """Build a Graphology-compatible graph payload for Sigma.js clients."""
    node_refs: dict[str, FunctionRef] = {}
    graph_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str]] = set()

    for source, target in edges:
        source_key = _safe_node_id(source.name, source.file_path)
        target_key = _safe_node_id(target.name, target.file_path)
        node_refs.setdefault(source_key, source)
        node_refs.setdefault(target_key, target)
        edge_key = (source_key, target_key)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        graph_edges.append(
            {
                "key": f"{source_key}__calls__{target_key}",
                "source": source_key,
                "target": target_key,
                "attributes": {
                    "kind": "calls",
                    "weight": 1,
                },
            }
        )

    nodes = [
        {
            "key": node_key,
            "attributes": _sigma_node_attributes(ref),
        }
        for node_key, ref in sorted(node_refs.items())
    ]

    return {
        "schema_version": "tsa.graphology.v1",
        "directed": True,
        "renderer": {
            "library": "sigma.js",
            "data_model": "graphology",
            "layout": "client_forceatlas2_or_precomputed",
        },
        "lod": {
            "strategy": "hierarchical_subgraph",
            "current_level": "method",
            "available_levels": ["package", "class", "method"],
            "drilldown_fields": {
                "package": "attributes.package",
                "class": "attributes.receiver",
                "method": "key",
            },
        },
        "nodes": nodes,
        "edges": graph_edges,
    }


def _sigma_node_attributes(ref: FunctionRef) -> dict[str, Any]:
    receiver = getattr(ref, "receiver", None)
    file_path = str(getattr(ref, "file_path", ""))
    name = str(getattr(ref, "name", ""))
    return {
        "label": _short_label(name, file_path),
        "kind": "method" if receiver else "function",
        "file_path": file_path,
        "symbol": name,
        "qualified_name": ref.qualified_name(),
        "language": getattr(ref, "language", ""),
        "line": getattr(ref, "start_line", 0),
        "end_line": getattr(ref, "end_line", getattr(ref, "start_line", 0)),
        "receiver": receiver,
        "package": _package_from_path(file_path),
        "lod": "method",
    }


def _package_from_path(file_path: str) -> str:
    parent = Path(file_path.replace("\\", "/")).parent
    if str(parent) in {"", "."}:
        return "(root)"
    return ".".join(parent.parts)
