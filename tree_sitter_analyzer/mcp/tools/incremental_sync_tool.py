#!/usr/bin/env python3
"""
CodeGraph Incremental Sync MCP Tool — Content-hash diff re-indexing.

Exposes the IncrementalSync engine as an MCP tool so agents can trigger
smart re-indexing that only parses files whose content hash changed.
Supports three modes:

  - sync:     Full incremental sync (detect new/modified/deleted, re-index)
  - changes:  Preview mode — lists changes without re-indexing
  - status:   Report current sync state (indexed files vs on-disk files)
"""

from __future__ import annotations

from typing import Any

from ...incremental_sync import IncrementalSync
from ...utils import setup_logger
from ..utils.auto_index_guard import ensure_indexed, is_indexed
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool


def _build_error(error: str) -> dict[str, Any]:
    return {"success": False, "verdict": "ERROR", "error": error}


def _build_response(verdict: str, **kwargs: Any) -> dict[str, Any]:
    return {"success": True, "verdict": verdict, **kwargs}


logger = setup_logger(__name__)


class CodeGraphIncrementalSyncTool(BaseMCPTool):
    """MCP Tool for incremental AST cache sync (CodeGraph parity)."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_incremental_sync",
            "description": (
                "Incremental AST cache sync using content-hash comparison "
                "(CodeGraph parity). Modes: "
                "sync (detect + re-index changed files), "
                "changes (preview only, no re-index), "
                "status (indexed vs on-disk file counts). "
                "Only re-parses files whose SHA-256 hash differs. "
                "No other tool provides incremental sync."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["sync", "changes", "status"],
                    "description": "Operation mode (default: sync)",
                    "default": "sync",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Max files to scan (default: 5000)",
                    "default": 5000,
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
        mode = arguments.get("mode", "sync")
        if mode not in ("sync", "changes", "status"):
            raise ValueError(f"Invalid mode: {mode}")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        mode = arguments.get("mode", "sync")
        output_format = arguments.get("output_format", "toon")

        if not self.project_root:
            result = _build_error(error="project_root not set")
            return apply_toon_format_to_response(result, output_format)

        if mode == "sync":
            return self._sync(arguments.get("max_files", 5000), output_format)
        elif mode == "changes":
            return self._changes(output_format)
        elif mode == "status":
            return self._status(output_format)

        return _build_error(error=f"Unknown mode: {mode}")

    def _ensure_cache(self, output_format: str) -> Any | None:
        if not is_indexed(str(self.project_root)):
            cache = ensure_indexed(str(self.project_root))
            if cache is None:
                return None
            return cache
        from ...ast_cache import ASTCache

        return ASTCache(str(self.project_root))

    def _sync(self, max_files: int, output_format: str) -> dict[str, Any]:
        cache = self._ensure_cache(output_format)
        if cache is None:
            result = _build_error(error="Failed to initialize AST cache")
            return apply_toon_format_to_response(result, output_format)

        sync = IncrementalSync(cache)
        try:
            sync_result = sync.sync(max_files=max_files)
        except Exception as exc:
            result = _build_error(error=f"Sync failed: {exc}")
            return apply_toon_format_to_response(result, output_format)

        result = _build_response(
            verdict="INFO",
            project_root=self.project_root,
            mode="sync",
            **sync_result.to_dict(),
        )
        return apply_toon_format_to_response(result, output_format)

    def _changes(self, output_format: str) -> dict[str, Any]:
        cache = self._ensure_cache(output_format)
        if cache is None:
            result = _build_error(error="Failed to initialize AST cache")
            return apply_toon_format_to_response(result, output_format)

        sync = IncrementalSync(cache)
        try:
            changes = sync.get_changes()
        except Exception as exc:
            result = _build_error(error=f"Change detection failed: {exc}")
            return apply_toon_format_to_response(result, output_format)

        new_count = len(changes.get("new", []))
        modified_count = len(changes.get("modified", []))
        deleted_count = len(changes.get("deleted", []))

        result = _build_response(
            verdict="INFO",
            project_root=self.project_root,
            mode="changes",
            new_files=new_count,
            modified_files=modified_count,
            deleted_files=deleted_count,
            new=changes.get("new", []),
            modified=changes.get("modified", []),
            deleted=changes.get("deleted", []),
        )
        return apply_toon_format_to_response(result, output_format)

    def _status(self, output_format: str) -> dict[str, Any]:
        from ...ast_cache import ASTCache

        cache = ASTCache(str(self.project_root))
        stats = cache.get_stats()

        try:
            sync = IncrementalSync(cache)
            changes = sync.get_changes()
            pending_changes = (
                len(changes.get("new", []))
                + len(changes.get("modified", []))
                + len(changes.get("deleted", []))
            )
        except Exception:
            pending_changes = -1
            changes = {}

        up_to_date = pending_changes == 0 if pending_changes >= 0 else None

        result = _build_response(
            verdict="INFO",
            project_root=self.project_root,
            mode="status",
            indexed_files=stats.get("total_files", 0),
            total_symbols=stats.get("total_symbols", 0),
            fts5_available=stats.get("fts5_available", False),
            pending_changes=pending_changes,
            up_to_date=up_to_date,
        )
        return apply_toon_format_to_response(result, output_format)
