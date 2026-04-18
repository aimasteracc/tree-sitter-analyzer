"""Architectural Boundary Analyzer Tool — MCP Tool.

Detects layered architecture violations: skip-layer imports,
wrong-direction dependencies, and circular layer dependencies.
"""
from __future__ import annotations

from typing import Any

from ...analysis.architectural_boundary import (
    ArchitecturalBoundaryAnalyzer,
    BoundaryResult,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ArchitecturalBoundaryTool(BaseMCPTool):
    """MCP tool for detecting layered architecture violations."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "architectural_boundary",
            "description": (
                "Detect layered architecture violations: cross-boundary imports, "
                "skip-layer dependencies, and circular layer dependencies."
                "\n\n"
                "Maps files to architectural layers (UI/Controller -> "
                "Service/Business -> Repository/DAO) based on directory naming "
                "conventions, then flags imports that violate layer boundaries."
                "\n\n"
                "Violation Types:\n"
                "- skip_layer: UI imports Repository directly (skips Service)\n"
                "- wrong_direction: Repository imports from UI/Service\n"
                "- circular: Two layers import each other\n"
                "\n"
                "Compliance Score: 1.0 = perfect layering, 0.0 = all edges violate"
                "\n\n"
                "WHEN TO USE:\n"
                "- During architecture reviews to find layer violations\n"
                "- Before refactoring to understand dependency direction\n"
                "- To enforce clean architecture in growing codebases"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["json", "toon"],
                        "description": "Output format (default: json)",
                    },
                },
                "required": [],
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        output_format = arguments.get("format", "json")

        project_root = self._get_project_root()
        analyzer = ArchitecturalBoundaryAnalyzer()
        result = analyzer.analyze_project(project_root)

        if output_format == "toon":
            return self._format_toon(result)

        return self._format_json(result)

    def _get_project_root(self) -> str:
        if self.project_root:
            return self.project_root
        bm = self.security_validator.boundary_manager
        if bm is not None:
            return str(bm.project_root)
        return "."

    def _format_json(self, result: BoundaryResult) -> dict[str, Any]:
        return {
            "result": result.to_dict(),
        }

    def _format_toon(self, result: BoundaryResult) -> dict[str, Any]:
        from ...formatters.toon_encoder import ToonEncoder

        lines: list[str] = []
        lines.append("Architectural Boundary Analysis")
        lines.append("=" * 40)
        lines.append(f"Project: {result.project_root}")
        lines.append(f"Files: {result.total_files} ({result.classified_files} classified)")
        lines.append(f"Compliance Score: {result.compliance_score:.1%}")
        lines.append("")

        if result.layer_summary:
            lines.append("Layer Distribution:")
            for ls in result.layer_summary:
                lines.append(
                    f"  {ls.layer_name}: {ls.file_count} files, "
                    f"{ls.violation_count} violations"
                )
            lines.append("")

        if result.violations:
            lines.append(f"Boundary Violations ({len(result.violations)}):")
            for v in result.violations[:10]:
                lines.append(
                    f"  [{v.violation_type}] {v.source_file} -> {v.target_file}"
                )
            if len(result.violations) > 10:
                lines.append(f"  ... and {len(result.violations) - 10} more")
            lines.append("")

        if result.circular_dependencies:
            lines.append(
                f"Circular Dependencies ({len(result.circular_dependencies)}):"
            )
            for v in result.circular_dependencies[:5]:
                lines.append(
                    f"  {v.source_file} <-> {v.target_file}"
                )
            lines.append("")

        if not result.violations and not result.circular_dependencies:
            lines.append("No boundary violations detected.")

        toon = ToonEncoder()
        content = "\n".join(lines)
        return {
            "content": [{"type": "text", "text": toon.encode(content)}],
            "summary": {
                "project_root": result.project_root,
                "total_files": result.total_files,
                "classified_files": result.classified_files,
                "compliance_score": round(result.compliance_score, 3),
                "violation_count": len(result.violations),
                "circular_count": len(result.circular_dependencies),
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "json")
        if fmt not in ("json", "toon"):
            raise ValueError(f"Invalid format: {fmt}")
        return True
