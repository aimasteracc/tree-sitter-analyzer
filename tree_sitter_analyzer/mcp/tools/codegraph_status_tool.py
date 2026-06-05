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
                schema_version=None,
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

        if not truly_indexed:
            hint = (
                "Index missing or empty. Run codegraph_autoindex mode=warm "
                "to build the cache."
            )
            result = build_response(
                verdict="WARN",
                project_root=self.project_root,
                indexed=False,
                total_files=0,
                total_symbols=0,
                schema_version=None,
                fts5_available=bool(stats.get("fts5_available")) if stats else False,
                lag_seconds=None,
                cache_path=cache_path if cache_exists else None,
                hint=hint,
            )
            return apply_toon_format_to_response(result, output_format)

        lag_seconds = None
        if include_lag:
            lag_seconds = self._compute_lag(cache_path)

        result = build_response(
            verdict="INFO",
            project_root=self.project_root,
            indexed=True,
            total_files=int(stats.get("total_files", 0)) if stats else 0,
            total_symbols=int(stats.get("total_symbols", 0)) if stats else 0,
            total_edges=int(stats.get("total_edges", 0)) if stats else 0,
            # CodeGraph parity: per-kind and per-language symbol breakdowns
            # + edges_by_kind (beyond CodeGraph — CG has no edge breakdown).
            # Degrade to empty dicts when the underlying stats omit them.
            symbols_by_kind=dict(stats.get("symbols_by_kind") or {}) if stats else {},
            symbols_by_language=dict(stats.get("symbols_by_language") or {})
            if stats
            else {},
            edges_by_kind=dict(stats.get("edges_by_kind") or {}) if stats else {},
            schema_version=stats.get("schema_version") if stats else None,
            fts5_available=bool(stats.get("fts5_available")) if stats else False,
            lag_seconds=lag_seconds,
            cache_path=cache_path,
            hint=None,
            auto_index_guard_warm=indexed_flag,
        )
        return apply_toon_format_to_response(result, output_format)

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
            # Enrich with call-edge count for graph density signal.
            try:
                edge_stats = cache.get_cross_file_stats()
                stats["total_edges"] = edge_stats.get("total", 0)
            except Exception:
                stats["total_edges"] = 0
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
