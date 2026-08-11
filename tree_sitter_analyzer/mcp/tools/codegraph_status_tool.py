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

from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_response
from .base_tool import BaseMCPTool

_DB_STORAGE_KEYS = (
    "db_size_bytes",
    "db_page_size",
    "db_page_count",
    "db_free_pages",
    "db_free_bytes",
    "db_auto_vacuum_mode",
)


class CodeGraphStatusTool(BaseMCPTool):
    """MCP Tool for index health at-a-glance (CodeGraph parity)."""

    def __init__(
        self, project_root: str | None = None, *, read_existing_default: bool = False
    ) -> None:
        self._read_existing_default = read_existing_default
        super().__init__(project_root)

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
                "access_mode": {
                    "type": "string",
                    "enum": ["read_existing"],
                    "default": "read_existing",
                    "description": "Open only an existing compatible index, without writes",
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
        access_mode = arguments.get("access_mode")
        if access_mode not in (None, "read_existing"):
            raise ValueError("access_mode must be read_existing")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "toon")
        # Status is unconditionally read-only.  JSON Schema defaults are not
        # injected by every direct caller, so omission must be handled here.
        return self._execute_read_existing(
            output_format, include_lag=arguments.get("include_lag", True)
        )

    def _execute_read_existing(
        self, output_format: str, *, include_lag: bool
    ) -> dict[str, Any]:
        """Serve status solely from one owner-issued SQLite read transaction."""
        from ...index_snapshot import (
            ACTION_VERSION,
            read_existing_snapshot,
            read_snapshot_stats,
        )

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
                snapshot_id=None,
                source_fingerprint=None,
                index_fingerprint=None,
                source_generation=None,
                completeness="unknown",
                oracle_reason="MISSING_PROJECT_ROOT",
                action_version=ACTION_VERSION,
                access_mode="read_existing",
                hint="project_root not set. Call set_project_path first.",
            )
            return apply_toon_format_to_response(result, output_format)

        snapshot = read_existing_snapshot(self.project_root)
        stats: dict[str, Any] = {}
        if snapshot.snapshot_id is not None:
            try:
                stats = read_snapshot_stats(
                    snapshot.snapshot_id,
                    self.project_root,
                    snapshot.source_generation,
                )
                expected_tokens = {
                    "snapshot_id": snapshot.snapshot_id,
                    "source_generation": snapshot.source_generation,
                    "source_fingerprint": snapshot.source_fingerprint,
                    "index_fingerprint": snapshot.index_fingerprint,
                }
                if any(
                    stats.get(key) != value for key, value in expected_tokens.items()
                ):
                    raise ValueError("SNAPSHOT_TOKEN_MISMATCH")
            except (OSError, ValueError, RuntimeError):
                snapshot = type(snapshot)(
                    None, None, None, None, "unknown", "SNAPSHOT_READ_FAILED", None, 0
                )
                stats = {}
        total_files = int(stats.get("total_files", 0))
        total_symbols = int(stats.get("total_symbols", 0))
        total_edges = int(stats.get("total_edges", 0))
        complete = snapshot.completeness == "complete"
        indexed = complete or total_files > 0
        verdict = "INFO" if indexed and complete else "WARN"
        cache_path = (
            os.path.join(snapshot.canonical_root, ".ast-cache", "index.db")
            if snapshot.canonical_root and snapshot.snapshot_id
            else None
        )
        if complete:
            hint = (
                "Index is complete. Use nav/search normally; snapshot IDs are "
                "process-local audit tokens owned internally for future reader "
                "composition, not caller inputs."
            )
        elif snapshot.reason == "CONCURRENT_WRITER":
            hint = (
                "A full-index rebuild is in progress. Retry status after it finishes. "
                "Do NOT start another index operation."
            )
        else:
            hint = (
                "Index snapshot is unavailable or not certified by an exact "
                "full-index manifest."
            )
        lag_seconds = None
        if include_lag and cache_path is not None:
            from ...index_lag import compute_qualitative_lag

            lag_seconds = compute_qualitative_lag(self.project_root, cache_path)

        result = build_response(
            verdict=verdict,
            project_root=snapshot.canonical_root or self.project_root,
            indexed=indexed,
            total_files=total_files,
            total_symbols=total_symbols,
            total_edges=total_edges,
            symbols_by_kind=dict(stats.get("symbols_by_kind") or {}),
            symbols_by_language=dict(stats.get("symbols_by_language") or {}),
            edges_by_kind=dict(stats.get("edges_by_kind") or {}),
            fts5_available=bool(stats.get("fts5_available", False)),
            lag_seconds=lag_seconds,
            cache_path=cache_path,
            snapshot_id=snapshot.snapshot_id,
            source_fingerprint=snapshot.source_fingerprint,
            index_fingerprint=snapshot.index_fingerprint,
            source_generation=snapshot.source_generation,
            completeness=snapshot.completeness,
            oracle_reason=snapshot.reason,
            action_version=ACTION_VERSION,
            access_mode="read_existing",
            hint=hint,
            agent_summary={
                "summary_line": (
                    "codegraph_status: index missing or empty"
                    if snapshot.reason == "MISSING_INDEX"
                    else (
                        f"codegraph_status: {snapshot.completeness} snapshot, "
                        f"{total_files} files, {total_symbols} symbols"
                    )
                ),
                "next_step": hint,
                "verdict": verdict,
            },
        )
        result.update(_storage_fields(stats))
        if stats.get("schema_version") is not None:
            result["schema_version"] = stats["schema_version"]
        return apply_toon_format_to_response(result, output_format)


def _storage_fields(stats: dict[str, Any] | None) -> dict[str, int]:
    if not stats:
        return {}
    fields: dict[str, int] = {}
    for key in _DB_STORAGE_KEYS:
        if key in stats and stats[key] is not None:
            fields[key] = int(stats[key])
    return fields
