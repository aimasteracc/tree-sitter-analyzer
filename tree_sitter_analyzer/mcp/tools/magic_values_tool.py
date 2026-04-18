#!/usr/bin/env python3
"""
Magic Value Detector Tool — MCP Tool

Detects hardcoded magic values (numbers, strings, URLs, paths, colors)
across codebases to help identify values that should be constants or config.

Supports: Python, JavaScript/TypeScript, Java, Go
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.magic_values import (
    MagicValueDetector,
    MagicValueResult,
    MagicValueUsage,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
}


class MagicValuesTool(BaseMCPTool):
    """MCP tool for detecting hardcoded magic values."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "magic_values",
            "description": (
                "Detect hardcoded magic values (numbers, strings, URLs, paths, "
                "colors) that should be constants or configuration.\n\n"
                "Categories:\n"
                "- magic_number: Hardcoded numbers (not 0, 1, -1, 2)\n"
                "- magic_string: Hardcoded strings (>=3 chars)\n"
                "- hardcoded_url: HTTP/FTP URLs\n"
                "- hardcoded_path: File system paths\n"
                "- hardcoded_color: CSS color codes (#RGB, #RRGGBB)\n\n"
                "Supported: Python, JS/TS, Java, Go\n\n"
                "WHEN TO USE:\n"
                "- Before code review to flag hardcoded values\n"
                "- During refactoring to identify extractable constants\n"
                "- To audit configuration consistency\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to a specific file to analyze.",
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Project root for directory scan.",
                    },
                    "min_occurrences": {
                        "type": "integer",
                        "description": "Minimum occurrences to report (default: 1).",
                        "default": 1,
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by categories: magic_number, "
                        "magic_string, hardcoded_url, hardcoded_path, "
                        "hardcoded_color",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "description": "Output format (default: toon).",
                        "default": "toon",
                    },
                },
            },
        }

    @handle_mcp_errors()
    def execute(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        file_path = args.get("file_path")
        project_root = args.get("project_root") or self.project_root
        min_occurrences = args.get("min_occurrences", 1)
        categories = set(args.get("categories", []))
        fmt = args.get("format", "toon")

        results: list[MagicValueResult] = []
        usages: list[MagicValueUsage] = []

        if file_path:
            path = Path(file_path)
            lang = _LANG_MAP.get(path.suffix, "python")
            detector = MagicValueDetector(lang)
            results = [detector.detect(path)]
        elif project_root:
            root = Path(project_root)
            extensions = set(_LANG_MAP.keys())
            for f in sorted(root.rglob("*")):
                if f.suffix in extensions and f.is_file():
                    lang = _LANG_MAP[f.suffix]
                    try:
                        det = MagicValueDetector(lang)
                        results.append(det.detect(f))
                    except Exception:
                        pass

        if categories:
            det_py = MagicValueDetector("python")
            results = det_py.filter_by_category(results, categories)

        det_group = MagicValueDetector("python")
        usages = det_group.group_by_value(results)
        if min_occurrences > 1:
            usages = [u for u in usages if u.total_refs >= min_occurrences]

        if fmt == "json":
            return [
                {
                    "total_values": len(usages),
                    "total_references": sum(u.total_refs for u in usages),
                    "values": [u.to_dict() for u in usages],
                    "files": [
                        {
                            "file": r.file_path,
                            "count": r.total_count,
                            "references": [ref.to_dict() for ref in r.references],
                        }
                        for r in results
                        if r.total_count > 0
                    ],
                }
            ]

        encoder = ToonEncoder()
        lines: list[str] = ["Magic Value Detection Report", "=" * 40]
        for u in usages:
            cat = u.category
            lines.append(f"  [{cat}] \"{u.value}\" ({u.total_refs}x in {u.file_count} files)")
            for ref in u.references[:5]:
                lines.append(f"    L{ref.line}: {ref.context[:60]}")
            if u.total_refs > 5:
                lines.append(f"    ... and {u.total_refs - 5} more")
        lines.append(f"\nTotal: {len(usages)} unique values, {sum(u.total_refs for u in usages)} references")
        return [{"content": encoder.encode("\n".join(lines))}]

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments."""
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            return False
        min_occ = arguments.get("min_occurrences", 1)
        if not isinstance(min_occ, int) or min_occ < 1:
            return False
        return True
