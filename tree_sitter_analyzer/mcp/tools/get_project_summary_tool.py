#!/usr/bin/env python3
"""
get_project_summary MCP Tool

Return a persistent architecture overview of the project, loaded from disk.
First call auto-builds the index; subsequent calls return instantly from cache.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..utils.project_index import ProjectIndex, ProjectIndexManager
from .base_tool import BaseMCPTool

# Languages that are not "real" programming languages for display purposes
_NON_CODE_LANGUAGES: frozenset[str] = frozenset(
    {"other", "markdown", "json", "yaml", "toml", "xml", "rst", "latex"}
)


def _format_toon(index: ProjectIndex, age_hours: float, is_fresh: bool) -> str:
    """Render project summary as TOON-style structured text."""
    lines: list[str] = []

    resolved = Path(index.project_root).resolve()
    project_name = resolved.name or resolved.parent.name

    # --- Header block ---
    lines.append(f"project: {project_name}")

    if index.readme_excerpt:
        lines.append(f"purpose: {index.readme_excerpt}")

    # Top-3 real programming languages — require ≥10 files to filter out
    # fixture-only languages (e.g. 6 Java test samples in a Python project)
    total_files = max(index.file_count, 1)
    code_langs = [
        (k, v)
        for k, v in index.language_distribution.items()
        if k not in _NON_CODE_LANGUAGES and (v >= 10 or v / total_files >= 0.02)
    ]
    code_langs.sort(key=lambda kv: -kv[1])
    top_langs = [k for k, _ in code_langs[:3]]
    if top_langs:
        lines.append(f"language: {'  '.join(top_langs)}")

    # Entry points
    if index.entry_points:
        lines.append(f"entry:    {'  '.join(index.entry_points)}")
    else:
        lines.append("entry:    n/a")

    # Key config files
    if index.key_files:
        lines.append(f"config:   {'  '.join(index.key_files)}")

    lines.append("")  # blank separator before structure

    # --- Structure block ---
    lines.append("structure:")

    has_descriptions = bool(index.module_descriptions)
    # Column width for directory name (including trailing slash)
    DIR_COL = 26

    shown_top = 0
    for item in index.top_level_structure:
        if shown_top >= 10:
            break
        name = item["name"]
        dir_label = name + "/"
        desc = index.module_descriptions.get(name, "") if has_descriptions else ""
        subdirs = item.get("subdirectories", [])
        sub_descs = [
            index.module_descriptions.get(f"{name}/{s['name']}", "")
            for s in subdirs
            if has_descriptions
        ]

        # Skip directories with no description and no described subdirectories
        # (they add visual noise without informational value)
        if not desc and not any(sub_descs):
            continue

        if desc:
            padding = max(1, DIR_COL - len(dir_label))
            lines.append(f"  {dir_label}{' ' * padding}{desc}")
        else:
            lines.append(f"  {dir_label}")

        shown_top += 1

        # Sub-directories (depth-2): only show those with a description
        shown_sub = 0
        for sub in item.get("subdirectories", []):
            if shown_sub >= 5:
                break
            sname = sub["name"]
            rel_key = f"{name}/{sname}"
            sub_desc = index.module_descriptions.get(rel_key, "") if has_descriptions else ""
            if not sub_desc:
                continue  # skip undescribed subdirs — noise without signal
            sub_label = sname + "/"
            padding = max(1, DIR_COL - 2 - len(sub_label))
            lines.append(f"    {sub_label}{' ' * padding}{sub_desc}")
            shown_sub += 1

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
                        "enum": ["toon", "json"],
                        "description": (
                            "Output format. 'toon' (default) returns a concise "
                            "TOON-style structured text summary with semantic "
                            "directory descriptions. 'json' returns the full "
                            "structured object."
                        ),
                        "default": "toon",
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
        output_format: str = str(arguments.get("format", "toon"))

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

        if output_format in ("toon", "compact"):
            text = _format_toon(index, age_hours, is_fresh)
            if include_notes and index.custom_notes:
                text += f"\nnotes: {index.custom_notes}"
            return {"format": "toon", "summary": text}

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
            "readme_excerpt": index.readme_excerpt,
            "module_descriptions": index.module_descriptions,
        }
        if include_notes:
            result["custom_notes"] = index.custom_notes
        return result
