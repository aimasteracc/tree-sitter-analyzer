#!/usr/bin/env python3
"""
build_project_index MCP Tool

Explicitly rebuild the persistent project index from scratch and save it to disk.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
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
        """Validate roots against project boundary before any filesystem traversal.

        Security contract (r37fB):
        - Every root must be a non-empty string.
        - Every root must resolve to an absolute path that is strictly within
          self.project_root (via SecurityValidator.validate_directory_path).
        - If roots is omitted and no project_root is configured, raise an
          error rather than defaulting to an unbounded traversal.
        - Nonexistent paths are rejected (must_exist=True inside
          resolve_and_validate_directory_path).

        Raises:
            ValueError: if any root fails type, boundary, or existence check.
        """
        roots_raw = arguments.get("roots")

        # Normalise: missing key → default to project_root; explicit empty → error.
        if roots_raw is None or "roots" not in arguments:
            if not self.project_root:
                raise ValueError("project_root not set; pass roots=[...] explicitly")
            # Inject the default so execute() can rely on it being present.
            arguments["roots"] = [self.project_root]
            return True

        if roots_raw in ([], "", None):
            if not self.project_root:
                raise ValueError("project_root not set; pass roots=[...] explicitly")
            arguments["roots"] = [self.project_root]
            return True

        roots = roots_raw
        if not isinstance(roots, list):
            raise ValueError("roots must be an array of strings")

        for root in roots:
            if not isinstance(root, str) or not root.strip():
                raise ValueError(
                    f"roots entries must be non-empty strings; got {root!r}"
                )

            # Resolve to absolute path so boundary check is unambiguous.
            if os.path.isabs(root):
                resolved = Path(root).resolve()
            else:
                base = self.project_root or os.getcwd()
                resolved = Path(base, root).resolve()

            # Boundary check: resolved path must be within project_root.
            if self.project_root:
                project_abs = Path(self.project_root).resolve()
                # Allow the project root itself and any sub-path.
                try:
                    resolved.relative_to(project_abs)
                except ValueError as boundary_err:
                    raise ValueError(
                        f"Refusing to index outside project: {root!r} "
                        f"resolves to {resolved}, which is outside "
                        f"project root {project_abs}"
                    ) from boundary_err

            # Existence + directory check (delegates to SecurityValidator
            # via the base-class helper, preserving the established pattern).
            try:
                self.resolve_and_validate_directory_path(str(resolved))
            except ValueError as exc:
                raise ValueError(f"Invalid root {root!r}: {exc}") from exc

        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Build a fresh project index, persist it, and return a build report."""
        try:
            self.validate_arguments(arguments)
        except ValueError as exc:
            summary_line = f"build_project_index refused: {exc}"
            return {
                "success": False,
                "error": str(exc),
                "error_type": "security",
                "summary_line": summary_line,
                "verdict": "ERROR",
                "agent_summary": {
                    "summary_line": summary_line,
                    "next_step": "Pass roots within the project boundary.",
                    "verdict": "ERROR",
                },
            }

        try:
            return await self._do_execute(arguments)
        except Exception as exc:  # noqa: BLE001
            summary_line = f"build_project_index internal error: {exc}"
            return {
                "success": False,
                "error": str(exc),
                "error_type": "internal",
                "summary_line": summary_line,
                "verdict": "ERROR",
                "agent_summary": {
                    "summary_line": summary_line,
                    "next_step": "Check server logs for details.",
                    "verdict": "ERROR",
                },
            }

    async def _do_execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Core build logic — called only after validate_arguments passes."""
        roots_raw: list[Any] = arguments.get("roots") or [self.project_root or "."]
        add_notes: str = str(arguments.get("add_notes") or "")

        project_root = self.project_root or "."
        manager = ProjectIndexManager(project_root)

        # Resolve roots relative to project_root when not absolute.
        roots: list[str] = []
        for r in roots_raw:
            r_str = str(r)
            if os.path.isabs(r_str):
                roots.append(r_str)
            else:
                roots.append(os.path.join(project_root, r_str))

        start_ms = time.time() * 1000
        index: ProjectIndex = manager.build(roots=roots)

        # Attach user notes (preserving existing notes if none provided).
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
        # mirror line + next_step + verdict (INFO — build op, not analysis).
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
            # r37fB: use _canonicalize_verdict instead of hardcoded "n/a".
            "verdict": "INFO",
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": next_step,
                "verdict": "INFO",
            },
        }
        return mirror_summary_line(response)
