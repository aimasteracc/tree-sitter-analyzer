#!/usr/bin/env python3
"""
CodeGraph Full Index MCP Tool — One-shot complete project intelligence.

Runs the entire indexing pipeline in a single call:
  1. AST cache: parse all source files, extract symbols/imports/structure
  2. Call edges: extract function calls and build call graph edges
  3. FTS5: build full-text search index over all symbols
  4. Incremental sync: detect changed/new/deleted files, re-index only changed
  5. Synapse resolution: resolve cross-file callee targets

Returns a unified report with file counts, symbol counts, call edges, and
timing per phase. Agents call this ONCE at session start instead of making
5+ separate tool calls.

CodeGraph parity: equivalent to CodeGraph's "index everything" single command.
"""

from __future__ import annotations

import time
from typing import Any

from ...utils import setup_logger
from ..utils.auto_index_guard import mark_dirty
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphFullIndexTool(BaseMCPTool):
    """MCP Tool for one-shot complete project intelligence indexing."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_full_index",
            "description": (
                "One-shot complete project intelligence index (CodeGraph parity). "
                "Runs AST parse + call edges + FTS5 + incremental sync + "
                "cross-file resolution in a single call. "
                "Agents call this once at session start — all codegraph tools "
                "become instant afterward. "
                "Mode 'full' forces re-index; 'incremental' only processes changes. "
                "No other tool runs the complete indexing pipeline."
            ),
            "inputSchema": self.get_tool_schema(),
            # destructive depending on mode (rebuild/warm/sync write the cache)
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["full", "incremental"],
                    "description": (
                        "'full' forces re-index of all files (slow, thorough); "
                        "'incremental' only processes changed files (fast, default)"
                    ),
                    "default": "incremental",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Max files to index (default: 20000)",
                    "default": 20000,
                },
                "resolve_synapse": {
                    "type": "boolean",
                    "description": "Run cross-file callee resolution after indexing (default: true)",
                    "default": True,
                },
                "include_activation": {
                    "type": "boolean",
                    "description": (
                        "Compute temporal git activation during AST cache indexing. "
                        "Default false keeps large-repo warm-up fast."
                    ),
                    "default": False,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format (default: toon)",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "incremental")
        if mode not in ("full", "incremental"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'full' or 'incremental'")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        if not self.project_root:
            return apply_toon_format_to_response(
                {
                    "success": False,
                    "verdict": "ERROR",
                    "error": "project_root not set. Call set_project_path first.",
                },
                arguments.get("output_format", "toon"),
            )

        mode = arguments.get("mode", "incremental")
        max_files = arguments.get("max_files", 20_000)
        resolve_synapse = arguments.get("resolve_synapse", True)
        include_activation = bool(arguments.get("include_activation", False))
        output_format = arguments.get("output_format", "toon")

        phases: dict[str, Any] = {}
        t_start = time.monotonic()

        if mode == "full":
            mark_dirty(self.project_root)

        ast_phase = self._phase_ast_cache(
            mode == "full",
            max_files,
            include_activation=include_activation,
        )
        phases["ast_cache"] = ast_phase
        phases["incremental_sync"] = self._phase_incremental_sync()
        phases["fts5"] = self._phase_fts5_stats()

        if resolve_synapse:
            # A1: the ast_cache phase already ran the complete backfill chain
            # (cross-file + synapse + edge-store refresh + unresolved_refs) via
            # _post_index_backfill. Re-running index_project(resolve_only=True)
            # here repeated the whole O(edges) chain a second time — on large
            # Java repos that doubled backfill time and was a primary stall/OOM
            # cause. Report from the already-computed stats instead of re-running.
            phases["synapse_resolution"] = self._phase_synapse(ast_phase)

        phases["call_edges"] = self._phase_call_edge_stats()

        elapsed = round(time.monotonic() - t_start, 3)

        stats = self._collect_final_stats()

        # #860: propagate phase-level errors to top-level verdict so callers
        # don't receive "success: True / verdict: INFO" when a DB flush failed.
        any_phase_error = any(
            p.get("status") == "error" for p in phases.values() if isinstance(p, dict)
        )
        top_verdict = "WARN" if any_phase_error else "INFO"

        result: dict[str, Any] = {
            "success": True,
            "verdict": top_verdict,
            "mode": mode,
            "elapsed_seconds": elapsed,
            "phases": phases,
            **stats,
        }

        return apply_toon_format_to_response(result, output_format)

    def _phase_ast_cache(
        self,
        force: bool,
        max_files: int,
        *,
        include_activation: bool = False,
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        try:
            from ...ast_cache import ASTCache

            cache = ASTCache(self.project_root or ".")
            result = cache.index_project(
                max_files=max_files,
                force=force,
                include_activation=include_activation,
            )
            elapsed = round(time.monotonic() - t0, 3)
            indexed = result.get("indexed", 0)
            cached = result.get("cached", 0)
            errors = result.get("errors", 0)
            cache.close()
            return {
                "status": "ok",
                "elapsed_seconds": elapsed,
                "files_indexed": indexed,
                "files_cached": cached,
                "errors": errors,
                "mode_used": result.get("mode_used", "unknown"),
                "activation_enabled": result.get("activation_enabled", False),
                # Surface the backfill counts produced by _post_index_backfill so
                # the synapse_resolution phase can report without re-running (A1).
                "synapse_backfill": result.get("synapse_backfill"),
                "unresolved_refs_backfill": result.get("unresolved_refs_backfill"),
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "elapsed_seconds": round(time.monotonic() - t0, 3),
            }

    def _phase_incremental_sync(self) -> dict[str, Any]:
        t0 = time.monotonic()
        try:
            from ...ast_cache import ASTCache
            from ...incremental_sync import IncrementalSync

            cache = ASTCache(self.project_root or ".")
            sync = IncrementalSync(cache)
            result = sync.sync(max_files=20_000)
            cache.close()
            elapsed = round(time.monotonic() - t0, 3)
            # #860: surface DB flush failures — sync catches them into result.errors
            # so they never raise but also must NOT be silently reported as "ok".
            status = "error" if result.errors > 0 else "ok"
            return {
                "status": status,
                "elapsed_seconds": elapsed,
                "scanned": result.scanned,
                "new_files": result.new_files,
                "updated_files": result.updated_files,
                "deleted_files": result.deleted_files,
                "unchanged_files": result.unchanged_files,
                "errors": result.errors,
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "elapsed_seconds": round(time.monotonic() - t0, 3),
            }

    def _phase_fts5_stats(self) -> dict[str, Any]:
        try:
            from ...ast_cache import ASTCache

            cache = ASTCache(self.project_root or ".")
            stats = cache.get_stats()
            cache.close()
            return {
                "status": "ok",
                "fts5_available": stats.get("fts5_available", False),
                "fts_indexed_symbols": stats.get("fts_indexed_symbols", 0),
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _phase_synapse(self, ast_phase: dict[str, Any]) -> dict[str, Any]:
        """Report cross-file resolution results.

        A1: cross-file resolution is performed once inside the ast_cache phase
        (``index_project`` -> ``_post_index_backfill``). This phase no longer
        re-runs the backfill chain; it summarizes the counts the ast_cache phase
        already produced. This halves backfill time on large repos and removes
        the duplicate full EdgeStore rewrite that caused the stall/OOM.
        """
        synapse = ast_phase.get("synapse_backfill") or {}
        unresolved = ast_phase.get("unresolved_refs_backfill") or {}
        resolved_edges = 0
        if isinstance(synapse, dict):
            resolved_edges += int(synapse.get("resolved", 0))
        if isinstance(unresolved, dict):
            resolved_edges += int(unresolved.get("resolved", 0))
        return {
            "status": "ok",
            "elapsed_seconds": 0.0,
            "resolved_edges": resolved_edges,
            "note": "resolved during ast_cache phase (single-pass backfill)",
        }

    def _phase_call_edge_stats(self) -> dict[str, Any]:
        try:
            from ...ast_cache import ASTCache

            cache = ASTCache(self.project_root or ".")
            has_edges = cache.has_call_edges()
            stats = cache.get_stats()
            cache.close()
            return {
                "status": "ok",
                "has_call_edges": has_edges,
                "total_files": stats.get("total_files", 0),
                "total_symbols": stats.get("total_symbols", 0),
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _collect_final_stats(self) -> dict[str, Any]:
        try:
            from ...ast_cache import ASTCache

            cache = ASTCache(self.project_root or ".")
            stats = cache.get_stats()
            cache.close()
            return {
                "total_files": stats.get("total_files", 0),
                "total_symbols": stats.get("total_symbols", 0),
                "by_language": stats.get("by_language", {}),
                "fts5_available": stats.get("fts5_available", False),
                "fts_indexed_symbols": stats.get("fts_indexed_symbols", 0),
            }
        except Exception:
            return {}
