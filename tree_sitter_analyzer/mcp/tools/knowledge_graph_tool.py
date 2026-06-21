"""Knowledge graph export tool."""

from __future__ import annotations

from typing import Any

from ...knowledge_graph.exporters import summarize, to_graphology
from ...knowledge_graph.models import (
    KnowledgeEdge,
    KnowledgeGraphSnapshot,
    KnowledgeNode,
)
from ...knowledge_graph.stores import JsonKnowledgeGraphStore
from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_error, build_response
from .base_tool import BaseMCPTool
from .knowledge_graph_index_tool import (
    CodeGraphKnowledgeIndexTool,
    _compact_sync_report,
)

__all__ = [
    "CodeGraphKnowledgeGraphTool",
    "CodeGraphKnowledgeIndexTool",
    "KnowledgeGraphTool",
    "_compact_sync_report",
]

_FORMATS = {"graphology", "raw", "summary"}
_LODS = {"package", "file", "symbol", "docs"}


class CodeGraphKnowledgeGraphTool(BaseMCPTool):
    """Export materialized code/document knowledge graphs."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "knowledge_graph",
            "description": (
                "Export the materialized whole-project code/document knowledge "
                "graph. Includes Markdown links, code files, symbols, calls, "
                "imports, inheritance, and contains edges. Use format=graphology "
                "for Sigma.js/react-sigma browser visualization."
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
                "export_format": {
                    "type": "string",
                    "enum": sorted(_FORMATS),
                    "default": "graphology",
                    "description": "graphology=Sigma.js payload; raw=nodes/edges; summary=compact stats",
                },
                "lod": {
                    "type": "string",
                    "enum": sorted(_LODS),
                    "default": "file",
                    "description": "Level of detail: package, file, symbol, or docs",
                },
                "focus": {
                    "type": "string",
                    "description": "Optional substring focus for node ids, labels, or paths",
                },
                "max_nodes": {
                    "type": "integer",
                    "default": 10000,
                    "description": "Max nodes emitted (default: 10000)",
                },
                "max_edges": {
                    "type": "integer",
                    "default": 50000,
                    "description": "Max edges emitted (default: 50000)",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": "Output format: toon (default) or json",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        export_format = arguments.get("export_format", "graphology")
        if export_format not in _FORMATS:
            raise ValueError("export_format must be one of: graphology, raw, summary")
        lod = arguments.get("lod", "file")
        if lod not in _LODS:
            raise ValueError("lod must be one of: package, file, symbol, docs")
        for key in ("max_nodes", "max_edges"):
            if int(arguments.get(key, 1)) < 1:
                raise ValueError(f"{key} must be a positive integer")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "toon")
        if not self.project_root:
            return apply_toon_format_to_response(
                build_error(error="project_root not set"),
                output_format,
            )

        store = JsonKnowledgeGraphStore(str(self.project_root))
        if not store.exists():
            return apply_toon_format_to_response(
                build_error(
                    error=(
                        "Knowledge graph sidecar is missing. Run "
                        "`--knowledge-graph-index` first."
                    )
                ),
                output_format,
            )

        snapshot = _snapshot_from_payload(store.read())
        export_format = arguments.get("export_format", "graphology")
        if export_format == "summary":
            graph = summarize(snapshot)
        elif export_format == "raw":
            graph = snapshot.to_dict()
        else:
            graph = to_graphology(
                snapshot,
                lod=arguments.get("lod", "file"),
                focus=arguments.get("focus"),
                max_nodes=int(arguments.get("max_nodes", 10_000)),
                max_edges=int(arguments.get("max_edges", 50_000)),
            )

        return apply_toon_format_to_response(
            build_response(
                verdict="INFO",
                export_format=export_format,
                lod=arguments.get("lod", "file"),
                graph=graph,
                source=store.status(),
            ),
            output_format,
        )


def _snapshot_from_payload(payload: dict[str, Any]) -> KnowledgeGraphSnapshot:
    nodes = [
        KnowledgeNode(
            id=str(node["id"]),
            label=str(node.get("label") or node["id"]),
            kind=str(node.get("kind") or "unknown"),
            file_path=str(node.get("file_path") or ""),
            language=str(node.get("language") or ""),
            line=node.get("line"),
            package=str(node.get("package") or ""),
            metadata=dict(node.get("metadata") or {}),
        )
        for node in payload.get("nodes", [])
        if isinstance(node, dict) and "id" in node
    ]
    edges = [
        KnowledgeEdge(
            id=str(edge["id"]),
            source=str(edge["source"]),
            target=str(edge["target"]),
            kind=str(edge.get("kind") or "unknown"),
            weight=float(edge.get("weight") or 1.0),
            provenance=str(edge.get("provenance") or "unknown"),
            line=edge.get("line"),
            metadata=dict(edge.get("metadata") or {}),
        )
        for edge in payload.get("edges", [])
        if isinstance(edge, dict) and {"id", "source", "target"} <= set(edge)
    ]
    stats = dict(payload.get("stats") or {})
    return KnowledgeGraphSnapshot(
        nodes=nodes,
        edges=edges,
        stats=stats,
        truncated=bool(payload.get("truncated", False)),
    )


KnowledgeGraphTool = CodeGraphKnowledgeGraphTool
