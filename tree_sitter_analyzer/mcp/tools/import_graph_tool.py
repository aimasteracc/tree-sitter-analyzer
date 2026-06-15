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
from ._validators import invalid_enum_error
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
                    "enum": [
                        "summary",
                        "deps",
                        "dependents",
                        "blast_radius",
                        "cycles",
                        "coupling",
                    ],
                    "description": (
                        "Operation mode. Inferred when omitted: 'deps' if "
                        "file_path is given, else 'summary' (#575)."
                    ),
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
            # #575: mode is NOT required — it has a default and is inferred from
            # file_path (the required-with-default contradiction is reconciled).
            "required": [],
            "additionalProperties": False,
        }

    @staticmethod
    def _effective_mode(arguments: dict[str, Any]) -> str:
        """#575: resolve the mode when omitted. A bare ``file_path`` means the
        agent wants that file's imports (``deps``), not the project ``summary``
        that ignores file_path — answering a different question than asked.
        """
        explicit = arguments.get("mode")
        if explicit:
            return str(explicit)
        return "deps" if arguments.get("file_path") else "summary"

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = self._effective_mode(arguments)
        valid_modes = [
            "summary",
            "deps",
            "dependents",
            "blast_radius",
            "cycles",
            "coupling",
        ]
        if mode not in valid_modes:
            raise invalid_enum_error("mode", mode, valid_modes)
        if mode in ("deps", "dependents", "blast_radius") and not arguments.get(
            "file_path"
        ):
            raise ValueError(f"file_path is required for mode '{mode}'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = self._effective_mode(arguments)
        output_format = arguments.get("output_format", "toon")
        graph = self._get_graph()

        if mode == "summary":
            graph.build()
            result = {
                "success": True,
                "verdict": "INFO",
                "mode": "summary",
                **graph.summary(),
                # Always include 'edges' key for schema consistency — empty in summary
                # mode since the full list is available via mode=deps/dependents.
                "edges": [],
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
                # Bug #784 fix: surface the detection scope so agents understand
                # why this count may differ from ``health action=deps mode=cycles``.
                # This tool walks the *ImportGraph* (ast_cache-backed, module-path
                # resolved import chains).  ``health action=deps mode=cycles`` walks
                # the *file-level DependencyGraph* (different edge types, different
                # resolution).  Neither count is wrong; they measure different things.
                "scope": "import_resolution_graph",
                "scope_note": (
                    "Counts cycles in the import-resolution graph. "
                    "Use health action=deps mode=cycles for file-dependency cycles "
                    "(different graph, legitimately different count)."
                ),
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

        # #577: uniform agent_summary across all facade actions.
        verdict: str = result.get("verdict", "INFO")
        result["agent_summary"] = _imports_agent_summary(mode, verdict, result)

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


def _imports_agent_summary(
    mode: str,
    verdict: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Build a concise agent_summary block for codegraph_import_graph results."""
    if mode == "summary":
        total = result.get("total_files", 0)
        edges = result.get("total_edges", 0)
        summary_line = f"imports: {total} file(s), {edges} import edge(s)"
        next_step = "Use mode=deps for a file's imports, mode=blast_radius for impact."
    elif mode == "deps":
        file_path = result.get("file", "?")
        count = result.get("dependency_count", 0)
        summary_line = f"imports deps: {file_path!r} → {count} import(s)"
        next_step = (
            "Use mode=blast_radius to see which files are at risk if this changes."
        )
    elif mode == "dependents":
        file_path = result.get("file", "?")
        count = result.get("dependent_count", 0)
        summary_line = f"imports dependents: {file_path!r} ← {count} dependent(s)"
        next_step = "Dependents above must be retested when this file changes."
    elif mode == "blast_radius":
        affected = len(result.get("affected_files", []))
        summary_line = f"imports blast_radius: {affected} file(s) at risk"
        next_step = (
            "Run tests for all affected files before committing changes."
            if affected > 0
            else "No downstream files at risk."
        )
    elif mode == "cycles":
        cycles = result.get("cycle_count", 0)
        summary_line = f"imports cycles: {cycles} circular chain(s) detected"
        next_step = (
            "Break the circular imports listed above to improve maintainability."
            if cycles > 0
            else "No circular imports detected."
        )
    elif mode == "coupling":
        summary_line = "imports coupling: top import hotspots listed"
        next_step = "Heavily-imported files are high-risk change points — review before editing."
    else:  # pragma: no cover — validate_arguments() rejects all non-enum modes before execute() runs
        summary_line = f"imports {mode}: {verdict.lower()}"
        next_step = ""
    return {"summary_line": summary_line, "verdict": verdict, "next_step": next_step}
