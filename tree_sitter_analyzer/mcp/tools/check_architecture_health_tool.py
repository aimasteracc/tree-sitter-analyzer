#!/usr/bin/env python3
"""check_architecture_health MCP tool."""
from __future__ import annotations

from typing import Any

from ...intelligence.architecture_metrics import ArchitectureMetrics
from ...intelligence.dependency_graph import DependencyGraphBuilder
from ...intelligence.formatters import format_architecture_report
from ...intelligence.symbol_index import SymbolIndex
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

VALID_CHECKS = ("coupling_metrics", "circular_dependencies", "layer_violations", "god_classes", "dead_code", "stability_metrics", "hotspots")


class CheckArchitectureHealthTool(BaseMCPTool):
    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self._dep_graph = DependencyGraphBuilder()
        self._symbol_index = SymbolIndex()
        self._metrics = ArchitectureMetrics(self._dep_graph, self._symbol_index)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "check_architecture_health",
            "description": "Assess architecture health: coupling metrics, circular dependencies, layer violations, god classes, dead code.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Project or module path to analyze"},
                    "checks": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(VALID_CHECKS)},
                        "description": "Which checks to run",
                    },
                    "layer_rules": {
                        "type": "object",
                        "description": "Custom layer dependency rules",
                    },
                    "output_format": {"type": "string", "enum": ["summary", "json"], "default": "summary"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "path" not in arguments or not arguments["path"]:
            raise ValueError("'path' is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        path = arguments["path"]
        checks = arguments.get("checks")
        layer_rules = arguments.get("layer_rules")
        output_format = arguments.get("output_format", "summary")

        try:
            report = self._metrics.compute_report(path, checks=checks, layer_rules=layer_rules)
            report_data = report.to_dict()
            formatted = format_architecture_report(report_data, output_format)
            return {"result": formatted, "data": report_data}
        except Exception as e:
            logger.error(f"Error checking architecture health: {e}")
            return {"error": str(e)}
