#!/usr/bin/env python3
"""
Output Formatter System

Provides unified output formatting with:
- Consistent JSON structure
- Multiple output formats
- Validation
- Customizable templates

Phase 4 User Experience Enhancement.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class OutputFormat(Enum):
    """Supported output formats."""
    JSON = "json"
    TEXT = "text"
    MARKDOWN = "markdown"
    TABLE = "table"


@dataclass
class OutputMetadata:
    """Metadata for output results."""
    analyzer_version: str = "1.10.3"
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    format_version: str = "1.0"
    processing_time_ms: float = 0.0


@dataclass
class OutputResult:
    """Structured output result."""
    success: bool
    data: Any
    metadata: OutputMetadata
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class OutputFormatter:
    """
    Unified output formatter.

    Provides consistent output formatting across all analyzer operations.

    Attributes:
        _format: Current output format
        _pretty: Whether to pretty-print output
        _include_metadata: Whether to include metadata
    """

    def __init__(
        self,
        output_format: OutputFormat = OutputFormat.JSON,
        pretty: bool = True,
        include_metadata: bool = True,
    ) -> None:
        """
        Initialize formatter.

        Args:
            output_format: Output format to use
            pretty: Pretty-print output
            include_metadata: Include metadata in output
        """
        self._format = output_format
        self._pretty = pretty
        self._include_metadata = include_metadata

    def format(
        self,
        data: Any,
        success: bool = True,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
        processing_time_ms: float = 0.0,
    ) -> str:
        """
        Format data according to current settings.

        Args:
            data: Data to format
            success: Whether operation was successful
            errors: List of error messages
            warnings: List of warning messages
            processing_time_ms: Processing time in milliseconds

        Returns:
            Formatted output string
        """
        metadata = OutputMetadata(processing_time_ms=processing_time_ms)

        result = OutputResult(
            success=success,
            data=data,
            metadata=metadata,
            errors=errors or [],
            warnings=warnings or [],
        )

        if self._format == OutputFormat.JSON:
            return self._format_json(result)
        if self._format == OutputFormat.TEXT:
            return self._format_text(result)
        if self._format == OutputFormat.MARKDOWN:
            return self._format_markdown(result)
        return self._format_table(result)

    def _format_json(self, result: OutputResult) -> str:
        """Format as JSON."""
        output: dict[str, Any] = {
            "success": result.success,
        }

        if self._include_metadata:
            output["metadata"] = {
                "analyzer_version": result.metadata.analyzer_version,
                "generated_at": result.metadata.generated_at,
                "format_version": result.metadata.format_version,
                "processing_time_ms": result.metadata.processing_time_ms,
            }

        output["data"] = self._serialize_data(result.data)

        if result.errors:
            output["errors"] = result.errors

        if result.warnings:
            output["warnings"] = result.warnings

        if self._pretty:
            return json.dumps(output, indent=2, ensure_ascii=False)
        return json.dumps(output, ensure_ascii=False)

    def _format_text(self, result: OutputResult) -> str:
        """Format as plain text."""
        lines: list[str] = []

        if self._include_metadata:
            lines.append(f"Analysis completed at: {result.metadata.generated_at}")
            lines.append(f"Processing time: {result.metadata.processing_time_ms:.1f}ms")
            lines.append("")

        if not result.success:
            lines.append("Status: FAILED")
            if result.errors:
                lines.append("Errors:")
                for error in result.errors:
                    lines.append(f"  - {error}")
            return "\n".join(lines)

        lines.append("Status: SUCCESS")
        lines.append("")

        # Format data
        data_str = self._format_data_text(result.data)
        lines.append(data_str)

        if result.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in result.warnings:
                lines.append(f"  - {warning}")

        return "\n".join(lines)

    def _format_markdown(self, result: OutputResult) -> str:
        """Format as Markdown."""
        lines: list[str] = []

        lines.append("# Analysis Result")
        lines.append("")

        if self._include_metadata:
            lines.append("## Metadata")
            lines.append("")
            lines.append(f"- **Generated**: {result.metadata.generated_at}")
            lines.append(f"- **Processing Time**: {result.metadata.processing_time_ms:.1f}ms")
            lines.append(f"- **Status**: {'✅ Success' if result.success else '❌ Failed'}")
            lines.append("")

        if not result.success:
            lines.append("## Errors")
            lines.append("")
            for error in result.errors:
                lines.append(f"- {error}")
            return "\n".join(lines)

        lines.append("## Results")
        lines.append("")

        # Format data as markdown
        data_md = self._format_data_markdown(result.data)
        lines.append(data_md)

        if result.warnings:
            lines.append("")
            lines.append("## Warnings")
            lines.append("")
            for warning in result.warnings:
                lines.append(f"- ⚠️ {warning}")

        return "\n".join(lines)

    def _format_table(self, result: OutputResult) -> str:
        """Format as table."""
        lines: list[str] = []

        if self._include_metadata:
            lines.append(f"Analysis: {result.metadata.generated_at}")
            lines.append(f"Time: {result.metadata.processing_time_ms:.1f}ms")
            lines.append(f"Status: {'OK' if result.success else 'FAILED'}")
            lines.append("")

        if isinstance(result.data, dict):
            lines.append(self._format_dict_table(result.data))
        elif isinstance(result.data, list):
            lines.append(self._format_list_table(result.data))
        else:
            lines.append(str(result.data))

        return "\n".join(lines)

    def _format_data_text(self, data: Any, indent: int = 0) -> str:
        """Format data as text."""
        prefix = "  " * indent

        if isinstance(data, dict):
            lines = []
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    lines.append(f"{prefix}{key}:")
                    lines.append(self._format_data_text(value, indent + 1))
                else:
                    lines.append(f"{prefix}{key}: {value}")
            return "\n".join(lines)

        if isinstance(data, list):
            lines = []
            for i, item in enumerate(data, 1):
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}[{i}]")
                    lines.append(self._format_data_text(item, indent + 1))
                else:
                    lines.append(f"{prefix}[{i}] {item}")
            return "\n".join(lines)

        return f"{prefix}{data}"

    def _format_data_markdown(self, data: Any) -> str:
        """Format data as Markdown."""
        if isinstance(data, dict):
            return self._format_dict_markdown(data)
        if isinstance(data, list):
            return self._format_list_markdown(data)
        return str(data)

    def _format_dict_markdown(self, data: dict) -> str:
        """Format dictionary as Markdown."""
        lines = []

        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"### {key}")
                lines.append("")
                lines.append(self._format_dict_markdown(value))
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                lines.append(f"### {key}")
                lines.append("")
                lines.append(self._format_list_markdown(value))
            else:
                lines.append(f"- **{key}**: {value}")

        return "\n".join(lines)

    def _format_list_markdown(self, data: list) -> str:
        """Format list as Markdown table."""
        if not data:
            return "_No items_"

        if not isinstance(data[0], dict):
            return "\n".join(f"- {item}" for item in data)

        # Get all keys
        keys = list({key for item in data for key in item.keys()})

        # Build table
        lines = ["| " + " | ".join(keys) + " |"]
        lines.append("| " + " | ".join(["---"] * len(keys)) + " |")

        for item in data:
            values = [str(item.get(key, "")) for key in keys]
            lines.append("| " + " | ".join(values) + " |")

        return "\n".join(lines)

    def _format_dict_table(self, data: dict) -> str:
        """Format dictionary as text table."""
        lines = ["Key | Value", "-" * 40]

        for key, value in data.items():
            if isinstance(value, (dict, list)):
                value_str = f"<{type(value).__name__}>({len(value)})"
            else:
                value_str = str(value)[:50]
            lines.append(f"{key} | {value_str}")

        return "\n".join(lines)

    def _format_list_table(self, data: list) -> str:
        """Format list as text table."""
        if not data:
            return "(empty)"

        lines = ["#", "-" * 5, "Value", "-" * 40]

        for i, item in enumerate(data, 1):
            if isinstance(item, (dict, list)):
                item_str = f"<{type(item).__name__}>"
            else:
                item_str = str(item)[:50]
            lines.append(f"{i} | {item_str}")

        return "\n".join(lines)

    def _serialize_data(self, data: Any) -> Any:
        """Serialize data for JSON output."""
        if hasattr(data, "to_dict"):
            return data.to_dict()
        if hasattr(data, "__dict__"):
            return {k: self._serialize_data(v) for k, v in data.__dict__.items()}
        if isinstance(data, dict):
            return {k: self._serialize_data(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._serialize_data(item) for item in data]
        return data


def format_output(
    data: Any,
    format: str = "json",
    **kwargs: Any,
) -> str:
    """
    Format data using specified format.

    Args:
        data: Data to format
        format: Output format (json, text, markdown, table)
        **kwargs: Additional arguments for formatter

    Returns:
        Formatted output string
    """
    try:
        output_format = OutputFormat(format.lower())
    except ValueError:
        output_format = OutputFormat.JSON

    formatter = OutputFormatter(output_format=output_format, **kwargs)
    return formatter.format(data)
