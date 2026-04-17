#!/usr/bin/env python3
"""
Design Pattern Detection Tool — MCP Tool

Detects design patterns and anti-patterns in source code:
- Creational patterns: Singleton, Factory Method, Builder, Prototype
- Structural patterns: Adapter, Decorator, Proxy, Composite
- Behavioral patterns: Observer, Strategy, Command, Template Method
- Anti-patterns: God Class, Long Method, Circular Dependencies
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.design_patterns import (
    PatternMatch,
    detect_patterns,
)
from ...formatters.toon_encoder import ToonEncoder
from ...sdk import Analyzer
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DesignPatternsTool(BaseMCPTool):
    """
    MCP tool for detecting design patterns and anti-patterns.

    Identifies creational, structural, and behavioral design patterns
    as well as common anti-patterns like God Class and Long Method.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "design_patterns",
            "description": (
                "Detect design patterns and anti-patterns in your codebase. "
                "\n\n"
                "Supported Patterns:\n"
                "- Creational: Singleton, Factory Method, Builder, Prototype\n"
                "- Structural: Adapter, Decorator, Proxy, Composite\n"
                "- Behavioral: Observer, Strategy, Command, Template Method\n"
                "- Anti-patterns: God Class, Long Method, Circular Dependencies\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to identify patterns and anti-patterns\n"
                "- Before refactoring to understand existing architecture\n"
                "- When learning a new codebase to understand design patterns\n"
                "- For architectural documentation and analysis\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For dependency analysis (use dependency_query instead)\n"
                "- For security vulnerability scanning (use security tools)\n"
                "- For dead code detection (use dead_code instead)"
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
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Project root directory. "
                            "If provided without file_path, scans entire project."
                        ),
                    },
                    "pattern_types": {
                        "type": "string",
                        "description": (
                            "Comma-separated list of pattern types to detect. "
                            "Options: singleton, factory_method, observer, strategy, "
                            "god_class, long_method, all. Default: all."
                        ),
                    },
                    "min_confidence": {
                        "type": "number",
                        "description": (
                            "Minimum confidence threshold (0.0 to 1.0). "
                            "Only report patterns with confidence >= this value. "
                            "Default: 0.6."
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
        """Execute the design patterns detection."""
        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root", self.project_root or "")
        pattern_types_str = arguments.get("pattern_types", "all")
        min_confidence = arguments.get("min_confidence", 0.6)
        output_format = arguments.get("format", "toon")

        # Parse pattern types
        if pattern_types_str == "all":
            pattern_filter = None
        else:
            pattern_filter = {p.strip().lower() for p in pattern_types_str.split(",")}

        # Determine analysis scope
        if file_path:
            paths = [Path(file_path)]
        elif project_root:
            paths = list(Path(project_root).rglob("*.*"))
        else:
            return {
                "error": "Either file_path or project_root must be provided",
                "format": output_format,
            }

        # Analyze files
        all_matches: list[PatternMatch] = []
        for path in paths:
            if not path.is_file():
                continue

            # Skip certain file types
            if path.suffix not in {".py", ".java", ".js", ".ts", ".tsx", ".jsx", ".cs", ".go", ".rs"}:
                continue

            try:
                # Parse the file
                analyzer = Analyzer(str(path))
                result = analyzer.get_code_outline(str(path))

                # Extract classes and functions
                classes = []
                for cls in result.get("elements", {}).get("classes", []):
                    classes.append(cls)

                functions = []
                for func in result.get("elements", {}).get("functions", []):
                    functions.append(func)

                # Detect patterns
                matches = detect_patterns(
                    classes, functions, str(path), path.suffix[1:]
                )

                # Filter by confidence and pattern type
                for match in matches:
                    if match.confidence >= min_confidence:
                        if pattern_filter is None or match.pattern_type.value in pattern_filter:
                            all_matches.append(match)

            except Exception as e:
                logger.warning(f"Failed to analyze {path}: {e}")

        # Generate output
        if output_format == "json":
            return self._format_json(all_matches, min_confidence)
        else:
            return self._format_toon(all_matches, min_confidence)

    def _format_json(
        self, matches: list[PatternMatch], min_confidence: float
    ) -> dict[str, Any]:
        """Format results as JSON."""
        return {
            "patterns": [m.to_dict() for m in matches],
            "summary": {
                "total_patterns": len(matches),
                "min_confidence": min_confidence,
                "by_type": self._count_by_type(matches),
            },
        }

    def _format_toon(
        self, matches: list[PatternMatch], min_confidence: float
    ) -> dict[str, Any]:
        """Format results as TOON."""
        if not matches:
            return {
                "tool": "design_patterns",
                "summary": f"No patterns detected with confidence >= {min_confidence}",
                "patterns": [],
            }

        # Group by pattern type
        by_type: dict[str, list[PatternMatch]] = {}
        for match in matches:
            pattern_type = match.pattern_type.value
            if pattern_type not in by_type:
                by_type[pattern_type] = []
            by_type[pattern_type].append(match)

        # Build TOON output
        encoder = ToonEncoder()
        lines = []

        lines.append(f"🔍 Design Patterns (confidence >= {min_confidence})")
        lines.append("")

        for pattern_type, type_matches in sorted(by_type.items()):
            lines.append(f"### {pattern_type.replace('_', ' ').title()}")
            lines.append("")
            for match in type_matches[:5]:  # Limit to 5 per type
                lines.append(f"- **{match.name}** ({match.file}:{match.line})")
                lines.append(f"  Confidence: {match.confidence:.0%}")
                if match.elements:
                    for key, value in match.elements.items():
                        if isinstance(value, list) and value:
                            lines.append(f"  {key}: {', '.join(str(v) for v in value[:3])}")
                        elif value:
                            lines.append(f"  {key}: {value}")
                lines.append("")

        summary = f"Total: {len(matches)} patterns detected"
        lines.append(f"**{summary}**")

        return {
            "tool": "design_patterns",
            "summary": summary,
            "patterns": [m.to_dict() for m in matches],
            "toon": encoder.encode("".join(lines)),
        }

    def validate_arguments(
        self, arguments: dict[str, Any]
    ) -> bool:
        """Validate tool arguments.

        Returns:
            True if valid, raises ValueError if invalid.
        """
        # Check min_confidence range
        min_confidence = arguments.get("min_confidence", 0.6)
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0.0 and 1.0")

        # Check format
        format_val = arguments.get("format", "toon")
        if format_val not in ["toon", "json"]:
            raise ValueError("format must be 'toon' or 'json'")

        # Check that either file_path or project_root is provided
        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root", "")
        if not file_path and not project_root:
            raise ValueError("Either file_path or project_root must be provided")

        return True

    def _count_by_type(self, matches: list[PatternMatch]) -> dict[str, int]:
        """Count matches by pattern type."""
        counts: dict[str, int] = {}
        for match in matches:
            pattern_type = match.pattern_type.value
            counts[pattern_type] = counts.get(pattern_type, 0) + 1
        return counts
