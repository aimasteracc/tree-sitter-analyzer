"""Method Chain Tool — MCP Tool.

Analyzes method/attribute chain length. Detects Law of Demeter violations
where code reaches deeply into object internals via long chains.
"""
from __future__ import annotations

from typing import Any

from ...analysis.method_chain import (
    MethodChainAnalyzer,
    MethodChainResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class MethodChainTool(BaseMCPTool):
    """MCP tool for analyzing method/attribute chain length."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "method_chain",
            "description": (
                "Analyze method/attribute chain length (Law of Demeter). "
                "\n\n"
                "Detects excessively long method chains (a.b().c().d()) "
                "that indicate Law of Demeter violations. Long chains "
                "couple code to deep object internals, making it fragile "
                "and hard to debug."
                "\n\n"
                "Supported Languages:\n"
                "- Python: obj.attr.method().field\n"
                "- JavaScript/TypeScript: obj.prop.method().field\n"
                "- Java: obj.getField().getMethod().getValue()\n"
                "- Go: obj.Field.Method().Value\n"
                "\n"
                "Severity Levels:\n"
                "- ok (2-3 links): Acceptable\n"
                "- long_chain (4-5 links): Consider refactoring\n"
                "- train_wreck (6+ links): Should introduce intermediate variables\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to spot Law of Demeter violations\n"
                "- To identify code that is tightly coupled to object internals\n"
                "- As a coupling-focused complement to other metrics\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For parameter coupling (use parameter_coupling)\n"
                "- For module-level coupling (use coupling_metrics)\n"
                "- For feature envy detection (use feature_envy)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze. "
                            "If provided, analyzes only this file."
                        ),
                    },
                    "threshold": {
                        "type": "integer",
                        "description": (
                            "Chain length threshold. Chains at or "
                            "above this length are flagged. Default: 4."
                        ),
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
        threshold = arguments.get("threshold", 4)
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = MethodChainAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result, threshold)
        return self._format_toon(result, threshold)

    def _format_json(
        self,
        result: MethodChainResult,
        threshold: int,
    ) -> dict[str, Any]:
        hotspots = [
            h for h in result.hotspots if h.chain_length >= threshold
        ]
        return {
            "file": result.file_path,
            "total_chains": result.total_chains,
            "max_chain_length": result.max_chain_length,
            "threshold": threshold,
            "hotspot_count": len(hotspots),
            "hotspots": [
                {
                    "line": h.line_number,
                    "chain_length": h.chain_length,
                    "severity": h.severity,
                    "expression": h.expression,
                }
                for h in hotspots
            ],
        }

    def _format_toon(
        self,
        result: MethodChainResult,
        threshold: int,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Method Chain Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total chains: {result.total_chains}")
        lines.append(f"Max chain length: {result.max_chain_length}")
        lines.append("")

        hotspots = [h for h in result.hotspots if h.chain_length >= threshold]
        if hotspots:
            lines.append(f"Long chains (>= {threshold} links):")
            for h in hotspots:
                lines.append(
                    f"  L{h.line_number}: {h.chain_length} links ({h.severity})"
                )
                lines.append(f"    {h.expression}")
        else:
            lines.append(
                f"No chains exceed length threshold ({threshold})."
            )

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_chains": result.total_chains,
            "max_chain_length": result.max_chain_length,
            "hotspot_count": len(hotspots),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
