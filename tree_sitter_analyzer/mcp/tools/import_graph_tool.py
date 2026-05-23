#!/usr/bin/env python3
"""
CodeGraph Import Graph MCP Tool — File-level import dependency analysis.

Exposes ImportGraph capabilities via MCP protocol. Modes:
  summary   — project-wide import dependency overview
  deps      — forward dependencies of a file (what it imports)
  dependents — reverse dependencies of a file (who imports it)
  blast_radius — transitive reverse deps (all files affected by a change)
  cycles    — detect circular import chains
  coupling  — most-imported / most-importing files (hotspots)

CodeGraph parity: equivalent to CodeGraph's file-dependency-graph feature.
"""

from typing import Any

from ...import_graph import ImportGraph
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphImportGraphTool(BaseMCPTool):
    """MCP Tool for file-level import dependency analysis (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._graph: ImportGraph | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._graph = None

    def _get_graph(self) -> ImportGraph:
        if self._graph is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            self._graph = ImportGraph(self.project_root)
        return self._graph

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_import_graph",
            "description": (
                "File-level import dependency graph (CodeGraph parity). "
                "Modes: summary (project overview), deps (what a file imports), "
                "dependents (who imports a file), blast_radius (transitive impact), "
                "cycles (circular imports), coupling (import hotspots). "
                "Requires ast_cache index to be built first (run ast_cache mode=index). "
                "No other tool provides file-level import dependency analysis."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": [
                        "summary",
                        "deps",
                        "dependents",
                        "blast_radius",
                        "cycles",
                        "coupling",
                    ],
                    "description": "Operation mode (default: summary)",
                    "default": "summary",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path (required for deps, dependents, blast_radius)",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max traversal depth for blast_radius (default: 10)",
                    "default": 10,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "required": ["mode"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "summary")
        valid_modes = {
            "summary",
            "deps",
            "dependents",
            "blast_radius",
            "cycles",
            "coupling",
        }
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {valid_modes}")
        if mode in ("deps", "dependents", "blast_radius") and not arguments.get(
            "file_path"
        ):
            raise ValueError(f"file_path is required for mode '{mode}'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "summary")
        output_format = arguments.get("output_format", "toon")
        graph = self._get_graph()

        if mode == "summary":
            graph.build()
            result = {
                "success": True,
                "verdict": "INFO",
                "mode": "summary",
                **graph.summary(),
            }

        elif mode == "deps":
            file_path = arguments["file_path"]
            resolved = self.resolve_and_validate_file_path(file_path)
            deps = graph.dependencies_of(resolved)
            result = {
                "success": True,
                "verdict": "INFO" if deps else "NOT_FOUND",
                "mode": "deps",
                "file": file_path,
                "dependency_count": len(deps),
                "dependencies": deps,
            }

        elif mode == "dependents":
            file_path = arguments["file_path"]
            resolved = self.resolve_and_validate_file_path(file_path)
            dependents = graph.dependents_of(resolved)
            result = {
                "success": True,
                "verdict": "INFO" if dependents else "NOT_FOUND",
                "mode": "dependents",
                "file": file_path,
                "dependent_count": len(dependents),
                "dependents": dependents,
            }

        elif mode == "blast_radius":
            file_path = arguments["file_path"]
            max_depth = arguments.get("max_depth", 10)
            resolved = self.resolve_and_validate_file_path(file_path)
            radius = graph.blast_radius(resolved, max_depth=max_depth)
            affected = radius.get("affected_files", [])
            result = {
                "success": True,
                "verdict": "REVIEW" if len(affected) > 5 else "INFO",
                "mode": "blast_radius",
                **radius,
            }

        elif mode == "cycles":
            graph_result = graph.build()
            result = {
                "success": True,
                "verdict": "CAUTION" if graph_result.cycles else "INFO",
                "mode": "cycles",
                "cycle_count": len(graph_result.cycles),
                "cycles": graph_result.cycles,
            }

        elif mode == "coupling":
            graph.build()
            summary = graph.summary()
            result = {
                "success": True,
                "verdict": "INFO",
                "mode": "coupling",
                "most_imported": summary.get("most_imported", []),
                "most_importing": summary.get("most_importing", []),
            }

        else:
            result = {
                "success": False,
                "error": f"Unknown mode: {mode}",
                "verdict": "ERROR",
            }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)
