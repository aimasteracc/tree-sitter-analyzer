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
from .base_tool import BaseMCPTool, format_summary_line

# Languages that are not "real" programming languages for display purposes
_NON_CODE_LANGUAGES: frozenset[str] = frozenset(
    {"other", "markdown", "json", "yaml", "toml", "xml", "rst", "latex"}
)


# Column width for directory name (including trailing slash) in TOON rendering.
_DIR_COL: int = 26


def _top_code_languages(index: ProjectIndex) -> list[str]:
    """Return up to top-3 real programming languages by file count.

    Filters out non-code languages (markdown, json, yaml, …) and noise
    languages contributing fewer than 10 files **and** less than 2% of
    the total file mix — keeps fixture-only languages (e.g. 6 Java test
    samples in a Python project) out of the headline.
    """
    total_files = max(index.file_count, 1)
    code_langs = [
        (k, v)
        for k, v in index.language_distribution.items()
        if k not in _NON_CODE_LANGUAGES and (v >= 10 or v / total_files >= 0.02)
    ]
    code_langs.sort(key=lambda kv: -kv[1])
    return [k for k, _ in code_langs[:3]]


def _emit_header_block(index: ProjectIndex, lines: list[str]) -> None:
    """Append the ``project`` / ``purpose`` / ``language`` / ``entry`` / ``config`` block."""
    resolved = Path(index.project_root).resolve()
    project_name = resolved.name or resolved.parent.name
    lines.append(f"project: {project_name}")

    if index.readme_excerpt:
        lines.append(f"purpose: {index.readme_excerpt}")

    top_langs = _top_code_languages(index)
    if top_langs:
        lines.append(f"language: {'  '.join(top_langs)}")

    if index.entry_points:
        lines.append(f"entry:    {'  '.join(index.entry_points)}")
    else:
        lines.append("entry:    n/a")

    if index.key_files:
        lines.append(f"config:   {'  '.join(index.key_files)}")


def _append_subdir_lines(
    name: str, subdirs: list[dict[str, Any]], descs: dict[str, str], lines: list[str]
) -> None:
    """Append described depth-2 subdirectories of ``name`` (up to 5)."""
    shown_sub = 0
    for sub in subdirs:
        if shown_sub >= 5:
            break
        sname = sub["name"]
        sub_desc = descs.get(f"{name}/{sname}", "")
        if not sub_desc:
            continue  # skip undescribed subdirs — noise without signal
        sub_label = sname + "/"
        padding = max(1, _DIR_COL - 2 - len(sub_label))
        lines.append(f"    {sub_label}{' ' * padding}{sub_desc}")
        shown_sub += 1


def _emit_structure_block(index: ProjectIndex, lines: list[str]) -> None:
    """Append the ``structure:`` block — up to 10 top-level dirs with descriptions."""
    lines.append("structure:")
    descs = index.module_descriptions if index.module_descriptions else {}

    shown_top = 0
    for item in index.top_level_structure:
        if shown_top >= 10:
            break
        name = item["name"]
        dir_label = name + "/"
        desc = descs.get(name, "")
        subdirs = item.get("subdirectories", [])
        sub_descs = [descs.get(f"{name}/{s['name']}", "") for s in subdirs]

        # Skip dirs with no description and no described subdirectories
        # (they add visual noise without informational value).
        if not desc and not any(sub_descs):
            continue

        if desc:
            padding = max(1, _DIR_COL - len(dir_label))
            lines.append(f"  {dir_label}{' ' * padding}{desc}")
        else:
            lines.append(f"  {dir_label}")
        shown_top += 1

        _append_subdir_lines(name, subdirs, descs, lines)


def _format_toon(index: ProjectIndex, age_hours: float, is_fresh: bool) -> str:
    """Render project summary as TOON-style structured text.

    r37eo (dogfood): 90 → ~10 lines of orchestration. Header / structure /
    sub-dir helpers (``_emit_header_block`` / ``_emit_structure_block`` /
    ``_append_subdir_lines``) own each block; ``_top_code_languages`` does
    the noise filtering once.
    """
    lines: list[str] = []
    _emit_header_block(index, lines)
    lines.append("")  # blank separator before structure
    _emit_structure_block(index, lines)
    return "\n".join(lines)


def _toon_envelope(
    resolved_fmt: str,
    text: str,
    summary_line: str,
    next_step: str,
) -> dict[str, Any]:
    """Construct the canonical TOON-path envelope.

    r37ba: extracted from ``execute``'s two TOON return statements so the
    20-line dict literal stops appearing twice. F12 / H10 / r37x contracts
    preserved.
    """
    return {
        "success": True,
        "format": resolved_fmt,
        "output_format": resolved_fmt,
        "summary": text,
        "summary_line": summary_line,
        "verdict": "INFO",  # r37x: top-level verdict mirror
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": next_step,
            "verdict": "INFO",  # T4 (round-37f): canonical envelope contract
        },
    }


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
                '- When you need a quick orientation: "what languages does this '
                'project use?", "where are the entry points?", "what\'s the '
                'top-level structure?"\n'
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
                    "output_format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "description": (
                            "Output format. 'toon' (default) returns a concise "
                            "TOON-style structured text summary with semantic "
                            "directory descriptions — chosen as the default "
                            "because get_project_summary is the first-hop "
                            "orientation tool and TOON cuts the response by "
                            "roughly 70% on a typical project index. Pass "
                            "'json' explicitly when you need the structured "
                            "object (file_count, language_distribution, "
                            "critical_nodes, top_level_structure, ...) for "
                            "downstream code. Both values echo back in the "
                            "``format`` and ``output_format`` keys (F12)."
                        ),
                        "default": "toon",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "description": (
                            "Deprecated alias for ``output_format`` — kept for "
                            "backward compatibility with pre-1.12.1 callers. "
                            "Prefer ``output_format``."
                        ),
                    },
                },
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Load (or build) the project index and return a summary.

        r37ba (dogfood): tool flagged this at 141 lines / nesting depth 7.
        Split into TOON-path + JSON-path helpers; each is now ~30 lines.
        Behaviour preserved (incl. F12 / H10 / r37x envelope contracts).
        """
        force_refresh: bool = bool(arguments.get("force_refresh", False))
        include_notes: bool = bool(arguments.get("include_notes", True))
        # Prefer ``output_format`` (standardised across all 23 MCP tools in
        # v1.12.0+); fall back to legacy ``format`` for pre-1.12.1 callers.
        output_format: str = str(
            arguments.get("output_format", arguments.get("format", "toon"))
        )

        project_root = self.project_root or "."
        manager = ProjectIndexManager(project_root)

        if output_format in ("toon", "compact"):
            return self._execute_toon(
                manager, project_root, force_refresh, include_notes
            )
        return self._execute_json(manager, project_root, force_refresh, include_notes)

    def _execute_toon(
        self,
        manager: ProjectIndexManager,
        project_root: str,
        force_refresh: bool,
        include_notes: bool,
    ) -> dict[str, Any]:
        """TOON path — return the pre-rendered summary.toon when possible.

        H10/F12: keeps ``"toon"`` as the resolved value even when the
        caller passed the legacy ``"compact"`` alias.
        """
        resolved_fmt = "toon"
        toon_path = Path(project_root) / manager.TOON_FILE

        if not force_refresh and toon_path.exists():
            try:
                text = toon_path.read_text(encoding="utf-8")
                text = self._append_custom_notes_if_needed(text, manager, include_notes)
                summary_line, next_step = _build_project_summary_line(
                    manager.load(), project_root
                )
                return _toon_envelope(resolved_fmt, text, summary_line, next_step)
            except OSError:
                pass  # fall through to rebuild

        index: ProjectIndex = manager.build(force_refresh=force_refresh)
        text = self._read_or_render_toon(manager, project_root, index, include_notes)
        summary_line, next_step = _build_project_summary_line(index, project_root)
        return _toon_envelope(resolved_fmt, text, summary_line, next_step)

    @staticmethod
    def _append_custom_notes_if_needed(
        text: str,
        manager: ProjectIndexManager,
        include_notes: bool,
    ) -> str:
        """Append ``custom_notes`` to the TOON text when the index has them."""
        if not include_notes:
            return text
        idx_for_notes = manager.load()
        if not idx_for_notes:
            return text
        notes = idx_for_notes.custom_notes
        if notes and notes not in text:
            return text + f"\nnotes:    {notes}"
        return text

    @staticmethod
    def _read_or_render_toon(
        manager: ProjectIndexManager,
        project_root: str,
        index: ProjectIndex,
        include_notes: bool,  # noqa: ARG004 — kept for future tightening, unused symmetry with TOON path above
    ) -> str:
        """Return TOON text — read pre-rendered file when present, else render now."""
        toon_path = Path(project_root) / manager.TOON_FILE
        if toon_path.exists():
            return toon_path.read_text(encoding="utf-8")
        return manager.render_toon(index)

    def _execute_json(
        self,
        manager: ProjectIndexManager,
        project_root: str,
        force_refresh: bool,
        include_notes: bool,
    ) -> dict[str, Any]:
        """JSON path — load (or build) the full index, attach the canonical envelope."""
        idx: ProjectIndex | None = None
        if not force_refresh:
            idx = manager.load()
        if idx is None or force_refresh:
            idx = manager.build(force_refresh=force_refresh)

        age_hours = round((time.time() - idx.updated_at) / 3600, 2)
        is_fresh = age_hours < 1.0
        quick_start = _make_quick_start(idx)
        summary_line, next_step = _build_project_summary_line(idx, project_root)

        # H10: echo the resolved output_format on the JSON path so JSON
        # and TOON callers see the same envelope shape.
        result: dict[str, Any] = {
            "success": True,
            "format": "json",
            "output_format": "json",
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
            "summary_line": summary_line,
            "verdict": "INFO",  # r37x: top-level verdict mirror
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": next_step,
                "verdict": "INFO",  # T4 (round-37f): canonical envelope contract
            },
        }
        if include_notes:
            result["custom_notes"] = idx.custom_notes
        return result


def _build_project_summary_line(
    idx: ProjectIndex | None, project_root: str
) -> tuple[str, str]:
    """Build the (summary_line, next_step) tuple for get_project_summary.

    Pattern: "<project_name> <lang> <pct>%  critical: <top3 names>"
    Falls back gracefully when ``idx`` is None (e.g. TOON cache hit
    before the index loader has been invoked).
    """
    resolved = Path(project_root).resolve()
    project_name = resolved.name or resolved.parent.name or "project"

    if idx is None or not idx.language_distribution:
        summary_line = f"{project_name} (no index — call build_project_index)"
        next_step = "build_project_index to populate the project summary"
        return summary_line, next_step

    total_files = max(idx.file_count, 1)
    # Pick the dominant code language for the headline.
    code_langs = [
        (k, v)
        for k, v in idx.language_distribution.items()
        if k not in _NON_CODE_LANGUAGES and (v >= 10 or v / total_files >= 0.02)
    ]
    code_langs.sort(key=lambda kv: -kv[1])
    if code_langs:
        top_lang, top_count = code_langs[0]
        pct = int(round(100 * top_count / total_files))
        lang_part = f"{top_lang} {pct}%"
    else:
        lang_part = "mixed"

    # Top-3 critical nodes by PageRank.
    top_critical = [str(n.get("name", "?")) for n in (idx.critical_nodes or [])[:3]]
    critical_part = (
        f"critical: {', '.join(top_critical)}" if top_critical else "critical: n/a"
    )
    # J5 (round-22): single-space join via helper — earlier this line had a
    # literal double-space between ``{lang_part}`` and ``{critical_part}``.
    summary_line = format_summary_line(project_name, lang_part, critical_part)

    # Next-step hint — orient the agent on what to do after orientation.
    if top_critical:
        next_step = f"get_code_outline {top_critical[0]} for the most-referenced file's structure"
    elif idx.entry_points:
        next_step = f"read_partial {idx.entry_points[0]} to inspect the entry point"
    else:
        next_step = "list_files for a per-directory view"
    return summary_line, next_step
