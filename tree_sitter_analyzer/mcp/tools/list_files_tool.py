#!/usr/bin/env python3
"""
list_files MCP Tool (fd wrapper)

Safely list files/directories based on name patterns and constraints, using fd.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..utils.error_handler import handle_mcp_errors
from ..utils.gitignore_detector import get_default_detector
from . import fd_rg_utils
from .base_tool import BaseMCPTool
from .list_files_helpers import (
    TOOL_SCHEMA,
    CountResponseContext,
    DetailedResponseContext,
    _build_agent_summary,
    _build_fd_command,
    _decode_lines,
    _missing_fd_response,
    _resolve_effective_types,
    _respond_detailed,
)
from .list_files_helpers import (
    _respond_count_only as _build_count_only_response,
)

logger = logging.getLogger(__name__)

# Time budget (ms) for the follow-up unbounded fd pass that resolves the real
# total file count when the user-supplied limit truncated the first pass.
_RECOUNT_BUDGET_MS = 500


def _decode_error(err: bytes) -> str:
    """Decode fd error bytes to a displayable string."""
    return err.decode("utf-8", "replace").strip() or "fd failed"


def _is_string_list(val: Any) -> bool:
    """Return True iff val is a list of strings."""
    return isinstance(val, list) and all(isinstance(x, str) for x in val)


def _check_str(key: str, arguments: dict[str, Any]) -> None:
    """Raise ValueError if arguments[key] is present but not a str."""
    if key in arguments and not isinstance(arguments[key], str):
        raise ValueError(f"{key} must be a string")


def _check_bool(key: str, arguments: dict[str, Any]) -> None:
    """Raise ValueError if arguments[key] is present but not a bool."""
    if key in arguments and not isinstance(arguments[key], bool):
        raise ValueError(f"{key} must be a boolean")


def _check_str_list(arr: str, arguments: dict[str, Any]) -> None:
    """Raise ValueError if arguments[arr] is present but not a list of strings."""
    if arr in arguments and not _is_string_list(arguments[arr]):
        raise ValueError(f"{arr} must be an array of strings")


__all__ = ["ListFilesTool", "_build_agent_summary"]


class ListFilesTool(BaseMCPTool):
    """MCP tool that wraps fd to list files with safety limits."""

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the MCP tool name, description, and input schema."""
        return {
            "name": "list_files",
            "description": (
                "fd-based file listing. Discover directory structure before deeper "
                "analysis. Honors .gitignore by default and respects file-type "
                "categories (.py, .ts, etc.) via the ``types`` parameter.\n\n"
                "WHEN TO USE:\n"
                "- Mapping a new codebase before any other analysis\n"
                "- Filtering files by extension (e.g. only .py + .pyi)\n"
                "- Counting how many source files a project has via count_only=true\n"
                "- Producing a quick structural overview\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- To search file CONTENT — use search_content or find_and_grep\n"
                "- To analyse a single file's structure — use get_code_outline\n"
                "- To get a semantic project map — use project_overview"
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def _validate_single_root(self, r: str) -> str:
        """Validate and resolve one root directory path."""
        if not isinstance(r, str) or not r.strip():
            raise ValueError("root entries must be non-empty strings")
        try:
            return self.resolve_and_validate_directory_path(r)
        except ValueError as e:
            raise ValueError(f"Invalid root '{r}': {e}") from e

    def _validate_roots(self, roots: list[str]) -> list[str]:
        """Resolve and validate each root directory path.

        Empty lists are rejected by ``validate_arguments`` (O7) before they
        reach this method — when they do reach here, the explicit-empty
        case has already been caught and this guard handles defensive
        callers that hit the method directly.
        """
        if not roots or not isinstance(roots, list):
            raise ValueError("roots must be a non-empty array of strings")
        return [self._validate_single_root(r) for r in roots]

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate roots and all option types.

        ``roots`` is optional: when the key is **missing** entirely the
        tool falls back to ``self.project_root`` so callers don't have
        to repeat the project path they already configured on the tool
        instance.

        An **explicit empty value** (``roots=[]``, ``roots=None``, or
        ``roots=""``) is treated as a user error per O7 — silently
        rewriting it to ``[project_root]`` masked typos and made the
        downstream ``_validate_roots`` check unreachable.
        """
        # Wave 1b (audit project-05): ``path`` is a single-directory alias for
        # ``roots``. Map it BEFORE the roots resolution so a caller-supplied
        # scope is actually honored (and existence-validated downstream),
        # instead of being dropped and silently falling back to project_root —
        # which made ``files path=nonexistent_dir`` return the whole project.
        # An explicit-but-empty ``path`` is a user error (O7), NOT a silent
        # fallback to scanning the whole project — that would re-introduce the
        # very bug this fixes. ``pop`` so the consumed alias never lingers.
        if "path" in arguments and "roots" not in arguments:
            path_value = arguments.pop("path")
            if not path_value or not isinstance(path_value, str):
                raise ValueError(
                    "path must be a non-empty string (or omit it to scan project_root)"
                )
            arguments["roots"] = [path_value]
        if "roots" not in arguments:
            if not self.project_root:
                raise ValueError(
                    "roots is required when the tool has no project_root configured"
                )
            arguments["roots"] = [self.project_root]
        elif arguments["roots"] in (None, [], ""):
            raise ValueError(
                "roots must be a non-empty array of strings "
                "(or omit the key to scan project_root)"
            )
        roots = arguments["roots"]
        if not isinstance(roots, list):
            raise ValueError("roots must be an array")
        for key in ["pattern", "changed_within", "changed_before"]:
            _check_str(key, arguments)
        for key in [
            "glob",
            "follow_symlinks",
            "hidden",
            "no_ignore",
            "full_path_match",
            "absolute",
        ]:
            _check_bool(key, arguments)
        if "depth" in arguments and not isinstance(arguments["depth"], int):
            raise ValueError("depth must be an integer")
        if "limit" in arguments and not isinstance(arguments["limit"], int):
            raise ValueError("limit must be an integer")
        for arr in ["types", "extensions", "exclude", "size"]:
            _check_str_list(arr, arguments)
        return True

    @handle_mcp_errors("list_files")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute fd-based file listing with safety limits."""
        if not fd_rg_utils.check_external_command("fd"):
            return _missing_fd_response()

        self.validate_arguments(arguments)
        roots = self._validate_roots(arguments["roots"])

        limit = fd_rg_utils.clamp_int(
            arguments.get("limit"),
            fd_rg_utils.DEFAULT_RESULTS_LIMIT,
            fd_rg_utils.MAX_RESULTS_HARD_CAP,
        )

        effective_types = _resolve_effective_types(arguments)
        no_ignore = self._resolve_no_ignore(arguments)

        cmd = _build_fd_command(arguments, roots, limit, effective_types, no_ignore)

        started = time.time()
        rc, out, err = await fd_rg_utils.run_command_capture(cmd)
        t1 = time.time()
        diff_s = t1 - started
        elapsed_ms = int(diff_s * 1000)

        if rc != 0:
            return {"success": False, "error": _decode_error(err), "returncode": rc}

        lines = _decode_lines(out)

        # H3 fix: fd's --max-results truncates server-side, so a response
        # with len(lines)==limit could mean "exactly limit files exist" OR
        # "many more exist, we just stopped early." Run a follow-up fd pass
        # without --max-results to learn the truth. Budget: 500ms.
        real_total, total_count_known = await self._resolve_real_total(
            lines, limit, arguments, roots, effective_types, no_ignore
        )

        if arguments.get("count_only", False):
            return self._respond_count_only(
                lines,
                elapsed_ms,
                arguments,
                limit,
                real_total=real_total,
                total_count_known=total_count_known,
            )

        return _respond_detailed(
            DetailedResponseContext(
                lines=lines,
                elapsed_ms=elapsed_ms,
                arguments=arguments,
                limit=limit,
                no_ignore=no_ignore,
                effective_types=effective_types,
                project_root=self.project_root,
            ),
            real_total=real_total,
            total_count_known=total_count_known,
        )

    async def _resolve_real_total(
        self,
        lines: list[str],
        limit: int,
        arguments: dict[str, Any],
        roots: list[str],
        effective_types: list[str] | None,
        no_ignore: bool,
    ) -> tuple[int, bool]:
        """Recount without --max-results when fd may have truncated.

        Returns ``(real_total, total_count_known)``.

        - Not truncated: ``(len(lines), True)`` — first pass already complete.
        - Truncated and recount within budget: ``(real_count, True)``.
        - Truncated and recount over budget or failed: ``(len(lines), False)``.
        """
        # Heuristic: if fd returned strictly fewer lines than the cap, there's
        # nothing more to find — the first pass was exhaustive.
        if len(lines) < limit:
            return len(lines), True

        try:
            unbounded_cmd = _build_fd_command(
                arguments,
                roots,
                fd_rg_utils.MAX_RESULTS_HARD_CAP,
                effective_types,
                no_ignore,
            )
            started = time.perf_counter()
            rc, out, _err = await fd_rg_utils.run_command_capture(
                unbounded_cmd,
                timeout_ms=_RECOUNT_BUDGET_MS,
            )
            t_end = time.perf_counter()
            elapsed = t_end - started
            recount_ms = int(elapsed * 1000)

            if rc != 0:
                logger.debug("list_files recount rc=%s in %sms", rc, recount_ms)
                return len(lines), False

            if recount_ms > _RECOUNT_BUDGET_MS:
                return len(lines), False

            recount_lines = _decode_lines(out)
            real_total = len(recount_lines)
            if real_total < len(lines):
                # Defensive: should not happen, but trust the visible lines.
                return len(lines), False
            return real_total, True
        except Exception as exc:  # noqa: BLE001
            logger.debug("list_files recount raised %s; using estimate", exc)
            return len(lines), False

    def _resolve_no_ignore(self, arguments: dict[str, Any]) -> bool:
        """Determine no_ignore flag with smart gitignore detection."""
        no_ignore = bool(arguments.get("no_ignore", False))
        if no_ignore:
            return no_ignore

        detector = get_default_detector()
        original_roots = arguments.get("roots", [])
        should_ignore = detector.should_use_no_ignore(original_roots, self.project_root)
        if should_ignore:
            detection_info = detector.get_detection_info(
                original_roots, self.project_root
            )
            logger.info(
                "Auto-enabled --no-ignore due to .gitignore interference: %s",
                detection_info["reason"],
            )
            return True
        return False

    def _respond_count_only(
        self,
        lines: list[str],
        elapsed_ms: int,
        arguments: dict[str, Any],
        limit: int,
        *,
        real_total: int | None = None,
        total_count_known: bool = True,
    ) -> dict[str, Any]:
        """Return count-only response through the shared response helper."""
        return _build_count_only_response(
            CountResponseContext(
                lines=lines,
                elapsed_ms=elapsed_ms,
                arguments=arguments,
                limit=limit,
                project_root=self.project_root,
            ),
            real_total=real_total,
            total_count_known=total_count_known,
        )
