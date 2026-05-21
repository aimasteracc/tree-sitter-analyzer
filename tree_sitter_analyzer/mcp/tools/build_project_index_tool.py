#!/usr/bin/env python3
"""
build_project_index MCP Tool

Explicitly rebuild the persistent project index from scratch and save it to disk.
"""

from __future__ import annotations

import time
from typing import Any

from ..utils.project_index import ProjectIndex, ProjectIndexManager
from .base_tool import BaseMCPTool, mirror_summary_line
from .get_project_summary_tool import _make_quick_start


class BuildProjectIndexTool(BaseMCPTool):
    """MCP tool that rebuilds and persists the project structure index."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "build_project_index",
            "description": (
                "Rebuild the persistent project index from scratch and save it to disk.\n\n"
                "Call this when: the project structure has changed significantly, "
                "get_project_summary returns stale data, or you are setting up "
                "tree-sitter-analyzer in a project for the first time and want to "
                "pre-build the index.\n\n"
                "WHEN TO USE:\n"
                "- After major refactoring (moved directories, renamed modules)\n"
                "- First time setup in a new project\n"
                "- When get_project_summary reports index_age_hours > 24\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- Every session — the index auto-loads from disk and stays fresh "
                "for 24 hours\n"
                "- When you just want to read the current index (use "
                "get_project_summary instead)\n"
                "\n"
                "Returns: build_duration_ms, files_scanned, languages_found, "
                "index_saved_to path."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "roots": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Directories to index. Defaults to project root."
                        ),
                        "default": ["."],
                    },
                    "add_notes": {
                        "type": "string",
                        "description": (
                            "Optional architecture notes to store with the index. "
                            "E.g. 'Monorepo: packages/ contains 3 services. "
                            "Entry point is packages/api/main.py'"
                        ),
                        "default": "",
                    },
                },
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Build a fresh project index, persist it, and return a build report."""
        roots_raw: list[Any] = arguments.get("roots") or ["."]
        add_notes: str = str(arguments.get("add_notes") or "")

        project_root = self.project_root or "."
        manager = ProjectIndexManager(project_root)

        # Resolve roots relative to project_root when not absolute
        import os

        roots: list[str] = []
        for r in roots_raw:
            r_str = str(r)
            if os.path.isabs(r_str):
                roots.append(r_str)
            else:
                roots.append(os.path.join(project_root, r_str))

        start_ms = time.time() * 1000
        index: ProjectIndex = manager.build(roots=roots)

        # Attach user notes (preserving existing notes if none provided)
        if add_notes:
            index.custom_notes = add_notes
        elif (existing := manager.load()) is not None:
            index.custom_notes = existing.custom_notes

        manager.save(index)
        build_duration_ms = round(time.time() * 1000 - start_ms)

        quick_start = _make_quick_start(index)

        # H5: build a canonical envelope — ``success``, top-level
        # ``summary_line`` (one-liner with the file count + duration so
        # callers can audit at a glance), and ``agent_summary`` with the
        # mirror line + next_step + verdict ("n/a" — this is a build
        # operation, not an analysis verdict).
        files_scanned = int(index.file_count or 0)
        languages_count = len(index.language_distribution or {})
        summary_line = (
            f"build_project_index built files={files_scanned} "
            f"languages={languages_count} duration_ms={build_duration_ms}"
        )
        next_step = "get_project_summary to retrieve this index in future sessions"
        response: dict[str, Any] = {
            "success": True,
            "status": "built",
            "build_duration_ms": build_duration_ms,
            "files_scanned": files_scanned,
            "languages_found": index.language_distribution,
            "index_saved_to": manager.CACHE_FILE,
            "quick_start": quick_start,
            "next_step": next_step,
            "summary_line": summary_line,
            # r37x (envelope ratchet): top-level verdict mirror (r37u contract).
            "verdict": "n/a",
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": next_step,
                "verdict": "n/a",
            },
        }
        return mirror_summary_line(response)
