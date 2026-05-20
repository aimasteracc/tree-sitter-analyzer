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
    ".swift": "swift",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    # Supported source file extensions and language mapping
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
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "get_project_overview",
            "description": (
                "Project portrait in one call: languages, file counts, largest files, "
                "tool routing guide. Use FIRST on any project. Replaces multiple Glob calls."
            ),
            "inputSchema": TOOL_SCHEMA,
        }

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the JSON schema for tool input validation."""
        return TOOL_SCHEMA

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate max_depth argument."""
        max_depth = arguments.get("max_depth", 5)
        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 20:
            raise ValueError("max_depth must be an integer between 1 and 20")
        return True

    # Main entry point - dispatches to mode-specific handler
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute project scan and build result with optional health data."""
        self.validate_arguments(arguments)
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        include_health = arguments.get("include_health", False)
        max_depth = arguments.get("max_depth", 5)
        output_format = arguments.get("output_format", "toon")

        root = Path(self.project_root).resolve()
        if not root.is_dir():
            raise ValueError(f"Project root is not a directory: {root}")

        scan = _scan_project(root, max_depth)
        result = _build_result(root, scan, include_health)

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


def _scan_project(root: Path, max_depth: int) -> dict[str, Any]:
    """Walk the project tree and collect file/directory stats."""
    scan = _new_scan()
    for path in root.rglob("*"):
        _add_path_to_scan(scan, root, path, max_depth)
    scan["source_files"].sort(key=lambda item: item["lines"], reverse=True)
    return scan


def _new_scan() -> dict[str, Any]:
    """Return mutable scan accumulators."""
    return {
        "lang_dist": {},
        "ext_dist": {},
        "source_files": [],
        "dir_tree": {},
    }


def _add_path_to_scan(
    scan: dict[str, Any], root: Path, path: Path, max_depth: int
) -> None:
    """Add a path to project scan accumulators when it is in scope."""
    if any(part in _EXCLUDE_DIRS for part in path.parts):
        return
    try:
        rel_path = path.relative_to(root)
    except ValueError:
        return
    if len(rel_path.parts) > max_depth:
        return
    if path.is_dir():
        _increment(scan["dir_tree"], path.name)
        return
    if path.is_file():
        _add_file_to_scan(scan, root, path)


def _add_file_to_scan(scan: dict[str, Any], root: Path, path: Path) -> None:
    """Add one source or non-source file to scan accumulators."""
    ext = path.suffix.lower()
    _increment(scan["ext_dist"], ext)
    lang = _SUPPORTED_EXTS.get(ext)
    if not lang:
        return
    try:
        size = path.stat().st_size
        lines = _count_lines(path)
        scan["source_files"].append(
            {
                "path": str(path.relative_to(root)),
                "language": lang,
                "lines": lines,
                "size_bytes": size,
            }
        )
        _increment(scan["lang_dist"], lang)
    except (OSError, UnicodeDecodeError):
        return


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _build_result(
    root: Path, scan: dict[str, Any], include_health: bool
) -> dict[str, Any]:
    """Build the result dict from scan data."""
    result = _build_base_result(root, scan)
    if include_health:
        _add_health_data(result, scan["source_files"], root)
        result["smart_workflow_hint"] = _build_smart_hint(result)
    else:
        result["smart_workflow_hint"] = _health_opt_in_hint()
    result["agent_summary"] = _build_agent_summary(result, include_health)
    result["tool_routing"] = _build_tool_routing()
    return result


def _build_base_result(root: Path, scan: dict[str, Any]) -> dict[str, Any]:
    """Build the health-independent overview response."""
    lang_dist = scan["lang_dist"]
    source_files = scan["source_files"]
    ext_dist = scan["ext_dist"]
    total_files = sum(ext_dist.values())
    source_count = sum(lang_dist.values())
    return {
        "success": True,
        "project_root": str(root),
        "summary": {
            "total_files": total_files,
            "source_files": source_count,
            "non_source_files": total_files - source_count,
            "total_lines": sum(item["lines"] for item in source_files),
            "languages_count": len(lang_dist),
        },
        "language_distribution": dict(
            sorted(lang_dist.items(), key=lambda item: -item[1])
        ),
        "largest_source_files": source_files[:15],
        "top_directories": dict(
            sorted(scan["dir_tree"].items(), key=lambda item: -item[1])[:20]
        ),
    }


def _health_opt_in_hint() -> str:
    return (
        "Call get_project_overview(include_health=true) for health grades, "
        "or check_code_scale on any file for a quick assessment."
    )


def _add_health_data(
    result: dict[str, Any], source_files: list[dict[str, Any]], root: Path
) -> None:
    """Add health grades for top source files."""
    from ...health_scorer import HealthScorer

    scorer = HealthScorer()
    health_results = [
        entry
        for sf in source_files[:10]
        if (entry := _score_health_entry(scorer, root, sf)) is not None
    ]
    result["health_summary"] = health_results
    unhealthy = [entry for entry in health_results if entry["grade"] in ("D", "F")]
    if unhealthy:
        result["health_alert"] = _build_health_alert(unhealthy)


def _score_health_entry(
    scorer: Any, root: Path, source_file: dict[str, Any]
) -> dict[str, Any] | None:
    """Score one source file for project overview health output."""
    try:
        health = scorer.score_file(str(root / source_file["path"]))
    except Exception:  # nosec B112
        return None
    entry: dict[str, Any] = {
        "file": source_file["path"],
        "grade": health.grade,
        "score": health.total,
    }
    if health.grade in ("D", "F"):
        suggestion = _suggest_refactor_action(
            source_file["path"], source_file.get("lines", 0), health
        )
        if suggestion:
            entry["suggestion"] = suggestion
    return entry


def _build_health_alert(unhealthy: list[dict[str, Any]]) -> str:
    files = ", ".join(entry["file"] for entry in unhealthy[:5])
    return f"{len(unhealthy)} file(s) scored D or F — prioritize refactoring: {files}"


def _build_agent_summary(
    result: dict[str, Any], include_health: bool
) -> dict[str, Any]:
    """Build a compact project-overview summary for first-hop agent decisions."""
    summary = result["summary"]
    largest = result.get("largest_source_files", [])
    top_language = _top_language(result.get("language_distribution", {}))
    return {
        "risk": _overview_risk(result, include_health),
        "next_step": _overview_next_step(result, include_health),
        "verification_command": "uv run python -m tree_sitter_analyzer --overview --format json",
        "project_health_command": "uv run python -m tree_sitter_analyzer --project-health --format json",
        "stop_condition": "Overview returns tool_routing and a concrete next_step.",
        "source_files": summary["source_files"],
        "languages_count": summary["languages_count"],
        "top_language": top_language,
        "largest_file": largest[0]["path"] if largest else "",
        "health_checked": include_health,
    }


def _overview_risk(result: dict[str, Any], include_health: bool) -> str:
    if result.get("health_alert"):
        return "high"
    if not include_health:
        return "unknown"
    return "low"


def _overview_next_step(result: dict[str, Any], include_health: bool) -> str:
    if result.get("health_alert"):
        return (
            "Run project-health for the full backlog, then safe-to-edit the queue head."
        )
    if not include_health:
        return "Re-run overview with include_health=true or run project-health."
    return "Use tool_routing to choose the next focused MCP tool."


def _top_language(language_distribution: dict[str, int]) -> str:
    if not language_distribution:
        return ""
    return max(language_distribution, key=lambda lang: language_distribution[lang])


def _build_tool_routing() -> dict[str, str]:
    """Return the static MCP tool routing guide."""
    return {
        "project_health": "check_project_health()  # grade ALL files, top fix targets",
        "file_health": "check_file_health(file_path=...)  # A-F grade + smells + security",
        "edit_risk": "safe_to_edit(file_path=...)  # MUST call before editing",
        "refactor_plan": "refactoring_suggestions(file_path=...)  # extraction plans",
        "change_impact": "analyze_change_impact()  # git diff + deps → tests to run",
        "file_scale": "check_code_scale(file_path=...)",
        "structure_table": "analyze_code_structure(file_path=..., format_type=compact)",
        "read_lines": "extract_code_section(file_path=..., start_line=..., end_line=...)",
        "find_symbol": "query_code(symbol='...')  # wildcards: *Service, fuzzy: ~analyz",
        "search_text": "search_content(query='...', total_only=true)  # ~10 tok",
        "find_files": "list_files(roots=['.'], extensions=['py'])",
    }


def _count_lines(path: Path) -> int:
    """Count lines in a file using UTF-8 encoding."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return sum(1 for _ in handle)
    except Exception:
        return 0


def _suggest_refactor_action(
    file_path: str, line_count: int, health: Any
) -> str | None:
    """Suggest refactoring action based on file type and size."""
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
    """Build smart workflow hint from health and language data."""
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
