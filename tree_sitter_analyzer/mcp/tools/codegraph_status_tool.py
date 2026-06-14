#!/usr/bin/env python3
"""
CodeGraph Status MCP Tool — INDEX HEALTH at-a-glance (CodeGraph parity).

Consolidates ast_cache + codegraph_autoindex + check_tools signals into a
single read-only call so agents know whether the index is ready, how stale
it is, and where to look. Replaces 3-4 separate tool calls.
"""

from __future__ import annotations

import os
from typing import Any

from ...utils import setup_logger
from ..utils.auto_index_guard import is_indexed
from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_response
from .base_tool import BaseMCPTool
from .index_rebuild_signal import is_index_rebuilding

logger = setup_logger(__name__)

# Cap walk cost — large monorepos can have 100k+ files; the lag signal is
# qualitative, not exact, so a bounded sample is fine.
_LAG_WALK_FILE_CAP = 5000

# Source extensions we count for "newest source mtime". Mirrors the set
# the auto_index_guard considers index-worthy.
_LAG_SOURCE_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs")

# Directories we don't traverse — cache/build artefacts only inflate the
# walk and never carry the newest user-edit timestamp.
_LAG_SKIP_DIRS = frozenset(
    {
        ".ast-cache",
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)


class CodeGraphStatusTool(BaseMCPTool):
    """MCP Tool for index health at-a-glance (CodeGraph parity)."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_status",
            "description": (
                "INDEX HEALTH at-a-glance (CodeGraph parity). "
                "One call returns: indexed yes/no, total files, total symbols, "
                "schema version, FTS5 availability, cache lag vs newest source. "
                "Use BEFORE any codegraph_* navigation call to decide whether to "
                "warm the cache first. Replaces ast_cache + codegraph_autoindex "
                "+ check_tools triangulation."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_lag": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Compare cache timestamp against newest source file mtime "
                        "to estimate index lag"
                    ),
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": "Output format (default: toon)",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        include_lag = arguments.get("include_lag", True)
        if not isinstance(include_lag, bool):
            raise ValueError("include_lag must be a boolean")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        include_lag = arguments.get("include_lag", True)
        output_format = arguments.get("output_format", "toon")

        # NOT_FOUND: no project_root → we literally cannot look anywhere.
        # Distinct from WARN (project set, just no cache yet) so agents can
        # branch on "set the path" vs "warm the index".
        if not self.project_root:
            result = build_response(
                verdict="NOT_FOUND",
                project_root=None,
                indexed=False,
                total_files=0,
                total_symbols=0,
                fts5_available=False,
                lag_seconds=None,
                cache_path=None,
                hint="project_root not set. Call set_project_path first.",
            )
            return apply_toon_format_to_response(result, output_format)

        cache_path = os.path.join(self.project_root, ".ast-cache", "index.db")
        cache_exists = os.path.exists(cache_path)

        stats: dict[str, Any] | None = None
        indexed_flag = is_indexed(self.project_root)
        if cache_exists:
            stats = self._safe_get_stats()

        # "Indexed" means we have a cache file AND it actually contains rows.
        # Empty cache (file exists, 0 files) is still WARN — agent should warm.
        truly_indexed = bool(stats and stats.get("total_files", 0) > 0)

        # #578: a full rebuild empties ast_index mid-flight. Distinguish that
        # transient empty/partial state from a genuinely missing index so the
        # agent retries instead of kicking off a redundant rebuild.
        rebuilding = self._is_rebuilding() if cache_exists else False

        if not truly_indexed:
            hint = (
                "Index missing or empty. Run the `index` tool with action=auto "
                "to build the cache."
            )
            if rebuilding:
                hint = (
                    "Full rebuild in progress — the index is transiently empty. "
                    "Do NOT start another index; retry status/nav shortly."
                )
            result = build_response(
                verdict="WARN",
                project_root=self.project_root,
                indexed=False,
                total_files=0,
                total_symbols=0,
                fts5_available=bool(stats.get("fts5_available")) if stats else False,
                lag_seconds=None,
                cache_path=cache_path if cache_exists else None,
                hint=hint,
                agent_summary={
                    "summary_line": (
                        "codegraph_status: full rebuild in progress (transient)"
                        if rebuilding
                        else "codegraph_status: index missing or empty"
                    ),
                    "next_step": hint,
                    "verdict": "WARN",
                },
            )
            # #578: only emit the flag when truthy (don't emit false scalars).
            if rebuilding:
                result["index_rebuilding"] = True
            # Item 1: omit schema_version when None (don't emit null scalars)
            if stats and stats.get("schema_version") is not None:
                result["schema_version"] = stats.get("schema_version")
            return apply_toon_format_to_response(result, output_format)

        lag_seconds = None
        if include_lag:
            lag_seconds = self._compute_lag(cache_path)

        # Item 1: real next_step for INFO verdict. Index is healthy, so suggest
        # proceeding with nav/search. Staleness check if lag available.
        next_step = "Index is healthy — proceed with nav or search tools"
        if lag_seconds is not None and lag_seconds > 300:  # 5+ minutes stale
            next_step = (
                "Index is healthy but stale (>5 min). Run action=sync first, "
                "then proceed with nav/search"
            )
        if rebuilding:
            # #578: nonempty but a rebuild is replacing rows — counts are partial.
            next_step = (
                "Full rebuild in progress — counts are partial and changing. "
                "Wait for it to finish before trusting nav/search results."
            )

        total_files = int(stats.get("total_files", 0)) if stats else 0
        total_symbols = int(stats.get("total_symbols", 0)) if stats else 0
        total_edges = int(stats.get("total_edges", 0)) if stats else 0

        # #578: a rebuild replacing rows makes counts untrustworthy → WARN.
        verdict = "WARN" if rebuilding else "INFO"
        result = build_response(
            verdict=verdict,
            project_root=self.project_root,
            indexed=True,
            total_files=total_files,
            total_symbols=total_symbols,
            total_edges=total_edges,
            # CodeGraph parity: per-kind and per-language symbol breakdowns
            # + edges_by_kind (beyond CodeGraph — CG has no edge breakdown).
            # Degrade to empty dicts when the underlying stats omit them.
            symbols_by_kind=dict(stats.get("symbols_by_kind") or {}) if stats else {},
            symbols_by_language=dict(stats.get("symbols_by_language") or {})
            if stats
            else {},
            edges_by_kind=dict(stats.get("edges_by_kind") or {}) if stats else {},
            fts5_available=bool(stats.get("fts5_available")) if stats else False,
            lag_seconds=lag_seconds,
            cache_path=cache_path,
            auto_index_guard_warm=indexed_flag,
            agent_summary={
                "summary_line": (
                    f"codegraph_status: {total_files} files, "
                    f"{total_symbols} symbols, "
                    f"{total_edges} edges"
                ),
                "next_step": next_step,
                "verdict": verdict,
            },
        )
        # #578: only emit the flag when truthy (don't emit false scalars).
        if rebuilding:
            result["index_rebuilding"] = True
        # Item 1: omit schema_version when None (don't emit null scalars)
        if stats and stats.get("schema_version") is not None:
            result["schema_version"] = stats.get("schema_version")
        return apply_toon_format_to_response(result, output_format)

    def _is_rebuilding(self) -> bool:
        """True while a full rebuild is replacing the cache (#578).

        Reads the persisted marker via a throwaway connection to the real cache
        db — deliberately not through ASTCache, to stay consistent with this
        tool's short-lived, handle-closing style and to avoid a migration just
        to check one flag. Never raises.
        """
        if not self.project_root:  # pragma: no cover — execute() guarantees it
            return False
        db_path = os.path.join(self.project_root, ".ast-cache", "index.db")
        if not os.path.exists(
            db_path
        ):  # pragma: no cover — caller gates on cache_exists
            return False
        return is_index_rebuilding(self.project_root)

    def _safe_get_stats(self) -> dict[str, Any] | None:
        # Always close the SQLite handle — this tool is read-only and
        # short-lived; leaving the cache open would leak a handle per
        # invocation. The navigate tool keeps its cache open across calls
        # because it reuses the connection; we don't.
        # Caller (execute) already early-returned on project_root unset,
        # so the explicit guard here is for mypy and defence-in-depth.
        if not self.project_root:
            return None
        try:
            from ...ast_cache import ASTCache

            cache = ASTCache(self.project_root)
        except Exception as exc:
            logger.debug(f"ASTCache open failed: {exc}")
            return None
        try:
            stats = cache.get_stats()
            # ``get_stats`` already reports ``total_edges`` as the sum across
            # ALL edge kinds, reconciling with ``edges_by_kind`` (Codex P2 #315).
            # Do NOT override it with the call-edge-only count, which made
            # total_edges disagree with the breakdown. The call-edge resolution
            # signal lives in get_cross_file_stats for callers that want it.
            stats.setdefault("total_edges", 0)
            return stats
        except Exception as exc:
            logger.debug(f"ASTCache.get_stats failed: {exc}")
            return None
        finally:
            try:
                cache.close()
            except Exception:
                pass

    def _compute_lag(self, cache_path: str) -> float | None:
        if not os.path.exists(cache_path):
            return None
        try:
            db_mtime = os.path.getmtime(cache_path)
        except OSError:
            return None

        newest_src = self._newest_source_mtime()
        if newest_src is None:
            return None
        return max(0.0, newest_src - db_mtime)

    def _newest_source_mtime(self) -> float | None:
        # Bounded walk: 5000-file cap keeps cost predictable on monorepos;
        # lag is a qualitative signal, not a forensic timestamp.
        if not self.project_root or not os.path.isdir(self.project_root):
            return None

        newest: float | None = None
        seen = 0
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in _LAG_SKIP_DIRS]
            for fname in files:
                if not fname.endswith(_LAG_SOURCE_EXTS):
                    continue
                seen += 1
                if seen > _LAG_WALK_FILE_CAP:
                    return newest
                try:
                    m = os.path.getmtime(os.path.join(root, fname))
                except OSError:
                    continue
                if newest is None or m > newest:
                    newest = m
        return newest
