"""Coupling Metrics Analyzer Tool — MCP Tool.

Quantifies module coupling: fan-out (dependencies), fan-in (dependents),
instability, and risk classification per file.
"""
from __future__ import annotations

from typing import Any

from ...analysis.coupling_metrics import (
    CouplingMetricsAnalyzer,
    CouplingResult,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CouplingMetricsTool(BaseMCPTool):
    """MCP tool for analyzing module coupling metrics."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "coupling_metrics",
            "description": (
                "Quantify module coupling: fan-out (dependencies), "
                "fan-in (dependents), instability, and risk."
                "\n\n"
                "Coupling metrics reveal architectural health: "
                "high fan-out means a module depends on too many others "
                "(fragile), high fan-in means many modules depend on it "
                "(critical). Instability = fan_out / (fan_in + fan_out)."
                "\n\n"
                "Risk Levels:\n"
                "- STABLE: instability < 0.3 (safe to depend on)\n"
                "- FLEXIBLE: 0.3-0.7 (balanced)\n"
                "- UNSTABLE: > 0.7 (change frequently, risky to depend on)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During architecture reviews to identify coupling hotspots\n"
                "- Before refactoring to understand blast radius\n"
                "- To find modules that are too critical (high fan-in) "
                "or too coupled (high fan-out)"
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
        analyzer = CouplingMetricsAnalyzer()
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

    def _format_json(self, result: CouplingResult) -> dict[str, Any]:
        return {
            "result": result.to_dict(),
        }

    def _format_toon(self, result: CouplingResult) -> dict[str, Any]:
        from ...formatters.toon_encoder import ToonEncoder

        lines: list[str] = []
        lines.append("Coupling Metrics Analysis")
        lines.append("=" * 40)
        lines.append(f"Project: {result.project_root}")
        lines.append(f"Files: {result.total_files}")
        lines.append(f"Dependencies: {result.total_edges}")
        lines.append(f"Avg fan-out: {result.avg_fan_out:.1f}")
        lines.append(f"Avg fan-in: {result.avg_fan_in:.1f}")
        lines.append("")

        if result.most_coupled:
            lines.append("Most Coupled (high fan-out):")
            for m in result.most_coupled[:5]:
                lines.append(
                    f"  [{m.risk}] {m.file_path}: "
                    f"out={m.fan_out}, in={m.fan_in}, "
                    f"I={m.instability:.2f}"
                )
            lines.append("")

        if result.most_critical:
            lines.append("Most Critical (high fan-in):")
            for m in result.most_critical[:5]:
                lines.append(
                    f"  [{m.risk}] {m.file_path}: "
                    f"out={m.fan_out}, in={m.fan_in}, "
                    f"I={m.instability:.2f}"
                )
            lines.append("")

        unstable = result.unstable_files
        if unstable:
            lines.append(f"Unstable files ({len(unstable)}):")
            for m in unstable[:10]:
                lines.append(f"  {m.file_path}: out={m.fan_out}")
        else:
            lines.append("No unstable files detected.")

        toon = ToonEncoder()
        content = "\n".join(lines)
        return {
            "content": [{"type": "text", "text": toon.encode(content)}],
            "summary": {
                "project_root": result.project_root,
                "total_files": result.total_files,
                "total_edges": result.total_edges,
                "unstable_count": len(result.unstable_files),
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "json")
        if fmt not in ("json", "toon"):
            raise ValueError(f"Invalid format: {fmt}")
        return True
