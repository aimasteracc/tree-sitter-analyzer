#!/usr/bin/env python3
"""
Project Overview MCP Tool

One-call entry point for AI agents to understand a project at a glance.
Aggregates language distribution, file counts, and top-level health summary.
"""

from pathlib import Path
from typing import Any

from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_SUPPORTED_EXTS = {
    ".py": "python",
    ".java": "java",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".kt": "kotlin",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
}

_EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "egg-info",
    ".eggs",
    ".idea",
    ".vscode",
    "htmlcov",
    ".cache",
    ".claude",
    ".deepseek",
    ".autonomous-runtime",
}


class ProjectOverviewTool(BaseMCPTool):
    """MCP Tool that gives AI agents a complete project portrait in one call."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "get_project_overview",
            "description": (
                "SMART Workflow 'Map' step (use as FIRST call): Get a complete project portrait — "
                "language distribution, file counts, largest files, and directory structure. "
                "Replaces multiple list_files + search_content calls with a single overview."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_health": {
                    "type": "boolean",
                    "description": "Include health grades for top-10 largest source files (slower)",
                    "default": False,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max directory depth to scan (default: 5)",
                    "default": 5,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        max_depth = arguments.get("max_depth", 5)
        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 20:
            raise ValueError("max_depth must be an integer between 1 and 20")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        include_health = arguments.get("include_health", False)
        max_depth = arguments.get("max_depth", 5)
        output_format = arguments.get("output_format", "toon")

        root = Path(self.project_root).resolve()
        if not root.is_dir():
            raise ValueError(f"Project root is not a directory: {root}")

        lang_dist: dict[str, int] = {}
        ext_dist: dict[str, int] = {}
        all_source_files: list[dict[str, Any]] = []
        dir_tree: dict[str, int] = {}

        for f in root.rglob("*"):
            # Skip excluded dirs
            if any(part in _EXCLUDE_DIRS for part in f.parts):
                continue
            # Depth check
            try:
                depth = len(f.relative_to(root).parts)
            except ValueError:
                continue
            if depth > max_depth:
                continue

            if f.is_file():
                ext = f.suffix.lower()
                ext_dist[ext] = ext_dist.get(ext, 0) + 1

                lang = _SUPPORTED_EXTS.get(ext)
                if lang:
                    lang_dist[lang] = lang_dist.get(lang, 0) + 1
                    try:
                        size = f.stat().st_size
                        lines = _count_lines(f)
                        all_source_files.append(
                            {
                                "path": str(f.relative_to(root)),
                                "language": lang,
                                "lines": lines,
                                "size_bytes": size,
                            }
                        )
                    except (OSError, UnicodeDecodeError):
                        continue

            elif f.is_dir():
                dir_name = f.name
                dir_tree[dir_name] = dir_tree.get(dir_name, 0) + 1

        # Sort source files by line count descending, take top 15
        all_source_files.sort(key=lambda x: x["lines"], reverse=True)
        largest_files = all_source_files[:15]

        total_files = sum(ext_dist.values())
        total_source = sum(lang_dist.values())
        total_lines = sum(f["lines"] for f in all_source_files)

        result: dict[str, Any] = {
            "success": True,
            "project_root": str(root),
            "summary": {
                "total_files": total_files,
                "source_files": total_source,
                "non_source_files": total_files - total_source,
                "total_lines": total_lines,
                "languages_count": len(lang_dist),
            },
            "language_distribution": dict(
                sorted(lang_dist.items(), key=lambda x: -x[1])
            ),
            "largest_source_files": largest_files,
            "top_directories": dict(sorted(dir_tree.items(), key=lambda x: -x[1])[:20]),
            "smart_workflow_hint": (
                "Next: call check_code_scale on any interesting file, "
                "or analyze_code_structure for a detailed table."
            ),
        }

        if include_health and all_source_files:
            from ...health_scorer import HealthScorer

            scorer = HealthScorer()
            health_files = all_source_files[:10]
            health_results = []
            for sf in health_files:
                abs_path = str(root / sf["path"])
                try:
                    h = scorer.score_file(abs_path)
                    health_results.append(
                        {
                            "file": sf["path"],
                            "grade": h.grade,
                            "score": h.total,
                        }
                    )
                except Exception:  # nosec B112
                    continue
            result["health_summary"] = health_results
            unhealthy = [h for h in health_results if h["grade"] in ("D", "F")]
            if unhealthy:
                result["health_alert"] = (
                    f"{len(unhealthy)} file(s) scored D or F — prioritize refactoring: "
                    + ", ".join(h["file"] for h in unhealthy[:5])
                )

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


def _count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in open(path, encoding="utf-8", errors="replace"))
    except Exception:
        return 0
