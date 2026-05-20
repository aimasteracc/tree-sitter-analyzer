#!/usr/bin/env python3
"""
Dependency Analysis MCP Tool

Exposes project_graph.py to AI agents via MCP protocol.
Provides dependency graph queries, blast radius analysis, and cycle detection.
"""

from pathlib import Path
from typing import Any

from ...project_graph import BlastRadius, DependencyGraph
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DependencyAnalysisTool(BaseMCPTool):
    """MCP Tool for project-level dependency analysis."""

    def __init__(self, project_root: str | None = None) -> None:
        self._graph: DependencyGraph | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._graph = None

    def _get_graph(self) -> DependencyGraph:
        if self._graph is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            self._graph = DependencyGraph(self.project_root)
        return self._graph

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "analyze_dependencies",
            "description": (
                "Dependency graph + blast radius. Modes: blast_radius (impact), "
                "file_deps, cycles, summary. No built-in tool provides this."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["blast_radius", "file_deps", "cycles", "summary"],
                    "description": "Analysis mode (default: summary)",
                    "default": "summary",
                },
                "file_path": {
                    "type": "string",
                    "description": "Required for blast_radius and file_deps modes. Relative or absolute path.",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "summary")
        if mode in ("blast_radius", "file_deps") and "file_path" not in arguments:
            raise ValueError(f"file_path is required for mode '{mode}'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "summary")
        output_format = arguments.get("output_format", "toon")
        graph = self._get_graph()

        if mode == "summary":
            result = _summary(graph)
        elif mode == "cycles":
            result = _cycles(graph)
        elif mode == "file_deps":
            file_path = arguments["file_path"]
            resolved = self._resolve_file(file_path, graph)
            result = _file_deps(graph, resolved)
        elif mode == "blast_radius":
            file_path = arguments["file_path"]
            resolved = self._resolve_file(file_path, graph)
            br = BlastRadius(graph)
            analysis = br.analyze(resolved)
            result = {
                "success": True,
                "file": resolved,
                "mode": "blast_radius",
                "forward_impact_count": analysis["forward_count"],
                "reverse_dependency_count": analysis["reverse_count"],
                "forward_impact": analysis["forward_impact"],
                "reverse_dependencies": analysis["reverse_dependencies"],
                "recommendation": _blast_recommendation(analysis),
            }
        else:
            raise ValueError(f"Unknown mode: {mode}")

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _resolve_file(self, file_path: str, graph: DependencyGraph) -> str:
        """Resolve file_path to a project-relative path that exists in the graph."""
        root = Path(self.project_root or ".")
        fp = Path(file_path)

        # Try direct match
        rel = (
            str(fp)
            if not fp.is_absolute()
            else str(fp.relative_to(root))
            if str(root) in str(fp)
            else str(fp)
        )
        if rel in graph._nodes or any(n.endswith(rel) for n in graph._nodes):
            return rel

        # Try resolving as absolute
        if fp.is_absolute():
            try:
                rel = str(fp.relative_to(root))
                if rel in graph._nodes:
                    return rel
            except ValueError:
                pass

        # Fuzzy: find by filename
        target_name = fp.name
        for node in graph._nodes:
            if Path(node).name == target_name:
                return node

        raise ValueError(
            f"File not found in dependency graph: {file_path}. "
            f"The graph has {len(graph._nodes)} nodes."
        )


def _summary(graph: DependencyGraph) -> dict[str, Any]:
    node_count = len(graph._nodes)
    edge_count = len(graph._edges)

    # Find hub files (most dependents = most relied upon)
    dep_counts = {n: len(graph.dependents_of(n)) for n in graph._nodes}
    hubs = sorted(dep_counts.items(), key=lambda x: -x[1])[:10]

    # Find high-fan-in files (most dependencies = most complex)
    fan_in = {n: len(graph.dependencies_of(n)) for n in graph._nodes}
    high_fan = sorted(fan_in.items(), key=lambda x: -x[1])[:10]

    return {
        "success": True,
        "mode": "summary",
        "node_count": node_count,
        "edge_count": edge_count,
        "top_hub_files": [{"file": f, "dependents": c} for f, c in hubs if c > 0],
        "high_dependency_files": [{"file": f, "deps": c} for f, c in high_fan if c > 0],
        "recommendation": (
            "Use mode='blast_radius' to assess change impact, "
            "or mode='cycles' to find circular dependencies."
        ),
    }


def _cycles(graph: DependencyGraph) -> dict[str, Any]:
    cycles = graph.find_cycles()
    return {
        "success": True,
        "mode": "cycles",
        "cycle_count": len(cycles),
        "cycles": cycles[:20],
        "recommendation": (
            f"Found {len(cycles)} circular dependencies. "
            "These can cause import errors and make refactoring harder."
            if cycles
            else "No circular dependencies detected. Project structure is clean."
        ),
    }


def _file_deps(graph: DependencyGraph, rel_path: str) -> dict[str, Any]:
    deps = graph.dependencies_of(rel_path)
    dependents = graph.dependents_of(rel_path)
    return {
        "success": True,
        "mode": "file_deps",
        "file": rel_path,
        "depends_on": deps,
        "depended_by": dependents,
        "dependency_count": len(deps),
        "dependent_count": len(dependents),
    }


def _blast_recommendation(analysis: dict[str, Any]) -> str:
    forward = analysis["forward_count"]
    reverse = analysis["reverse_count"]
    if forward == 0 and reverse == 0:
        return "Isolated file — changes here have no ripple effect."
    if forward > 20:
        return f"High-impact file — {forward} files will be affected by changes. Test thoroughly."
    if forward > 5:
        return f"Moderate impact — {forward} files depend on this. Verify downstream behavior."
    if forward > 0:
        return f"Low impact — only {forward} file(s) affected. Safe to change with basic testing."
    return "No downstream impact detected."
