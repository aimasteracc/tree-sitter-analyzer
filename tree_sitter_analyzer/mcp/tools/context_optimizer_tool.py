#!/usr/bin/env python3
"""
Context Optimizer MCP Tool - LLM context window optimization as an MCP tool.

Provides intelligent code context summarization by scoring and filtering
code elements based on complexity, dependencies, and usage patterns.
"""
from __future__ import annotations

from typing import Any

from ...analysis.context_optimizer import (
    calculate_compression_ratio,
    optimize_for_llm,
)


class ContextOptimizerTool:
    """Context optimizer tool for reducing token consumption while preserving semantic information."""

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the context optimizer tool.

        Args:
            project_root: Root directory of the project (optional, for future use)
        """
        self.project_root = project_root

    def get_name(self) -> str:
        """Get the tool name."""
        return "context_optimizer"

    def get_description(self) -> str:
        """Get the tool description."""
        return """Optimize code context for LLM context windows.

Intelligently reduces token consumption of code analysis output while
preserving semantically important information.

Algorithm:
- Scores code elements by importance (complexity + dependencies + call frequency)
- Filters by threshold (keep top N% most important elements)
- Reconstructs optimized output

Use Cases:
- Reduce large analysis outputs to fit in LLM context windows
- Focus LLM attention on high-value code elements
- Improve analysis quality by removing noise

Parameters:
- toon_output (required): TOON formatted code output to optimize
- threshold (optional): Importance threshold 0.0-1.0 (default: 0.5, keeps top 50%)
- dependency_counts (optional): Element name → dependency count mapping
- call_frequencies (optional): Element name → call frequency mapping

Returns:
- Optimized TOON output with compression ratio
"""

    def get_tool_definition(self) -> dict[str, Any]:
        """Get MCP tool definition.

        Returns:
            Tool definition dictionary
        """
        return {
            "name": "context_optimizer",
            "description": self.get_description(),
            "inputSchema": {
                "type": "object",
                "properties": self.get_parameters()["properties"],
                "required": self.get_parameters()["required"],
            },
        }

    def get_parameters(self) -> dict[str, Any]:
        """Get the tool parameters schema.

        Returns:
            Parameters schema dictionary
        """
        return {
            "properties": {
                "toon_output": {
                    "type": "string",
                    "description": "TOON formatted code output to optimize",
                },
                "threshold": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Importance threshold (0.0-1.0, default 0.5)",
                },
                "dependency_counts": {
                    "type": "object",
                    "description": "Element name → dependency count mapping",
                },
                "call_frequencies": {
                    "type": "object",
                    "description": "Element name → call frequency mapping",
                },
            },
            "required": ["toon_output"],
        }

    def execute(self, arguments: dict[str, Any]) -> str:
        """Execute the context optimizer tool.

        Args:
            arguments: Tool arguments from MCP request

        Returns:
            Optimized TOON output with metadata
        """
        toon_output = arguments.get("toon_output", "")
        threshold = arguments.get("threshold", 0.5)
        dependency_counts = arguments.get("dependency_counts")
        call_frequencies = arguments.get("call_frequencies")

        # Optimize the TOON output
        optimized = optimize_for_llm(
            toon_output,
            threshold=threshold,
            dependency_counts=dependency_counts,
            call_frequencies=call_frequencies,
        )

        # Calculate compression ratio
        compression_ratio = calculate_compression_ratio(toon_output, optimized)

        # Format result with metadata
        result = f"""# Context Optimized Output
# Compression: {compression_ratio:.1%} reduction
# Threshold: {threshold:.1%}

{optimized}
"""

        return result
