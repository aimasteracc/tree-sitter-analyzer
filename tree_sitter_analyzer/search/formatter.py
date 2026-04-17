"""
Result Formatter Module

Formats search results into a unified, human-readable output format.
Supports multiple output formats (text, json, TOON).
"""
from __future__ import annotations

import json
from typing import Any

from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder
from tree_sitter_analyzer.utils import setup_logger

# Set up logging
logger = setup_logger(__name__)


class SearchResultFormatter:
    """
    Formats search results into unified output.

    Provides multiple output formats:
    - text: Plain text with formatting
    - json: Structured JSON output
    - toon: Compact TOON format (using ToonEncoder)
    """

    def __init__(self) -> None:
        """Initialize the result formatter."""
        self.toon_encoder = ToonEncoder()

    def format(
        self,
        results: list[dict[str, Any]],
        format_type: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Format search results into the specified format.

        Args:
            results: List of search result dictionaries
            format_type: Output format ("text", "json", "toon")
            metadata: Optional metadata (query, execution_time, etc.)

        Returns:
            Formatted output string
        """
        if format_type == "json":
            return self._format_json(results, metadata)
        elif format_type == "toon":
            return self._format_toon(results, metadata)
        else:  # text
            return self._format_text(results, metadata)

    def _format_text(
        self,
        results: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Format results as plain text."""
        lines = []

        if metadata:
            query = metadata.get("query", "")
            exec_time = metadata.get("execution_time", 0)
            tool_used = metadata.get("tool_used", "")
            lines.append(f"Query: {query}")
            if tool_used:
                lines.append(f"Tool: {tool_used}")
            if exec_time:
                lines.append(f"Time: {exec_time:.3f}s")
            lines.append("")

        if not results:
            lines.append("No results found.")
        else:
            lines.append(f"Found {len(results)} result(s):")
            lines.append("")

            for i, result in enumerate(results, 1):
                lines.append(f"{i}. {result.get('file', 'Unknown file')}")

                if "line" in result:
                    content = result.get("content", "")
                    lines.append(f"   Line {result['line']}: {content}")

                # Add additional fields
                for key, value in result.items():
                    if key not in ("file", "line", "content"):
                        lines.append(f"   {key}: {value}")

                lines.append("")

        return "\n".join(lines)

    def _format_json(
        self,
        results: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Format results as JSON."""
        output = {
            "results": results,
            "count": len(results),
        }

        if metadata:
            output["metadata"] = metadata

        return json.dumps(output, indent=2)

    def _format_toon(
        self,
        results: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Format results in TOON format."""
        lines = [
            "# Search Results",
            "",
        ]

        if metadata:
            query = metadata.get("query", "")
            lines.append(f"Query: {query}")
            lines.append("")

        if not results:
            lines.append("No results found.")
        else:
            lines.append(f"Found {len(results)} result(s):")
            lines.append("")

            for result in results:
                file_path = result.get("file", "")
                line_num = result.get("line", "")

                if line_num:
                    lines.append(f"- {file_path}:{line_num}")
                    content = result.get("content", "")
                    if content:
                        lines.append(f"  {content}")
                else:
                    lines.append(f"- {file_path}")

                # Add additional fields
                for key, value in result.items():
                    if key not in ("file", "line", "content"):
                        lines.append(f"  {key}: {value}")

                lines.append("")

        return "\n".join(lines)


def format_search_error(
    error: str,
    format_type: str = "text",
) -> str:
    """
    Format an error message.

    Args:
        error: Error message
        format_type: Output format

    Returns:
        Formatted error message
    """
    if format_type == "json":
        return json.dumps({"error": error, "results": []})
    elif format_type == "toon":
        return f"# Error\n\n{error}\n"
    else:  # text
        return f"Error: {error}"
