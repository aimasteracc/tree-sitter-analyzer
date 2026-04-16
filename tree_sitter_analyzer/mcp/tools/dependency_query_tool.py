"""
MCP tool for dependency graph queries and health scoring.

Provides graph traversal (dependents, blast radius), health scores,
and visualization output (Mermaid/DOT).
"""

from __future__ import annotations

from typing import Any

from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.mcp.utils.graph_service import (
    ProjectGraph,
    build_graph_from_files,
    score_project_health,
)
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


class DependencyQueryTool(BaseMCPTool):
    """Query the project dependency graph for dependents, blast radius, and health scores."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "dependency_query",
            "description": (
                "Query the project dependency graph — find dependents, compute blast radius, "
                "get health scores (A-F) for files, or export the full graph as Mermaid/DOT.\n\n"
                "WHEN TO USE:\n"
                "- Before deleting or moving a file: use blast_radius to see all affected files\n"
                "- To understand coupling: use dependents to see who depends on a module\n"
                "- For project health overview: use health_scores to grade all files A-F\n"
                "- For visualization: use export with format=mermaid or format=dot\n\n"
                "WHEN NOT TO USE:\n"
                "- Simple symbol usage search — use trace_impact instead\n"
                "- File-level metrics only — use check_code_scale instead"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": [
                            "dependents",
                            "dependencies",
                            "blast_radius",
                            "health_scores",
                            "export",
                        ],
                        "description": "Type of graph query to perform",
                    },
                    "node": {
                        "type": "string",
                        "description": "Target file/module for dependents/blast_radius queries (relative path from project root)",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum traversal depth for blast_radius (default: 10)",
                        "default": 10,
                    },
                    "format": {
                        "type": "string",
                        "enum": ["mermaid", "dot", "json"],
                        "description": "Output format for export query (default: json)",
                        "default": "json",
                    },
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of files to scope the graph (default: auto-discover from project root)",
                    },
                },
                "required": ["query_type"],
                "examples": [
                    {"query_type": "blast_radius", "node": "src/main.py"},
                    {"query_type": "dependents", "node": "src/models/User.java"},
                    {"query_type": "health_scores"},
                    {"query_type": "export", "format": "mermaid"},
                ],
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "query_type" not in arguments:
            raise ValueError("query_type is required")
        qt = arguments["query_type"]
        valid_types = {"dependents", "dependencies", "blast_radius", "health_scores", "export"}
        if qt not in valid_types:
            raise ValueError(f"Invalid query_type: {qt}. Must be one of {valid_types}")
        if qt in ("dependents", "dependencies", "blast_radius") and "node" not in arguments:
            raise ValueError(f"node is required for query_type '{qt}'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        query_type = arguments["query_type"]
        node = arguments.get("node", "")
        max_depth = arguments.get("max_depth", 10)
        output_format = arguments.get("format", "json")

        root = self.project_root or "."
        files = arguments.get("file_paths")

        if query_type == "health_scores":
            return self._health_scores(root, files)
        if query_type == "export":
            return self._export(root, files, output_format)
        if query_type == "blast_radius":
            return self._blast_radius(root, files, node, max_depth)
        if query_type == "dependents":
            return self._dependents(root, files, node)
        if query_type == "dependencies":
            return self._dependencies(root, files, node)

        return {"success": False, "error": f"Unknown query_type: {query_type}"}

    def _build_graph(
        self, root: str, files: list[str] | None
    ) -> ProjectGraph:
        if files is None:
            import subprocess

            result = subprocess.run(
                ["fd", "-e", "java", "-e", "py", "-e", "ts", "-e", "js", "-e", "tsx",
                 "-e", "jsx", "-t", "f", ".", root, "--max-depth", "10"],
                capture_output=True, text=True, timeout=30,
            )
            files = result.stdout.strip().split("\n") if result.stdout.strip() else []

        return build_graph_from_files(files, root)

    def _dependents(
        self, root: str, files: list[str] | None, node: str
    ) -> dict[str, Any]:
        graph = self._build_graph(root, files)
        deps = graph.direct_dependents(node)
        return {
            "success": True,
            "query_type": "dependents",
            "node": node,
            "dependents": deps,
            "count": len(deps),
        }

    def _dependencies(
        self, root: str, files: list[str] | None, node: str
    ) -> dict[str, Any]:
        graph = self._build_graph(root, files)
        deps = graph.direct_dependencies(node)
        return {
            "success": True,
            "query_type": "dependencies",
            "node": node,
            "dependencies": deps,
            "count": len(deps),
        }

    def _blast_radius(
        self, root: str, files: list[str] | None, node: str, max_depth: int
    ) -> dict[str, Any]:
        graph = self._build_graph(root, files)
        result = graph.blast_radius(node, max_depth=max_depth)
        return {
            "success": True,
            "query_type": "blast_radius",
            "node": node,
            "affected_files": sorted(result.dependents),
            "depth_map": result.depth_map,
            "total_affected": len(result.dependents),
        }

    def _health_scores(
        self, root: str, files: list[str] | None
    ) -> dict[str, Any]:
        scores = score_project_health(root, file_paths=files)
        grade_distribution: dict[str, int] = {}
        results: list[dict[str, Any]] = []
        for s in scores:
            grade_distribution[s.grade] = grade_distribution.get(s.grade, 0) + 1
            results.append({
                "file": s.file_path,
                "grade": s.grade,
                "score": s.score,
                "lines": s.lines,
                "methods": s.methods,
                "imports": s.imports,
            })
        return {
            "success": True,
            "query_type": "health_scores",
            "total_files": len(results),
            "grade_distribution": grade_distribution,
            "scores": results,
        }

    def _export(
        self, root: str, files: list[str] | None, fmt: str
    ) -> dict[str, Any]:
        from tree_sitter_analyzer.analysis.dependency_graph import DependencyGraph

        graph = self._build_graph(root, files)
        nodes: dict[str, dict[str, str | int]] = {n: {} for n in graph.nodes()}
        dep_graph = DependencyGraph(nodes=nodes, edges=graph.edges)

        if fmt == "mermaid":
            output = dep_graph.to_mermaid()
        elif fmt == "dot":
            output = dep_graph.to_dot()
        else:
            output = dep_graph.to_json()

        return {
            "success": True,
            "query_type": "export",
            "format": fmt,
            "output": output,
            "node_count": len(nodes),
            "edge_count": len(graph.edges),
        }
