"""Circular Dependency Tool — MCP Tool.

Detects circular import/require dependencies in codebases.
"""
from __future__ import annotations

from typing import Any

from ...analysis.circular_dependency import (
    CircularDependencyAnalyzer,
    CircularDependencyResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CircularDependencyTool(BaseMCPTool):
    """MCP tool for detecting circular dependencies."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "circular_dependency",
            "description": (
                "Detect circular import/require dependencies in codebases. "
                "\n\n"
                "Builds an import graph from AST analysis and finds cycles via DFS. "
                "Reports cycles with severity based on length."
                "\n\n"
                "Supported Languages:\n"
                "- Python: import/from imports\n"
                "- JavaScript/TypeScript: require() and ES6 import\n"
                "- Java: import declarations\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find circular dependencies causing import errors\n"
                "- To audit module coupling\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to a file to analyze imports.",
                    },
                    "project_path": {
                        "type": "string",
                        "description": "Path to project root for full cycle detection.",
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: toon (default) or json",
                        "enum": ["toon", "json"],
                    },
                },
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        project_path = arguments.get("project_path", "")
        output_format = arguments.get("format", "toon")

        if not file_path and not project_path:
            return {"error": "file_path or project_path must be provided"}

        analyzer = CircularDependencyAnalyzer()

        if project_path:
            result = analyzer.analyze_project(project_path)
        else:
            result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return result.to_dict()
        return self._format_toon(result)

    def _format_toon(self, result: CircularDependencyResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Circular Dependency Analysis")
        lines.append(f"Root: {result.root_path}")
        lines.append(f"Import edges: {len(result.edges)}")
        lines.append(f"Cycles found: {result.total_cycles}")
        lines.append("")

        if result.cycles:
            for c in result.cycles:
                path_str = " -> ".join(c.path) + f" -> {c.path[0]}"
                lines.append(f"  [{c.severity}] Cycle ({c.length} nodes): {path_str}")
        else:
            lines.append("No circular dependencies found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_cycles": result.total_cycles,
            "edge_count": len(result.edges),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")
        return True
