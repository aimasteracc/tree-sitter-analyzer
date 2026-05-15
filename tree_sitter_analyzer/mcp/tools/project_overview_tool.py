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

TOOL_SCHEMA: dict[str, Any] = {
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
            "description": "Output format",
            "default": "toon",
        },
    },
    "additionalProperties": False,
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
            "inputSchema": TOOL_SCHEMA,
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

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

        scan = self._scan_project(root, max_depth)
        result = self._build_result(root, scan, include_health)

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _scan_project(self, root: Path, max_depth: int) -> dict[str, Any]:
        """Walk the project tree and collect file/directory stats."""
        lang_dist: dict[str, int] = {}
        ext_dist: dict[str, int] = {}
        all_source_files: list[dict[str, Any]] = []
        dir_tree: dict[str, int] = {}

        for f in root.rglob("*"):
            if any(part in _EXCLUDE_DIRS for part in f.parts):
                continue
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
                dir_tree[f.name] = dir_tree.get(f.name, 0) + 1

        all_source_files.sort(key=lambda x: x["lines"], reverse=True)
        return {
            "lang_dist": lang_dist,
            "ext_dist": ext_dist,
            "source_files": all_source_files,
            "dir_tree": dir_tree,
        }

    def _build_result(
        self, root: Path, scan: dict[str, Any], include_health: bool
    ) -> dict[str, Any]:
        """Build the result dict from scan data."""
        lang_dist = scan["lang_dist"]
        source_files = scan["source_files"]
        ext_dist = scan["ext_dist"]

        total_files = sum(ext_dist.values())
        total_lines = sum(f["lines"] for f in source_files)

        result: dict[str, Any] = {
            "success": True,
            "project_root": str(root),
            "summary": {
                "total_files": total_files,
                "source_files": sum(lang_dist.values()),
                "non_source_files": total_files - sum(lang_dist.values()),
                "total_lines": total_lines,
                "languages_count": len(lang_dist),
            },
            "language_distribution": dict(
                sorted(lang_dist.items(), key=lambda x: -x[1])
            ),
            "largest_source_files": source_files[:15],
            "top_directories": dict(
                sorted(scan["dir_tree"].items(), key=lambda x: -x[1])[:20]
            ),
        }

        if not include_health:
            result["smart_workflow_hint"] = (
                "Call get_project_overview(include_health=true) for health grades, "
                "or check_code_scale on any file for a quick assessment."
            )
        else:
            self._add_health_data(result, source_files, root)
            result["smart_workflow_hint"] = _build_smart_hint(result)

        result["tool_routing"] = {
            "file_health": "check_file_health(file_path=...)",
            "file_scale": "check_code_scale(file_path=...)",
            "structure_table": "analyze_code_structure(file_path=..., format_type=compact)",
            "read_lines": "extract_code_section(file_path=..., start_line=..., end_line=...)",
            "find_symbol": "query_code(symbol='...')  # cross-file search",
            "search_text": "search_content(query='...', roots=['src/'])",
            "find_files": "list_files(roots=['.'], extensions=['py'])",
            "refactor_targets": "check_file_health(file_path=...)  # returns code_smells + next_action",
        }
        return result

    def _add_health_data(
        self, result: dict[str, Any], source_files: list[dict[str, Any]], root: Path
    ) -> None:
        """Add health grades for top source files."""
        from ...health_scorer import HealthScorer

        scorer = HealthScorer()
        health_results = []
        for sf in source_files[:10]:
            try:
                h = scorer.score_file(str(root / sf["path"]))
                entry: dict[str, Any] = {
                    "file": sf["path"],
                    "grade": h.grade,
                    "score": h.total,
                }
                if h.grade in ("D", "F"):
                    suggestion = _suggest_refactor_action(
                        sf["path"], sf.get("lines", 0), h
                    )
                    if suggestion:
                        entry["suggestion"] = suggestion
                health_results.append(entry)
            except Exception:  # nosec B112
                continue

        result["health_summary"] = health_results
        unhealthy = [h for h in health_results if h["grade"] in ("D", "F")]
        if unhealthy:
            result["health_alert"] = (
                f"{len(unhealthy)} file(s) scored D or F — prioritize refactoring: "
                + ", ".join(h["file"] for h in unhealthy[:5])
            )


def _count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in open(path, encoding="utf-8", errors="replace"))
    except Exception:
        return 0


def _suggest_refactor_action(
    file_path: str, line_count: int, health: Any
) -> str | None:
    ext = Path(file_path).suffix.lower()
    is_test = "test" in file_path.lower()
    is_prod = not is_test and ext == ".py"

    if line_count > 500 and is_prod:
        return f"check_file_health(file_path='{file_path}') for extraction targets, then extract longest methods into a new module"
    if is_test:
        return f"Split test file by test class into separate files (current: {line_count} lines)"
    if ext == ".md":
        return f"Archive old entries to reduce size ({line_count} lines)"
    return None


def _build_smart_hint(result: dict[str, Any]) -> str:
    parts: list[str] = []
    health_summary = result.get("health_summary", [])
    unhealthy = [h for h in health_summary if h.get("grade") in ("D", "F")]
    lang_dist = result.get("language_distribution", {})
    top_lang = max(lang_dist, key=lambda k: lang_dist[k]) if lang_dist else ""

    if unhealthy:
        prod = [h for h in unhealthy if "test" not in h["file"].lower()]
        target = prod[0] if prod else unhealthy[0]
        action = target.get("suggestion", "check_file_health for details")
        parts.append(
            f"REFACTOR: {target['file']} ({target['grade']} {target['score']:.0f}) — {action}"
        )
    else:
        parts.append("Project health is good — all top files are A/B/C grade")

    if top_lang:
        parts.append(
            f"SMART 'Analyze': analyze_code_structure on any .{top_lang} file for detailed table"
        )

    largest = result.get("largest_source_files", [])
    if largest:
        biggest = largest[0]
        parts.append(
            f"SMART 'Retrieve': extract_code_section on {biggest['path']} ({biggest['lines']} lines)"
        )

    return " | ".join(parts[:3])
