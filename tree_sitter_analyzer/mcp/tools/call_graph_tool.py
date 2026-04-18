"""Call Graph Tool — MCP Tool for function-level call graph analysis.

Builds function call graphs, detects island functions (never called),
and god functions (call too many others).

Supports: Python, JavaScript/TypeScript, Java, Go
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.call_graph import (
    CallGraphAnalyzer,
    CallGraphResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
}


class CallGraphTool(BaseMCPTool):
    """MCP tool for function call graph analysis."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "call_graph",
            "description": (
                "Analyze function call graphs: who calls whom, "
                "island functions (never called), god functions (too many calls).\n\n"
                "Features:\n"
                "- Function definition extraction\n"
                "- Call edge mapping (caller -> callee)\n"
                "- Island detection (defined but never called)\n"
                "- God function detection (calls >= N functions)\n\n"
                "Supported: Python, JS/TS, Java, Go\n\n"
                "WHEN TO USE:\n"
                "- To understand code structure and call relationships\n"
                "- To find dead code (island functions)\n"
                "- To identify overly complex functions (god functions)\n"
                "- Before refactoring to understand impact\n"
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
                    "god_threshold": {
                        "type": "integer",
                        "description": "Minimum calls to be a god function (default: 20).",
                        "default": 20,
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
        god_threshold = args.get("god_threshold", 20)
        fmt = args.get("format", "toon")

        results: list[CallGraphResult] = []

        if file_path:
            path = Path(file_path)
            lang = _LANG_MAP.get(path.suffix, "python")
            analyzer = CallGraphAnalyzer(lang)
            results = [analyzer.analyze_file(str(path), god_threshold)]
        elif project_root:
            root = Path(project_root)
            for ext in sorted(_LANG_MAP.keys()):
                for f in sorted(root.rglob(f"*{ext}")):
                    if not f.is_file():
                        continue
                    lang = _LANG_MAP[f.suffix]
                    try:
                        analyzer = CallGraphAnalyzer(lang)
                        result = analyzer.analyze_file(str(f), god_threshold)
                        if result.function_count > 0:
                            results.append(result)
                    except Exception:
                        pass

        if fmt == "json":
            return [
                {
                    "total_functions": sum(r.function_count for r in results),
                    "total_edges": sum(r.edge_count for r in results),
                    "total_islands": sum(len(r.island_functions) for r in results),
                    "total_god": sum(len(r.god_functions) for r in results),
                    "files": [r.to_dict() for r in results],
                }
            ]

        encoder = ToonEncoder()
        lines: list[str] = ["Call Graph Analysis Report", "=" * 40]

        total_funcs = sum(r.function_count for r in results)
        total_edges = sum(r.edge_count for r in results)
        all_islands: list[str] = []
        all_gods: list[tuple[str, int]] = []

        for r in results:
            lines.append(f"\nFile: {r.file_path}")
            lines.append(f"  Functions: {r.function_count}, Edges: {r.edge_count}")

            for func in r.functions:
                lines.append(f"  - {func.name} (L{func.start_line}-{func.end_line})")

            if r.call_edges:
                lines.append("  Call edges:")
                for edge in r.call_edges[:20]:
                    lines.append(f"    {edge.caller} -> {edge.callee} (L{edge.line})")
                if r.edge_count > 20:
                    lines.append(f"    ... and {r.edge_count - 20} more")

            all_islands.extend(r.island_functions)
            all_gods.extend(r.god_functions)

        if all_islands:
            lines.append(f"\nIsland functions ({len(all_islands)}):")
            for name in all_islands[:30]:
                lines.append(f"  - {name}")
            if len(all_islands) > 30:
                lines.append(f"  ... and {len(all_islands) - 30} more")

        if all_gods:
            lines.append(f"\nGod functions ({len(all_gods)}):")
            for name, count in all_gods[:10]:
                lines.append(f"  - {name} ({count} callees)")
        else:
            lines.append("\nNo god functions detected.")

        lines.append(
            f"\nSummary: {total_funcs} functions, "
            f"{total_edges} edges, "
            f"{len(all_islands)} islands, "
            f"{len(all_gods)} god functions"
        )

        return [{"content": encoder.encode("\n".join(lines))}]

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            return False
        threshold = arguments.get("god_threshold", 20)
        if not isinstance(threshold, int) or threshold < 1:
            return False
        return True
