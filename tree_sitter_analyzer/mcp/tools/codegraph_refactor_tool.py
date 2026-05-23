#!/usr/bin/env python3
"""
CodeGraph Refactor MCP Tool — AST-aware symbol renaming.

Renames a function, class, method, or variable across the entire project
using the pre-indexed AST cache for instant symbol location. Performs
coordinated text replacement at all definition and reference sites.

Modes:
  - preview: Dry-run rename showing all sites that would change (default)
  - apply:   Execute the rename, writing all affected files

CodeGraph parity: equivalent to CodeGraph's "Rename Symbol" refactoring.
"""

from __future__ import annotations

from typing import Any

from ...rename_symbol import rename_symbol
from ...utils import setup_logger
from ..utils.auto_index_guard import ensure_indexed
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphRefactorTool(BaseMCPTool):
    """MCP Tool for AST-aware symbol renaming (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._cache = None

    def _get_cache(self) -> Any:
        if self._cache is not None:
            return self._cache
        cache = ensure_indexed(self.project_root)
        if cache is not None:
            self._cache = cache
        return self._cache

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_refactor",
            "description": (
                "AST-aware symbol renaming across the project (CodeGraph parity). "
                "Renames a function, class, method, or variable at all definition "
                "and reference sites using pre-indexed AST cache. "
                "Mode 'preview' shows what would change (safe, default). "
                "Mode 'apply' writes changes to disk. "
                "No other tool performs project-wide AST-aware renaming."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name to rename (function, class, method, or variable)",
                },
                "new_name": {
                    "type": "string",
                    "description": "New name for the symbol",
                },
                "mode": {
                    "type": "string",
                    "enum": ["preview", "apply"],
                    "default": "preview",
                    "description": (
                        "preview=dry-run showing affected sites (safe, default); "
                        "apply=write changes to disk"
                    ),
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                },
            },
            "required": ["symbol", "new_name"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        symbol = arguments.get("symbol", "").strip()
        new_name = arguments.get("new_name", "").strip()
        if not symbol:
            raise ValueError("symbol is required")
        if not new_name:
            raise ValueError("new_name is required")
        if symbol == new_name:
            raise ValueError("new_name must differ from symbol")
        if not all(c.isalnum() or c == "_" or c == "." for c in symbol):
            raise ValueError("symbol must be a valid identifier (alphanumeric, underscore, dots)")
        if not all(c.isalnum() or c == "_" for c in new_name):
            raise ValueError("new_name must be a valid identifier (alphanumeric, underscore)")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        symbol = arguments["symbol"].strip()
        new_name = arguments["new_name"].strip()
        mode = arguments.get("mode", "preview")
        output_format = arguments.get("output_format", "toon")
        dry_run = mode == "preview"

        cache = self._get_cache()
        if cache is None:
            return apply_toon_format_to_response(
                {
                    "success": False,
                    "error": (
                        "AST cache is empty. Run ast_cache mode=index first "
                        "to build the pre-indexed cache."
                    ),
                    "verdict": "ERROR",
                },
                output_format,
            )

        result = rename_symbol(
            cache=cache,
            old_name=symbol,
            new_name=new_name,
            dry_run=dry_run,
            project_root=self.project_root,
        )

        response: dict[str, Any] = {
            "success": True,
            "verdict": "DRY_RUN" if dry_run else ("OK" if not result.errors else "ERROR"),
        }
        response.update(result.to_dict())

        if dry_run and result.sites:
            files = sorted(set(s.file for s in result.sites))
            response["files_affected"] = files
            response["hint"] = (
                f"Would rename '{symbol}' → '{new_name}' at {result.sites_renamed or len(result.sites)} "
                f"sites across {len(files)} files. Use mode=apply to execute."
            )
        elif not dry_run and result.sites:
            response["hint"] = (
                f"Renamed '{symbol}' → '{new_name}': "
                f"{result.files_changed} files changed, "
                f"{result.sites_renamed} sites renamed."
            )

        from ..utils.format_helper import apply_toon_format_to_response
        return apply_toon_format_to_response(response, output_format)
