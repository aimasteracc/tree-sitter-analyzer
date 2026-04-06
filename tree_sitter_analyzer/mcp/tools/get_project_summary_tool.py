#!/usr/bin/env python3
"""
get_project_summary MCP Tool

Return a persistent architecture overview of the project, loaded from disk.
First call auto-builds the index; subsequent calls return instantly from cache.
"""

from __future__ import annotations

import time
from typing import Any

from ..utils.project_index import ProjectIndex, ProjectIndexManager
from .base_tool import BaseMCPTool


def _format_compact(index: ProjectIndex, age_hours: float, is_fresh: bool) -> str:
    """Render project summary as compact text — ~5x fewer tokens than JSON."""
    lines: list[str] = []

    # Dominant language
    top_lang = (
        max(index.language_distribution, key=lambda k: index.language_distribution[k])
        if index.language_distribution
        else "unknown"
    )
    freshness = "fresh" if is_fresh else f"stale ({age_hours:.1f}h old)"
    lines.append(
        f"{top_lang.capitalize()} project | {index.file_count} files | index: {freshness}"
    )

    # Entry points
    if index.entry_points:
        lines.append(f"Entry:  {', '.join(index.entry_points)}")

    # Key config files
    if index.key_files:
        lines.append(f"Config: {'  '.join(index.key_files)}")

    # Top languages (skip "other", cap at 6)
    lang_items = sorted(
        ((k, v) for k, v in index.language_distribution.items() if k != "other"),
        key=lambda kv: -kv[1],
    )[:6]
    if lang_items:
        lang_str = "  ".join(f"{k}({v})" for k, v in lang_items)
        lines.append(f"Langs:  {lang_str}")

    # Custom notes
    if index.custom_notes:
        lines.append(f"Notes:  {index.custom_notes}")

    lines.append("")  # blank separator

    # Directory tree
    for item in index.top_level_structure:
        name = item["name"]
        count = item.get("file_count", 0)
        lines.append(f"{name + '/':<26}{count:>5}")
        for sub in item.get("subdirectories", []):
            sname = sub["name"]
            scount = sub.get("file_count", 0)
            lines.append(f"  {sname + '/':<24}{scount:>5}")

    return "\n".join(lines)


def _make_quick_start(index: ProjectIndex) -> str:
    """Generate a one-line orientation sentence (≤100 chars)."""
    # Dominant language
    if index.language_distribution:
        top_lang = max(
            index.language_distribution, key=lambda k: index.language_distribution[k]
        )
    else:
        top_lang = "unknown"

    entry = index.entry_points[0] if index.entry_points else "n/a"

    # Try to find a tests directory
    test_dir = "n/a"
    for item in index.top_level_structure:
        name_lower = item["name"].lower()
        if name_lower in ("tests", "test", "spec", "specs", "__tests__"):
            test_dir = item["name"]
            break

    # Config file
    config = "n/a"
    priority_configs = [
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "Makefile",
    ]
    for cfg in priority_configs:
        if cfg in index.key_files:
            config = cfg
            break

    summary = (
        f"{top_lang.capitalize()} project. "
        f"Entry: {entry}. "
        f"Tests: {test_dir}. "
        f"Config: {config}."
    )
    return summary[:100]


class GetProjectSummaryTool(BaseMCPTool):
    """MCP tool that returns a persistent cross-session architecture overview."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "get_project_summary",
            "description": (
                "Get a persistent architecture overview of the entire codebase — "
                "built once, recalled instantly.\n\n"
                "Returns the project index: file count, language distribution, "
                "top-level directory structure, key configuration files, and entry "
                "points. Survives across sessions: once built, the index is stored "
                "in .tree-sitter-cache/project-index.json and reloaded on next "
                "connection.\n\n"
                "WHEN TO USE:\n"
                "- At the START of any session before exploring a codebase — avoids "
                "re-analyzing what is already known\n"
                "- When you need a quick orientation: \"what languages does this "
                "project use?\", \"where are the entry points?\", \"what's the "
                "top-level structure?\"\n"
                "- Before calling list_files — this gives the big picture in one call\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- When you need real-time file search (use list_files instead — the "
                "index may be up to 24 hours old)\n"
                "- When you need code structure details of specific files (use "
                "get_code_outline instead)\n"
                "- When the project has just been heavily restructured (call "
                "build_project_index to refresh)\n"
                "\n"
                "IMPORTANT: If this returns stale data (index older than 24h), or you "
                "know the project structure has changed significantly, call "
                "build_project_index to refresh."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "force_refresh": {
                        "type": "boolean",
                        "description": (
                            "Force rebuild the index even if a fresh one exists. "
                            "Use after major project restructuring."
                        ),
                        "default": False,
                    },
                    "include_notes": {
                        "type": "boolean",
                        "description": (
                            "Include custom architecture notes if any have been added "
                            "via annotate_project."
                        ),
                        "default": True,
                    },
                    "format": {
                        "type": "string",
                        "enum": ["compact", "json"],
                        "description": (
                            "Output format. 'compact' (default) returns a concise text "
                            "summary (~5x fewer tokens). 'json' returns the full "
                            "structured object."
                        ),
                        "default": "compact",
                    },
                },
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Load (or build) the project index and return a summary."""
        force_refresh: bool = bool(arguments.get("force_refresh", False))
        include_notes: bool = bool(arguments.get("include_notes", True))
        output_format: str = str(arguments.get("format", "compact"))

        project_root = self.project_root or "."
        manager = ProjectIndexManager(project_root)

        index: ProjectIndex | None = None
        is_fresh = False

        if not force_refresh:
            index = manager.load()
            if index is not None and not manager.is_stale(index):
                is_fresh = True

        if index is None or force_refresh:
            index = manager.build()
            manager.save(index)
            is_fresh = True

        age_hours = round((time.time() - index.updated_at) / 3600, 2)

        if output_format == "compact":
            text = _format_compact(index, age_hours, is_fresh)
            if include_notes and index.custom_notes:
                pass  # already included in _format_compact
            return {"format": "compact", "summary": text}

        # json format
        quick_start = _make_quick_start(index)
        result: dict[str, Any] = {
            "project_root": index.project_root,
            "index_age_hours": age_hours,
            "is_fresh": is_fresh,
            "file_count": index.file_count,
            "language_distribution": index.language_distribution,
            "top_level_structure": index.top_level_structure,
            "key_files": index.key_files,
            "entry_points": index.entry_points,
            "quick_start": quick_start,
        }
        if include_notes:
            result["custom_notes"] = index.custom_notes
        return result
