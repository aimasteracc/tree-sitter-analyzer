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
        """Load (or build) the project index and return a summary.

        TOON path: reads pre-rendered summary.toon directly — no recomputation.
        If summary.toon is missing, builds the index on demand and saves it.
        JSON path: reads full index object.
        """
        force_refresh: bool = bool(arguments.get("force_refresh", False))
        include_notes: bool = bool(arguments.get("include_notes", True))
        output_format: str = str(arguments.get("format", "toon"))

        project_root = self.project_root or "."
        manager = ProjectIndexManager(project_root)

        if output_format in ("toon", "compact"):
            toon_path = Path(project_root) / manager.TOON_FILE
            if not force_refresh and toon_path.exists():
                # Fast path: return pre-rendered TOON directly
                try:
                    text = toon_path.read_text(encoding="utf-8")
                    if include_notes:
                        # Append notes from index if not already in TOON
                        idx_for_notes = manager.load()
                        if (
                            idx_for_notes
                            and idx_for_notes.custom_notes
                            and idx_for_notes.custom_notes not in text
                        ):
                            text += f"\nnotes:    {idx_for_notes.custom_notes}"
                    return {"format": "toon", "summary": text}
                except OSError:
                    pass  # fall through to rebuild

            # Build index (incremental if possible) and render TOON
            index: ProjectIndex = manager.build(force_refresh=force_refresh)
            if include_notes and index.custom_notes:
                toon_path = Path(project_root) / manager.TOON_FILE
                if toon_path.exists():
                    text = toon_path.read_text(encoding="utf-8")
                else:
                    text = manager.render_toon(index)
            else:
                toon_path = Path(project_root) / manager.TOON_FILE
                text = (
                    toon_path.read_text(encoding="utf-8")
                    if toon_path.exists()
                    else manager.render_toon(index)
                )
            return {"format": "toon", "summary": text}

        # JSON format: load full index
        index_or_none: ProjectIndex | None = None
        if not force_refresh:
            index_or_none = manager.load()

        if index_or_none is None or force_refresh:
            index_or_none = manager.build(force_refresh=force_refresh)

        idx = index_or_none
        age_hours = round((time.time() - idx.updated_at) / 3600, 2)
        is_fresh = age_hours < 1.0
        quick_start = _make_quick_start(idx)
        result: dict[str, Any] = {
            "project_root": idx.project_root,
            "index_age_hours": age_hours,
            "is_fresh": is_fresh,
            "file_count": idx.file_count,
            "language_distribution": idx.language_distribution,
            "top_level_structure": idx.top_level_structure,
            "key_files": idx.key_files,
            "entry_points": idx.entry_points,
            "critical_nodes": idx.critical_nodes,
            "quick_start": quick_start,
            "readme_excerpt": idx.readme_excerpt,
            "module_descriptions": idx.module_descriptions,
        }
        if include_notes:
            result["custom_notes"] = idx.custom_notes
        return result
