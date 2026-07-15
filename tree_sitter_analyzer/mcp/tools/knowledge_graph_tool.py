#!/usr/bin/env python3
"""Whole-project code/doc knowledge graph build and export tools."""

from __future__ import annotations

from typing import Any

from ...incremental_sync import IncrementalSync
from ...knowledge_graph import (
    KnowledgeGraphBuilder,
    LadybugKnowledgeGraphStore,
)
from ...knowledge_graph.exporters import (
    summarize,
    to_dot,
    to_graphml,
    to_graphology,
    to_mermaid_uml,
)
from ...knowledge_graph.html_viewer import to_html_viewer
from ...knowledge_graph.stores import LadybugUnavailableError
from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_error, build_response
from .base_tool import BaseMCPTool

_BACKENDS = {"auto", "sqlite", "ladybug"}
_EXPORT_FORMATS = {"dot", "graphml", "graphology", "html", "raw", "summary", "uml"}
_LOD_LEVELS = {"package", "file", "symbol", "docs"}
_UML_KINDS = {"class", "package", "component", "sequence"}
_UML_DEFAULT_MAX_NODES = 200
_UML_DEFAULT_MAX_EDGES = 500


class CodeGraphKnowledgeIndexTool(BaseMCPTool):
    """Build/update the materialized project knowledge graph."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_knowledge_index",
            "description": (
                "Build or update the whole-project code/doc knowledge graph. "
                "Uses the SQLite AST cache and edge store as the canonical "
                "index, with an optional LadybugDB projection for Cypher traversal."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["build", "update", "status"],
                    "default": "update",
                    "description": "build=reindex then materialize; update=incremental sync then materialize; status=no writes",
                },
                "backend": {
                    "type": "string",
                    "enum": sorted(_BACKENDS),
                    "default": "auto",
                    "description": "auto uses LadybugDB when available and SQLite otherwise; sqlite never materializes a second graph store",
                },
                "max_files": {
                    "type": "integer",
                    "default": 1000000,
                    "description": "Max source files for full build; update mode uses a safe full-project scan",
                },
                "max_nodes": {
                    "type": "integer",
                    "default": 0,
                    "description": "Max nodes to materialize; 0 means no materialization cap",
                },
                "max_edges": {
                    "type": "integer",
                    "default": 0,
                    "description": "Max edges to materialize; 0 means no materialization cap",
                },
                "include_docs": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include Markdown file-link graph edges",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "update")
        if mode not in {"build", "update", "status"}:
            raise ValueError("mode must be one of: build, update, status")
        backend = arguments.get("backend", "auto")
        if backend not in _BACKENDS:
            raise ValueError("backend must be one of: auto, ladybug, sqlite")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "toon")
        if not self.project_root:
            return apply_toon_format_to_response(
                build_error(error="project_root not set"),
                output_format,
            )

        mode = arguments.get("mode", "update")
        backend = arguments.get("backend", "auto")
        ladybug_store = LadybugKnowledgeGraphStore(str(self.project_root))
        effective_backend = backend
        if backend == "auto":
            effective_backend = "ladybug" if ladybug_store.available() else "sqlite"
        if mode == "status":
            response = build_response(
                verdict="INFO",
                mode=mode,
                backend=backend,
                sqlite_index=_sqlite_index_status(str(self.project_root)),
                ladybug_store=ladybug_store.status(),
            )
            return apply_toon_format_to_response(response, output_format)

        sync_report = self._prepare_index(
            mode=mode,
            max_files=int(arguments.get("max_files", 20_000)),
        )
        if (
            mode == "update"
            and not _sync_has_changes(sync_report)
            and _backend_ready(effective_backend, ladybug_store)
        ):
            snapshot = KnowledgeGraphBuilder(str(self.project_root)).build(
                include_docs=bool(arguments.get("include_docs", True)),
                max_nodes=int(arguments.get("max_nodes", 0)),
                max_edges=int(arguments.get("max_edges", 0)),
            )
            response = build_response(
                verdict="INFO",
                mode=mode,
                backend=backend,
                effective_backend=effective_backend,
                sync=sync_report,
                graph=summarize(snapshot),
                writes={},
                skipped_write_reason="no indexed file changes",
            )
            return apply_toon_format_to_response(response, output_format)

        snapshot = KnowledgeGraphBuilder(str(self.project_root)).build(
            include_docs=bool(arguments.get("include_docs", True)),
            max_nodes=int(arguments.get("max_nodes", 0)),
            max_edges=int(arguments.get("max_edges", 0)),
        )
        writes: dict[str, Any] = {}
        if effective_backend == "ladybug":
            try:
                writes["ladybug"] = ladybug_store.write(snapshot)
            except LadybugUnavailableError as exc:
                response = build_error(error=str(exc))
                response["backend"] = backend
                response["sqlite_index"] = _sqlite_index_status(str(self.project_root))
                return apply_toon_format_to_response(response, output_format)

        response = build_response(
            verdict="INFO",
            mode=mode,
            backend=backend,
            effective_backend=effective_backend,
            sync=sync_report,
            graph=summarize(snapshot),
            writes=writes,
        )
        return apply_toon_format_to_response(response, output_format)

    def _prepare_index(self, *, mode: str, max_files: int) -> dict[str, Any]:
        from ...ast_cache import ASTCache

        cache = ASTCache(str(self.project_root))
        try:
            if mode == "build":
                return _compact_sync_report(
                    cache.index_project(max_files=max_files, force=True)
                )
            sync = IncrementalSync(cache)
            # IncrementalSync treats indexed files outside max_files as deleted.
            # Knowledge graph update must be safe on large repos, so use a full
            # scan floor and reserve max_files as a full-build cap.
            safe_max_files = max(max_files, 1_000_000)
            return _compact_sync_report(sync.sync(max_files=safe_max_files).to_dict())
        finally:
            cache.close()


class CodeGraphKnowledgeGraphTool(BaseMCPTool):
    """Read/export the materialized project knowledge graph."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_knowledge_graph",
            "description": (
                "Export the project code/doc knowledge graph for humans and "
                "programs. Graphology output is Sigma.js-compatible and can "
                "drive an Obsidian-like graph view of files, Markdown docs, "
                "symbols, calls, imports, inheritance, and doc links."
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
                    "enum": sorted(_EXPORT_FORMATS),
                    "default": "graphology",
                    "description": "graphology=Sigma.js JSON, html=standalone force-directed canvas viewer, dot=Graphviz DOT, graphml=Gephi/yEd/Cytoscape XML, uml=Mermaid, raw=full sidecar, summary=compact stats",
                },
                "uml_kind": {
                    "type": "string",
                    "enum": sorted(_UML_KINDS),
                    "default": "component",
                    "description": "Mermaid UML view when export_format=uml: class, package, component, or sequence",
                },
                "lod": {
                    "type": "string",
                    "enum": sorted(_LOD_LEVELS),
                    "default": "file",
                    "description": "package/file/symbol/docs level of detail",
                },
                "focus": {
                    "type": "string",
                    "description": "Optional substring focus for node ids, labels, or paths",
                },
                "max_nodes": {
                    "type": "integer",
                    "default": 10000,
                    "description": "Max nodes in Graphology export",
                },
                "max_edges": {
                    "type": "integer",
                    "default": 50000,
                    "description": "Max edges in Graphology export",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        export_format = arguments.get("export_format", "graphology")
        if export_format not in _EXPORT_FORMATS:
            raise ValueError(
                "export_format must be one of: dot, graphml, graphology, html, raw, summary, uml"
            )
        lod = arguments.get("lod", "file")
        if lod not in _LOD_LEVELS:
            raise ValueError("lod must be one of: package, file, symbol, docs")
        uml_kind = arguments.get("uml_kind", "component")
        if uml_kind not in _UML_KINDS:
            raise ValueError(
                "uml_kind must be one of: class, component, package, sequence"
            )
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "toon")
        if not self.project_root:
            return apply_toon_format_to_response(
                build_error(error="project_root not set"),
                output_format,
            )

        snapshot = KnowledgeGraphBuilder(str(self.project_root)).build()
        export_format = arguments.get("export_format", "graphology")
        if export_format == "raw":
            response = build_response(verdict="INFO", graph=snapshot.to_dict())
        elif export_format == "summary":
            response = build_response(verdict="INFO", graph=summarize(snapshot))
        elif export_format == "html":
            graph = to_graphology(
                snapshot,
                lod=arguments.get("lod", "file"),
                focus=arguments.get("focus") or None,
                max_nodes=int(arguments.get("max_nodes", 10_000)),
                max_edges=int(arguments.get("max_edges", 50_000)),
            )
            response = build_response(
                verdict="INFO",
                html=to_html_viewer(graph),
                graph=summarize(snapshot),
                export_stats=graph.get("stats", {}),
            )
        elif export_format == "dot":
            lod = arguments.get("lod", "file")
            dot_str = to_dot(
                snapshot,
                lod=lod,
                focus=arguments.get("focus") or None,
                max_nodes=int(arguments.get("max_nodes", 500)),
                max_edges=int(arguments.get("max_edges", 2_000)),
            )
            response = build_response(
                verdict="INFO",
                dot=dot_str,
                instructions="Render with: dot -Tsvg graph.dot -o graph.svg  (or pass to Graphviz online)",
            )
        elif export_format == "graphml":
            lod = arguments.get("lod", "file")
            xml_str = to_graphml(
                snapshot,
                lod=lod,
                focus=arguments.get("focus") or None,
                max_nodes=int(arguments.get("max_nodes", 5_000)),
                max_edges=int(arguments.get("max_edges", 20_000)),
            )
            response = build_response(
                verdict="INFO",
                graphml=xml_str,
                instructions="Open in Gephi, yEd, or Cytoscape. Nodes carry centrality/degree metadata.",
            )
        elif export_format == "uml":
            response = build_response(
                verdict="INFO",
                graph=to_mermaid_uml(
                    snapshot,
                    diagram=arguments.get("uml_kind", "component"),
                    focus=arguments.get("focus") or None,
                    max_nodes=int(arguments.get("max_nodes", _UML_DEFAULT_MAX_NODES)),
                    max_edges=int(arguments.get("max_edges", _UML_DEFAULT_MAX_EDGES)),
                ),
            )
        else:
            response = build_response(
                verdict="INFO",
                graph=to_graphology(
                    snapshot,
                    lod=arguments.get("lod", "file"),
                    focus=arguments.get("focus") or None,
                    max_nodes=int(arguments.get("max_nodes", 10_000)),
                    max_edges=int(arguments.get("max_edges", 50_000)),
                ),
            )
        return apply_toon_format_to_response(response, output_format)


def _compact_sync_report(report: dict[str, Any]) -> dict[str, Any]:
    """Drop per-file details from CLI/MCP responses; counts are enough here."""
    return {
        key: value
        for key, value in report.items()
        if key not in {"details", "files", "updated", "deleted", "new"}
    }


def _sync_has_changes(report: dict[str, Any]) -> bool:
    return any(
        int(report.get(key, 0) or 0)
        for key in ("new_files", "updated_files", "deleted_files")
    )


def _backend_ready(
    backend: str,
    ladybug_store: LadybugKnowledgeGraphStore,
) -> bool:
    return backend == "sqlite" or ladybug_store.exists()


def _sqlite_index_status(project_root: str) -> dict[str, Any]:
    from pathlib import Path

    path = Path(project_root) / ".ast-cache" / "index.db"
    if not path.exists():
        return {"exists": False, "path": str(path)}
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
