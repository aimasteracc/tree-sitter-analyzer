#!/usr/bin/env python3
"""
Project Overview MCP Tool

One-call entry point for AI agents to understand a project at a glance.
Aggregates language distribution, file counts, and top-level health summary.
"""

from pathlib import Path
from typing import Any

import pathspec

from ...utils import setup_logger
from ._graph_cache_fingerprint import _EXCLUDE_DIRS as _PROJECT_EXCLUDE_DIRS
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

# Reverse mapping: language name → canonical file extension (for hints/suggestions)
_LANGUAGE_TO_EXT = {
    "python": "py",
    "java": "java",
    "javascript": "js",
    "typescript": "ts",
    "go": "go",
    "rust": "rs",
    "kotlin": "kt",
    "swift": "swift",
    "csharp": "cs",
    "ruby": "rb",
    "php": "php",
    "c": "c",
    "cpp": "cpp",
    "sql": "sql",
    "html": "html",
    "css": "css",
    "yaml": "yaml",
    "markdown": "md",
    "bash": "sh",
    "scala": "scala",
    "json": "json",
}

_EXCLUDE_DIRS = frozenset(
    _PROJECT_EXCLUDE_DIRS  # canonical: .ast-cache, .tree-sitter-cache, etc.
    | {
        # K10: overview also drops a couple of project-specific paths that
        # are not source but used to be enumerated. Keep them here so the
        # overview never returns ``.deepseek/...`` or ``.autonomous-runtime/...``
        # as part of the file count.
        "egg-info",
        ".deepseek",
    }
)

# Path segments that should be excluded from language-distribution counts.
# These dirs contain valid source files (fixtures, golden masters,
# internal audit docs) but those files are NOT part of the project's
# "actual source mix" — counting them inflates secondary languages
# (markdown=2945 swamping python=1347) and misleads the headline number.
_LANGUAGE_COUNT_EXCLUDED_SEGMENTS: frozenset[str] = frozenset(
    {
        "tests/golden_masters",
        "tests/fixtures",
        "tests/test_data",
        "tests/golden",
        "docs/internal",
        "compatibility_test/results",
        "corpus",
        "examples",
        ".tree-sitter-cache",
        ".ast-cache",
        # Build artefacts + dev-tooling caches that ship .md / .yaml files
        # by the hundred (skill docs, agent prompts) but are NOT project
        # source. ``comprehensive_test_results`` alone holds ~2,500 md
        # files that drown out the real source mix.
        "comprehensive_test_results",
        "openspec",
        ".claude",
        ".agents",
        ".swarm",
        ".kiro",
        ".roo",
        ".autonomous-runtime",
        ".claude-flow",
    }
)


def _is_language_count_excluded(rel_path: str) -> bool:
    """True if ``rel_path`` should not influence language_distribution."""
    normalized = rel_path.replace("\\", "/")
    return any(seg in normalized for seg in _LANGUAGE_COUNT_EXCLUDED_SEGMENTS)


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
                "One-shot project portrait — the agent's first call on any "
                "new repo. Returns language distribution, file/line totals, "
                "largest files, top-level directory structure, key entry "
                "points, and a tool_routing guide that maps common questions "
                "to the right MCP tool. Optionally includes per-language "
                "health rollup when ``include_health=true`` (default).\n\n"
                "WHEN TO USE:\n"
                "- FIRST call when opening an unfamiliar repository\n"
                "- To decide whether the project is small/medium/large "
                "(affects which deeper tools are affordable)\n"
                "- To find the entry points before navigating to a specific "
                "file\n"
                "- For periodic project-health rollups paired with "
                "project_health\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- To read a single file — use partial_read or get_code_outline\n"
                "- For per-file quality grades — use file_health\n"
                "- To list files matching a pattern — use list_files\n"
                "- For dependency graph queries — use dependency_analysis"
            ),
            "inputSchema": TOOL_SCHEMA,
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
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


def _load_gitignore_patterns(root: Path) -> pathspec.PathSpec | None:
    """Load .gitignore patterns from the project root.

    Returns a pathspec.PathSpec object if .gitignore exists, None otherwise.
    Uses gitwildmatch syntax to match git's semantics.
    """
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        return None

    try:
        patterns = []
        with open(gitignore_path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n\r")
                # Skip empty lines and comments
                if line and not line.startswith("#"):
                    patterns.append(line)

        if not patterns:
            return None

        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    except Exception as e:
        logger.warning(f"Failed to load .gitignore from {gitignore_path}: {e}")
        return None


def _is_ignored_by_gitignore(
    rel_path: str, gitignore_spec: pathspec.PathSpec | None
) -> bool:
    """Check if a relative path matches any gitignore patterns.

    Args:
        rel_path: Relative path from project root (use forward slashes)
        gitignore_spec: Compiled pathspec from .gitignore (None if no .gitignore)

    Returns:
        True if the path should be ignored, False otherwise
    """
    if gitignore_spec is None:
        return False

    # Normalize to forward slashes for gitignore matching
    normalized = rel_path.replace("\\", "/")
    return gitignore_spec.match_file(normalized)


def _scan_project(root: Path, max_depth: int) -> dict[str, Any]:
    """Walk the project tree and collect file/directory stats.

    Uses ``os.walk`` (not ``rglob``) so ignored directories are pruned from
    the recursion frontier BEFORE descending — a gitignored vendored tree
    like .benchmark-repos/ must not even be visited (Codex P2 on #493).
    """
    import os

    scan = _new_scan()
    gitignore_spec = _load_gitignore_patterns(root)

    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        keep_dirs = []
        for d in dirnames:
            rel = d if rel_dir == "." else f"{rel_dir}/{d}"
            # match both "dir" and "dir/" forms (pathspec dir patterns)
            if _is_ignored_by_gitignore(rel, gitignore_spec) or (
                _is_ignored_by_gitignore(rel + "/", gitignore_spec)
            ):
                continue
            keep_dirs.append(d)
        dirnames[:] = sorted(keep_dirs)
        for d in dirnames:
            _add_path_to_scan(scan, root, Path(dirpath) / d, max_depth, gitignore_spec)
        for f in sorted(filenames):
            _add_path_to_scan(scan, root, Path(dirpath) / f, max_depth, gitignore_spec)
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
    scan: dict[str, Any],
    root: Path,
    path: Path,
    max_depth: int,
    gitignore_spec: pathspec.PathSpec | None = None,
) -> None:
    """Add a path to project scan accumulators when it is in scope.

    Args:
        scan: Mutable scan accumulator dict
        root: Project root path
        path: Path to check and potentially add
        max_depth: Max directory depth to scan
        gitignore_spec: Compiled .gitignore patterns (if any)
    """
    if any(part in _EXCLUDE_DIRS for part in path.parts):
        return
    try:
        rel_path = path.relative_to(root)
    except ValueError:
        return

    # Check if path is ignored by .gitignore
    if _is_ignored_by_gitignore(str(rel_path), gitignore_spec):
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
        # Forward slashes on every platform — agents must not get
        # OS-dependent separators in response payloads.
        rel_path = str(path.relative_to(root)).replace("\\", "/")
        size = path.stat().st_size
        lines = _count_lines(path)
        scan["source_files"].append(
            {
                "path": rel_path,
                "language": lang,
                "lines": lines,
                "size_bytes": size,
            }
        )
        # Skip language tally for fixture / golden-master / internal-docs
        # files. They're real code but not part of the project's "source mix".
        # Their existence is still recorded in ``source_files`` and ``ext_dist``.
        if not _is_language_count_excluded(rel_path):
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
    # Finding 6: mirror agent_summary.summary_line to the top-level envelope.
    from .base_tool import mirror_summary_line

    return mirror_summary_line(result)


def _build_base_result(root: Path, scan: dict[str, Any]) -> dict[str, Any]:
    """Build the health-independent overview response."""
    lang_dist = scan["lang_dist"]
    source_files = scan["source_files"]
    ext_dist = scan["ext_dist"]
    total_files = sum(ext_dist.values())
    source_count = sum(lang_dist.values())
    # O5 (round-30): mirror the language map into ``summary.by_language``
    # so consumers building a summary block don't need to read two
    # different sub-trees of the response. ``language_distribution``
    # stays at the top level for back-compat with all existing
    # consumers — the new field is purely additive.
    sorted_lang_dist = dict(sorted(lang_dist.items(), key=lambda item: -item[1]))
    return {
        "success": True,
        "project_root": str(root),
        "summary": {
            "total_files": total_files,
            "source_files": source_count,
            "non_source_files": total_files - source_count,
            "total_lines": sum(item["lines"] for item in source_files),
            # ``languages_count`` is derived from the same map so it can
            # never drift out of sync with ``summary.by_language``.
            "languages_count": len(sorted_lang_dist),
            "by_language": sorted_lang_dist,
        },
        "language_distribution": sorted_lang_dist,
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
    # Finding 6: include summary_line so the dispatch post-hook can mirror
    # it to the top-level envelope (was None across the project_overview
    # JSON response in round-16b dogfood).
    summary_line = (
        f"project_overview source_files={summary['source_files']} "
        f"languages={summary['languages_count']} "
        f"top_language={top_language or 'unknown'}"
    )
    risk = _overview_risk(result, include_health)
    return {
        "summary_line": summary_line,
        # N4 (round-27): emit ``verdict`` so the cross-tool envelope
        # contract (``TestEnvelopeContractSnapshot``) is satisfied.
        # ``risk`` is the project-overview headline; ``verdict`` mirrors
        # it to the safety-tool vocabulary so agents that branch on
        # ``verdict`` see a consistent shape across tools.
        "verdict": _overview_risk_to_verdict(risk),
        "risk": risk,
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


def _overview_risk_to_verdict(risk: str) -> str:
    """Map project-overview risk to the cross-tool verdict vocabulary.

    N4 (round-27) + Item 3 (#446): verdict should reflect whether the code
    NEEDS review, not whether the tool has checked health yet.

    - ``high`` → ``REVIEW`` (oversized files / health alerts — code needs review)
    - ``medium`` → ``CAUTION`` (some signals worth a glance)
    - ``low`` → ``SAFE`` (clean project, no red flags)
    - ``unknown`` (when include_health=false and no observable signals) → ``INFO``
      (plain informational overview, not a review prompt)
    """
    risk_lower = (risk or "").lower()
    if risk_lower == "high":
        return "REVIEW"
    if risk_lower == "medium":
        return "CAUTION"
    if risk_lower == "unknown":
        # Item 3: plain informational overview (no health check) → INFO, not REVIEW
        return "INFO"
    return "SAFE"


def _overview_risk(result: dict[str, Any], include_health: bool) -> str:
    """Infer project risk from observable signals (F11 fix).

    Before F11 we returned ``"unknown"`` when ``include_health`` was
    false, which gave AI agents no signal. We now derive a coarse
    risk grade from data that is *always* present in the scan:
    largest-file line counts, the count of oversized files in the
    top-15 largest list, and language spread. When ``include_health``
    is true we additionally honour D/F grades and health_alert.

    Returns one of ``"low"``, ``"medium"``, ``"high"``. Never returns
    ``"unknown"`` (which used to flow through to ``agent_summary``).
    """
    # Strongest signal first: explicit D/F health alert.
    if result.get("health_alert"):
        return "high"
    if include_health:
        health_summary = result.get("health_summary", [])
        if isinstance(health_summary, list):
            failing = sum(
                1
                for entry in health_summary
                if isinstance(entry, dict) and entry.get("grade") in {"D", "F"}
            )
            if failing >= 2:
                return "high"
            if failing == 1:
                return "medium"

    # Signal: oversized source files in the top-15 largest list.
    # Thresholds match the project's documented health rules
    # (~500 lines is the soft refactor cue, ~800 is the hard cap).
    largest = result.get("largest_source_files", []) or []
    if isinstance(largest, list) and largest:
        big_files = [
            item
            for item in largest
            if isinstance(item, dict)
            and isinstance(item.get("lines"), int)
            and item["lines"] >= 800
            and ".md" not in str(item.get("path", "")).lower()
        ]
        moderate_files = [
            item
            for item in largest
            if isinstance(item, dict)
            and isinstance(item.get("lines"), int)
            and item["lines"] >= 500
            and ".md" not in str(item.get("path", "")).lower()
        ]
        if len(big_files) >= 3:
            return "high"
        if big_files or len(moderate_files) >= 5:
            return "medium"

    # Signal: language sprawl (many languages → more integration risk).
    summary = result.get("summary", {})
    if isinstance(summary, dict):
        languages_count = summary.get("languages_count", 0)
        source_files = summary.get("source_files", 0)
        if isinstance(languages_count, int) and languages_count >= 8:
            return "medium"
        # Very large monorepos (>2k source files) without health data
        # warrant a hint to opt in to deeper inspection.
        if (
            not include_health
            and isinstance(source_files, int)
            and source_files >= 2000
        ):
            return "medium"

    # Default — clean project (or insufficient signal but no red flags).
    return "low"


def _overview_next_step(result: dict[str, Any], include_health: bool) -> str:
    if result.get("health_alert"):
        return (
            "Run project-health for the full backlog, then safe-to-edit the queue head."
        )
    if not include_health:
        return "Re-run overview with include_health=true or run project-health."
    return (
        "Pick the next query from the tool_routing map in this response "
        "(e.g. health for grades, structure for outlines)."
    )


def _top_language(language_distribution: dict[str, int]) -> str:
    if not language_distribution:
        return ""
    return max(language_distribution, key=lambda lang: language_distribution[lang])


def _build_tool_routing() -> dict[str, str]:
    """Return the static MCP tool routing guide.

    H11: every value here must reference a tool name that is actually
    registered in ``_create_tool_registry`` (see
    ``tree_sitter_analyzer/mcp/server.py``). The previous version mixed
    CLI shorthand into the MCP syntax, which made calls fail with
    "unknown tool" when an agent copy-pasted the snippet through the
    MCP JSON-RPC transport. The single source of truth for the names
    below is the registry tuple in ``server._create_tool_registry``.
    All snippets use MCP keyword-argument form (``tool(key=value)``);
    none of them use CLI positional form.
    """
    return {
        # Health + safety
        "project_health": (
            "check_project_health()  # grade ALL files, top fix targets"
        ),
        "file_health": (
            "check_file_health(file_path='...')  # A-F grade + smells + security"
        ),
        "edit_risk": ("safe_to_edit(file_path='...')  # MUST call before editing"),
        "refactor_plan": (
            "refactoring_suggestions(file_path='...')  # extraction plans"
        ),
        "change_impact": ("analyze_change_impact()  # git diff + deps -> tests to run"),
        # Scale + structure
        "file_scale": "check_code_scale(file_path='...')",
        "structure_table": (
            "analyze_code_structure(file_path='...', format_type='compact')"
        ),
        "read_lines": (
            "extract_code_section(file_path='...', start_line=1, end_line=100)"
        ),
        # Symbol + text search (MCP-canonical names from server registry)
        "find_symbol": (
            "query_code(symbol='...')  # wildcards: *Service, fuzzy: ~analyz"
        ),
        "search_text": ("search_content(query='...', total_only=true)  # ~10 tok"),
        "find_files": "list_files(roots=['.'], extensions=['py'])",
        "find_and_grep": "find_and_grep(query='...', roots=['.'])",
        # Deep analysis
        "deps": "analyze_dependencies(mode='summary')",
        "call_graph": "codegraph_call_graph(mode='summary')",
        "symbol_lineage": "symbol_lineage(symbol='...')",
        "smart_context": "smart_context(file_path='...')",
        # Code-quality + routing
        "code_patterns": "code_patterns(file_path='...')",
        "detect_routes": "detect_routes(mode='summary')",
        # Index + workflow
        "ast_cache": "ast_cache(mode='stats')",
        "agent_workflow": "get_agent_workflow(file_path='...')",
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
        ext = _LANGUAGE_TO_EXT.get(top_lang, top_lang)
        parts.append(
            f"SMART 'Analyze': analyze_code_structure on any .{ext} file for detailed table"
        )

    largest = result.get("largest_source_files", [])
    if largest:
        biggest = largest[0]
        parts.append(
            f"SMART 'Retrieve': extract_code_section on {biggest['path']} ({biggest['lines']} lines)"
        )

    return " | ".join(parts[:3])
