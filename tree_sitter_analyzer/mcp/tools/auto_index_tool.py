#!/usr/bin/env python3
"""
CodeGraph Auto-Index MCP Tool — Transparent cache warming.

Gives agents explicit control over the auto-index guard that other
codegraph tools (callers, callees, symbol_search, metrics, etc.) use
internally.

Modes:
  - status: Check if project is indexed and cache state
  - warm:   Trigger auto-index (idempotent — no-op if already warm)
  - reset:  Force re-index on next access
"""

from __future__ import annotations

from typing import Any

from ...utils import setup_logger
from ..utils.auto_index_guard import (
    ensure_indexed,
    is_indexed,
    mark_dirty,
)
from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_error, build_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphAutoIndexTool(BaseMCPTool):
    """MCP Tool for transparent AST cache warming (CodeGraph parity)."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_autoindex",
            "description": (
                "Transparent AST cache auto-indexing (CodeGraph parity). "
                "Modes: "
                "status (check index state), "
                "warm (trigger index — idempotent), "
                "reset (force re-index on next access). "
                "Other codegraph tools auto-warm on first call; "
                "this tool gives explicit control. "
                "No other tool manages auto-index lifecycle."
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
                    "enum": ["status", "warm", "reset"],
                    "description": "Operation mode (default: status)",
                    "default": "status",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Max files to index when warming (default: 20000)",
                    "default": 20000,
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
        mode = arguments.get("mode", "status")
        if mode not in ("status", "warm", "reset"):
            raise ValueError(f"Invalid mode: {mode}")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        mode = arguments.get("mode", "status")
        output_format = arguments.get("output_format", "toon")

        if mode == "status":
            return self._status(output_format)
        elif mode == "warm":
            return self._warm(arguments.get("max_files", 20_000), output_format)
        elif mode == "reset":
            return self._reset(output_format)

        return build_error(error=f"Unknown mode: {mode}")

    def _status(self, output_format: str) -> dict[str, Any]:
        if not self.project_root:
            result = build_response(
                verdict="WARN",
                indexed=False,
                reason="project_root not set",
            )
            return apply_toon_format_to_response(result, output_format)

        indexed = is_indexed(self.project_root)
        cache_stats = None
        if indexed:
            try:
                from ...ast_cache import ASTCache

                cache = ASTCache(self.project_root)
                cache_stats = cache.get_stats()
            except Exception:
                pass

        result = build_response(
            verdict="INFO",
            project_root=self.project_root,
            indexed=indexed,
            cache_stats=cache_stats,
        )
        return apply_toon_format_to_response(result, output_format)

    def _warm(self, max_files: int, output_format: str) -> dict[str, Any]:
        # The two failure branches below historically returned a
        # ``reason`` key instead of ``error``. We keep that shape to stay
        # back-compatible with anyone branching on ``reason``; the
        # envelope still passes through build_response so the verdict is
        # validated. (Migrating to ``error`` would be a behaviour change
        # — out of scope for the factory rollout.)
        if not self.project_root:
            result = build_response(
                verdict="ERROR",
                success=False,
                reason="project_root not set",
            )
            return apply_toon_format_to_response(result, output_format)

        cache = ensure_indexed(self.project_root, max_files=max_files)
        if cache is None:
            result = build_response(
                verdict="ERROR",
                success=False,
                reason="auto-index failed",
            )
            return apply_toon_format_to_response(result, output_format)

        stats = cache.get_stats()
        result = build_response(
            verdict="INFO",
            project_root=self.project_root,
            indexed=True,
            cache_stats=stats,
        )
        return apply_toon_format_to_response(result, output_format)

    def _reset(self, output_format: str) -> dict[str, Any]:
        if self.project_root:
            mark_dirty(self.project_root)
        result = build_response(
            verdict="INFO",
            project_root=self.project_root,
            action="reset",
        )
        return apply_toon_format_to_response(result, output_format)
