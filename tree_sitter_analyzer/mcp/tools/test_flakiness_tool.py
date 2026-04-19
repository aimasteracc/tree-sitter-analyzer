"""Test Flakiness Tool — MCP Tool.

Analyzes test files for patterns that cause unreliable/flaky test results.
"""
from __future__ import annotations

from typing import Any

from ...analysis.test_flakiness import (
    FlakinessAnalyzer,
    FlakinessResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class TestFlakinessTool(BaseMCPTool):
    """MCP tool for detecting flaky test patterns."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "test_flakiness",
            "description": (
                "Analyze test files for flakiness risk factors. "
                "\n\n"
                "Detects patterns that cause unreliable tests: "
                "sleep/wait calls, random data generation, time-dependent assertions, "
                "and shared mutable state."
                "\n\n"
                "Supported Languages:\n"
                "- Python: time.sleep, random, uuid, datetime.now\n"
                "- JavaScript/TypeScript: setTimeout, Math.random, new Date\n"
                "- Java: Thread.sleep, Random, static mutable fields\n"
                "\n"
                "Factor Types:\n"
                "- sleep_wait: timing-dependent test (high)\n"
                "- random_usage: non-deterministic data (medium)\n"
                "- time_dependent: clock-dependent assertions (medium)\n"
                "- mutable_shared_state: shared mutable class vars (medium)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find why tests fail intermittently\n"
                "- To audit test suite reliability\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to a test file to analyze.",
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
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {"error": "file_path must be provided", "format": output_format}

        analyzer = FlakinessAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: FlakinessResult) -> dict[str, Any]:
        return result.to_dict()

    def _format_toon(self, result: FlakinessResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Test Flakiness Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Risk level: {result.risk_level}")
        lines.append(f"Total factors: {result.total_factors}")
        lines.append("")

        if result.factors:
            for f in result.factors:
                lines.append(
                    f"  L{f.line_number}: [{f.factor_type}] [{f.severity}] {f.message}"
                )
        else:
            lines.append("No flakiness risk factors found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_factors": result.total_factors,
            "risk_level": result.risk_level,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
