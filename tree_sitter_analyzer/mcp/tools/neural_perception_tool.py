"""Neural Perception Tool — MCP Tool.

Runs ALL analyzers (not just 10) on target files via the NeuralPerception
engine, correlates findings, and produces a holistic perception map with
compound hotspots, health scores, and category coverage.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.neural_perception import (
    NeuralPerception,
    PerceptionMap,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class NeuralPerceptionTool(BaseMCPTool):
    """MCP tool that runs the full neural perception engine."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "neural_perception",
            "description": (
                "Run ALL analyzers on files and correlate findings into "
                "a holistic perception map. Each analyzer is a 'neuron' "
                "that fires on specific patterns; compound hotspots emerge "
                "where multiple neurons fire together."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Single file to perceive",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory to perceive (recursive .py)",
                    },
                    "self_perception": {
                        "type": "boolean",
                        "description": "Perceive the tool's own source code",
                    },
                    "max_files": {
                        "type": "integer",
                        "description": "Max files to process (default 50)",
                        "default": 50,
                    },
                    "format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "default": "toon",
                    },
                },
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        fmt = arguments.get("format", "toon")
        perception = NeuralPerception()

        if arguments.get("self_perception"):
            result = perception.perceive_self()
            return self._format_result(result, fmt)

        if "file_path" in arguments:
            resolved = self.resolve_and_validate_file_path(
                arguments["file_path"]
            )
            pmap = perception.perceive_file(resolved)
            return self._format_map(pmap, fmt)

        if "directory" in arguments:
            resolved = self.resolve_and_validate_directory_path(
                arguments["directory"]
            )
            max_files = arguments.get("max_files", 50)
            py_files = sorted(str(p) for p in Path(resolved).rglob("*.py"))
            py_files = py_files[:max_files]
            result = perception.perceive_files(py_files)
            return self._format_result(result, fmt)

        raise ValueError("Provide file_path, directory, or self_perception")

    def _format_map(
        self, pmap: PerceptionMap, fmt: str
    ) -> dict[str, Any]:
        data = {
            "file": pmap.file_path,
            "total_neurons": pmap.total_neurons,
            "fired_neurons": pmap.fired_neurons,
            "total_findings": pmap.total_findings,
            "health_score": pmap.health_score,
            "perception_score": round(pmap.perception_score, 3),
            "severity_distribution": pmap.severity_distribution,
            "category_coverage": pmap.category_coverage,
            "critical_hotspots": len(pmap.critical_hotspots),
            "warning_hotspots": len(pmap.hotspots)
            - len(pmap.critical_hotspots),
            "hotspots": [
                {
                    "line": h.line,
                    "end_line": h.end_line,
                    "analyzer_count": h.analyzer_count,
                    "analyzer_names": h.analyzer_names,
                    "max_severity": h.max_severity.value,
                    "finding_types": h.finding_types,
                }
                for h in pmap.hotspots[:10]
            ],
        }
        if fmt == "toon":
            return {"content": ToonEncoder().encode(data)}
        return data

    def _format_result(
        self, result: Any, fmt: str
    ) -> dict[str, Any]:
        data: dict[str, Any] = result.to_dict()
        if fmt == "toon":
            return {"content": ToonEncoder().encode(data)}
        return data
