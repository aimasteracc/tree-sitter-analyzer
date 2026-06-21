"""Knowledge graph index build/update tool."""

from __future__ import annotations

from typing import Any

from ...incremental_sync import IncrementalSync
from ...knowledge_graph import (
    JsonKnowledgeGraphStore,
    KnowledgeGraphBuilder,
    LadybugKnowledgeGraphStore,
    LadybugUnavailableError,
)
from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_error, build_response
from .base_tool import BaseMCPTool

_LEVELS = {"package", "file", "symbol"}
_BACKENDS = {"json", "ladybug", "both", "hybrid"}
_MODES = {"build", "update", "status"}


class CodeGraphKnowledgeIndexTool(BaseMCPTool):
    """Build or refresh the whole-project knowledge graph snapshot."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "knowledge_graph_index",
            "description": (
                "Build/update the whole-project code/document knowledge graph. "
                "Uses the existing SQLite AST cache for parsing, hashes, FTS, and "
                "incremental sync; optionally mirrors the graph into LadybugDB for "
                "Cypher traversal. Supports package/file/symbol LOD snapshots."
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
                    "enum": sorted(_MODES),
                    "default": "update",
                    "description": "build=write snapshot; update=incremental sync then write; status=read cache state",
                },
                "level": {
                    "type": "string",
                    "enum": sorted(_LEVELS),
                    "default": "file",
                    "description": "LOD: package overview, file/doc graph, or symbol graph",
                },
                "backend": {
                    "type": "string",
                    "enum": sorted(_BACKENDS),
                    "default": "json",
                    "description": "json=sidecar; ladybug=embedded graph DB; hybrid/both=write both",
                },
                "focus": {
                    "type": "string",
                    "description": "Optional path/package substring filter for focused graph slices",
                },
                "include_docs": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include Markdown-to-code/doc links (default: true)",
                },
                "include_symbols": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include symbol nodes when level=symbol (default: true)",
                },
                "max_nodes": {
                    "type": "integer",
                    "default": 50000,
                    "description": "Max nodes in stored snapshot (default: 50000)",
                },
                "max_edges": {
                    "type": "integer",
                    "default": 100000,
                    "description": "Max edges in stored snapshot (default: 100000)",
                },
                "max_files": {
                    "type": "integer",
                    "default": 20000,
                    "description": "Max source files for incremental sync in mode=update",
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
        mode = arguments.get("mode", "update")
        if mode not in _MODES:
            raise ValueError("mode must be one of: build, status, update")
        level = arguments.get("level", "file")
        if level not in _LEVELS:
            raise ValueError("level must be one of: package, file, symbol")
        backend = arguments.get("backend", "json")
        if backend not in _BACKENDS:
            raise ValueError("backend must be one of: json, ladybug, both, hybrid")
        for key in ("max_nodes", "max_edges", "max_files"):
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

        mode = arguments.get("mode", "update")
        json_store = JsonKnowledgeGraphStore(str(self.project_root))
        ladybug_store = LadybugKnowledgeGraphStore(str(self.project_root))
        if mode == "status":
            return apply_toon_format_to_response(
                build_response(
                    verdict="INFO",
                    mode="status",
                    project_root=str(self.project_root),
                    json_store=json_store.status(),
                    ladybug_store=ladybug_store.status(),
                ),
                output_format,
            )

        sync_report: dict[str, Any] | None = None
        if mode == "update":
            sync_report = _compact_sync_report(
                self._run_incremental_sync(int(arguments.get("max_files", 20_000)))
            )

        try:
            snapshot = KnowledgeGraphBuilder(str(self.project_root)).build(
                level=arguments.get("level", "file"),
                focus=arguments.get("focus"),
                include_docs=bool(arguments.get("include_docs", True)),
                include_symbols=bool(arguments.get("include_symbols", True)),
                max_nodes=int(arguments.get("max_nodes", 50_000)),
                max_edges=int(arguments.get("max_edges", 100_000)),
            )
            write_result = self._write_snapshot(
                snapshot,
                json_store,
                ladybug_store,
                str(arguments.get("backend", "json")),
            )
        except LadybugUnavailableError as exc:
            return apply_toon_format_to_response(
                build_error(error=str(exc)),
                output_format,
            )

        response = build_response(
            verdict="INFO",
            mode=mode,
            project_root=str(self.project_root),
            storage=write_result,
            stats=snapshot.stats,
            truncated=snapshot.truncated,
        )
        if sync_report is not None:
            response["incremental_sync"] = sync_report
        return apply_toon_format_to_response(response, output_format)

    def _write_snapshot(
        self,
        snapshot: Any,
        json_store: JsonKnowledgeGraphStore,
        ladybug_store: LadybugKnowledgeGraphStore,
        backend: str,
    ) -> dict[str, Any]:
        if backend == "json":
            return {"backend": "json", "json_store": json_store.write(snapshot)}
        if backend == "ladybug":
            return {
                "backend": "ladybug",
                "ladybug_store": ladybug_store.write(snapshot),
            }
        if backend in {"both", "hybrid"}:
            return {
                "backend": "hybrid",
                "json_store": json_store.write(snapshot),
                "ladybug_store": ladybug_store.write(snapshot),
            }
        raise ValueError("backend must be one of: json, ladybug, both, hybrid")

    def _run_incremental_sync(self, max_files: int) -> dict[str, Any]:
        from ...ast_cache import ASTCache

        cache = ASTCache(str(self.project_root))
        try:
            result = IncrementalSync(cache).sync(max_files=max_files)
            return result.to_dict()
        finally:
            cache.close()


KnowledgeGraphIndexTool = CodeGraphKnowledgeIndexTool


def _compact_sync_report(report: dict[str, Any]) -> dict[str, Any]:
    """Drop verbose per-file lists from incremental-sync report."""

    return {
        key: value
        for key, value in report.items()
        if key not in {"details", "deleted", "updated", "new", "modified"}
    }
