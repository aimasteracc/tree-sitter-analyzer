#!/usr/bin/env python3
"""保守的 Python 函数、类及直接导入重命名工具。"""

from __future__ import annotations

from typing import Any

from ...rename_symbol import rename_symbol
from ...utils import setup_logger
from ..utils.auto_index_guard import ensure_indexed
from ..utils.format_helper import apply_output_format_to_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphRefactorTool(BaseMCPTool):
    """MCP Tool for AST-aware symbol renaming (CodeGraph parity)."""

    #: When set, ``mode`` is taken from here and the caller's value is ignored
    #: entirely. RFC-0027 §L8's ``edit action=plan_rename`` binding sets it to
    #: ``"preview"`` so a planning surface cannot be talked into writing. It is
    #: a class attribute rather than an injected argument so the pin survives
    #: the strict-parameter guard and shows up in the subclass definition.
    FORCED_MODE: str | None = None

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
                "Rename a unique Python module-level function or class and its direct imports. "
                "Fresh AST identifier locations preserve literals and comments. "
                "Unsupported languages and ambiguous bindings fail closed. "
                "Mode preview is read-only; mode apply writes validated changes."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Unqualified Python module-level function or class name to rename",
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
                    "enum": ["json"],
                    "default": "json",
                    "description": "Output format: JSON",
                },
            },
            "required": ["symbol", "new_name"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = self.FORCED_MODE or arguments.get("mode", "preview")
        if mode not in ("preview", "apply"):
            raise ValueError("mode must be preview or apply")
        symbol = arguments.get("symbol", "").strip()
        new_name = arguments.get("new_name", "").strip()
        if not symbol:
            raise ValueError("symbol is required")
        if not new_name:
            raise ValueError("new_name is required")
        if symbol == new_name:
            raise ValueError("new_name must differ from symbol")
        if not all(c.isalnum() or c == "_" or c == "." for c in symbol):
            raise ValueError(
                "symbol must be a valid identifier (alphanumeric, underscore, dots)"
            )
        if not all(c.isalnum() or c == "_" for c in new_name):
            raise ValueError(
                "new_name must be a valid identifier (alphanumeric, underscore)"
            )
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        symbol = arguments["symbol"].strip()
        new_name = arguments["new_name"].strip()
        mode = self.FORCED_MODE or arguments.get("mode", "preview")
        output_format = arguments.get("output_format", "json")
        dry_run = mode == "preview"

        cache = self._get_cache()
        if cache is None:
            return apply_output_format_to_response(
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

        # PM-fix (post-mcp-builder audit): map non-canonical verdicts to
        # _LEGAL_VERDICTS. "DRY_RUN" → INFO (informational preview),
        # "OK" → INFO (rename succeeded), "ERROR" stays.
        if result.errors:
            verdict = "ERROR"
        elif dry_run:
            verdict = "INFO"  # preview-only, no state change
        else:
            verdict = "INFO"  # rename applied successfully
        response: dict[str, Any] = {"success": not result.errors, "verdict": verdict}
        response.update(result.to_dict())

        if not result.errors and dry_run and result.sites:
            files = sorted({s.file for s in result.sites})
            response["files_affected"] = files
            response["hint"] = (
                f"Would rename '{symbol}' → '{new_name}' at {result.sites_renamed or len(result.sites)} "
                f"sites across {len(files)} files. Use mode=apply to execute."
            )
        elif not result.errors and not dry_run and result.sites:
            response["hint"] = (
                f"Renamed '{symbol}' → '{new_name}': "
                f"{result.files_changed} files changed, "
                f"{result.sites_renamed} sites renamed."
            )

        return apply_output_format_to_response(response, output_format)
