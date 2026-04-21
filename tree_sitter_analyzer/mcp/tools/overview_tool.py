#!/usr/bin/env python3
"""
Overview MCP Tool - Unified project health report as an MCP tool.

Aggregates results from dependency analysis, health scoring, pattern detection,
security scanning, dead code detection, ownership analysis, and blast radius analysis.
"""
from __future__ import annotations

from typing import Any

from ...overview.aggregator import OverviewAggregator
from ...overview.reporter import OverviewReporter


class OverviewTool:
    """Unified project overview tool for MCP."""

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the overview tool.

        Args:
            project_root: Root directory of the project to analyze
        """
        self.project_root = project_root

    def get_name(self) -> str:
        """Get the tool name."""
        return "overview"

    def get_description(self) -> str:
        """Get the tool description."""
        return """Generate a unified project overview report.

Aggregates results from multiple analysis tools:
- Dependency graph (file relationships, cycles)
- Health scores (file grades, risk metrics)
- Design patterns (pattern detection)
- Security issues (vulnerability scanning)
- Dead code (unused code detection)
- Ownership (code ownership metrics)
- Blast radius (impact analysis)

Parameters:
- include (optional): List of specific analyses to run (default: all)
  Options: dependency_graph, health_score, design_patterns, security_scan,
  dead_code_analysis, ownership, blast_radius
- format (optional): Output format - "markdown", "json", or "toon" (default: "markdown")
- parallel (optional): Enable parallel execution (default: true)

Returns:
- Comprehensive project health report with metrics, findings, and recommendations
"""

    def get_tool_definition(self) -> dict[str, Any]:
        """Get MCP tool definition.

        Returns:
            Tool definition dictionary
        """
        return {
            "name": "overview",
            "description": self.get_description(),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "include": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "dependency_graph",
                                "health_score",
                                "design_patterns",
                                "security_scan",
                                "dead_code_analysis",
                                "ownership",
                                "blast_radius",
                            ],
                        },
                        "description": "Specific analyses to include (default: all)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json", "toon"],
                        "description": "Output format (default: markdown)",
                    },
                    "parallel": {
                        "type": "boolean",
                        "description": "Enable parallel execution (default: true)",
                    },
                },
            },
        }

    def get_parameters(self) -> dict[str, Any]:
        """Get the tool parameters schema.

        Returns:
            Parameters schema dictionary
        """
        return {
            "properties": {
                "include": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific analyses to include",
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json", "toon"],
                    "description": "Output format",
                },
                "parallel": {
                    "type": "boolean",
                    "description": "Enable parallel execution",
                },
            },
            "required": [],
        }

    def execute(self, arguments: dict[str, Any]) -> str:
        """Execute the overview tool.

        Args:
            arguments: Tool arguments from MCP request

        Returns:
            Formatted overview report
        """
        # Get parameters
        include = arguments.get("include")
        output_format = arguments.get("format", "markdown")
        parallel = arguments.get("parallel", True)

        # Map include argument names to internal names
        include_mapping = {
            "dependency_graph": "dependency_graph",
            "health_score": "health_score",
            "design_patterns": "design_patterns",
            "security_scan": "security_scan",
            "dead_code": "dead_code_analysis",
            "ownership": "ownership",
            "blast_radius": "blast_radius",
        }

        # Convert include list if provided
        include_list = None
        if include:
            include_list = [include_mapping[name] for name in include]

        # Create aggregator and generate report
        aggregator = OverviewAggregator(
            self.project_root or ".",
            parallel=parallel,
        )
        report = aggregator.generate_overview(include=include_list)

        # Create reporter and format output
        reporter = OverviewReporter(report)

        if output_format == "json":
            return reporter.generate_json()
        if output_format == "toon":
            return reporter.generate_toon()
        return reporter.generate_markdown()
