#!/usr/bin/env python3
"""assess_change_impact MCP tool."""

from __future__ import annotations

from typing import Any

from ...intelligence.formatters import format_impact_result
from ...intelligence.impact_analyzer import ImpactAnalyzer
from ...intelligence.project_indexer import ProjectIndexer
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

VALID_CHANGE_TYPES = ("signature_change", "behavior_change", "rename", "delete")


class AssessChangeImpactTool(BaseMCPTool):
    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self._indexer: ProjectIndexer | None = None
        self._owns_indexer: bool = True

    def set_indexer(self, indexer: ProjectIndexer) -> None:
        """Set a shared indexer (owned externally, e.g. by the server)."""
        self._indexer = indexer
        self._owns_indexer = False

    def _ensure_indexed(self) -> ProjectIndexer:
        """Lazily create and populate the project indexer."""
        if self._indexer is None:
            self._indexer = ProjectIndexer(self.project_root or "")
            self._owns_indexer = True
        self._indexer.ensure_indexed()
        return self._indexer

    def set_project_path(self, project_path: str) -> None:
        """Override to reset indexer when project path changes."""
        super().set_project_path(project_path)
        if self._owns_indexer:
            self._indexer = None

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "assess_change_impact",
            "description": "Assess the blast radius of a code change — identify affected files, functions, and tests.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Symbol or file to assess",
                    },
                    "change_type": {
                        "type": "string",
                        "enum": list(VALID_CHANGE_TYPES),
                        "default": "behavior_change",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Max transitive depth",
                        "default": 3,
                    },
                    "include_tests": {"type": "boolean", "default": True},
                    "output_format": {
                        "type": "string",
                        "enum": ["summary", "json"],
                        "default": "summary",
                    },
                },
                "required": ["target"],
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "target" not in arguments or not arguments["target"]:
            raise ValueError("'target' is required")
        ct = arguments.get("change_type", "behavior_change")
        if ct not in VALID_CHANGE_TYPES:
            raise ValueError(f"Invalid change_type '{ct}'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        target = arguments["target"]
        change_type = arguments.get("change_type", "behavior_change")
        depth = arguments.get("depth", 3)
        include_tests = arguments.get("include_tests", True)
        output_format = arguments.get("output_format", "summary")

        # Ensure project is indexed before analysis
        indexer = self._ensure_indexed()
        analyzer = ImpactAnalyzer(
            indexer.call_graph, indexer.dep_graph, indexer.symbol_index
        )

        try:
            result = analyzer.assess(target, change_type, depth, include_tests)
            result_data = result.to_dict()
            formatted = format_impact_result(result_data, output_format)
            return {"result": formatted, "data": result_data}
        except Exception as e:
            logger.error(f"Error assessing impact for '{target}': {e}")
            return {"error": str(e)}
