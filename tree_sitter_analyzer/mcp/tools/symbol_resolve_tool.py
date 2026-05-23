#!/usr/bin/env python3
"""
Symbol Resolve MCP Tool — Go-to-definition and find-all-references.

Resolves symbol names to their definition locations and finds all references
across the project using the pre-indexed AST cache. CodeGraph parity for
go-to-def navigation.

Modes:
  - resolve: Find where a symbol is defined (go-to-definition)
  - references: Find all usage sites + definition (find-all-references)
"""

from typing import Any

from ...symbol_resolver import SymbolResolver
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["resolve", "references"],
            "default": "resolve",
            "description": (
                "resolve=go-to-definition (find where symbol is defined), "
                "references=find-all-references (definition + all usage sites)"
            ),
        },
        "symbol": {
            "type": "string",
            "description": (
                "Symbol name to resolve. Supports: simple names (e.g. 'ASTCache'), "
                "dotted qualified names (e.g. 'ast_cache.ASTCache.index_file')"
            ),
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
            "description": "Output format: 'toon' (default, token-efficient) or 'json'",
        },
    },
    "required": ["symbol"],
    "additionalProperties": False,
}


class CodeGraphSymbolResolveTool(BaseMCPTool):
    """MCP Tool for CodeGraph go-to-definition and find-all-references."""

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._cache = None

    def _get_cache(self) -> Any:
        if self._cache is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            from ...ast_cache import ASTCache

            self._cache = ASTCache(self.project_root)
        return self._cache

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_resolve",
            "description": (
                "Go-to-definition and find-all-references (CodeGraph parity). "
                "Resolves symbol names to definition locations using pre-indexed AST cache. "
                "Supports qualified names (module.Class.method). "
                "Requires ast_cache index to be built first (run ast_cache mode=index). "
                "No other tool provides symbol definition resolution."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("symbol"):
            raise ValueError("symbol is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        symbol = arguments["symbol"]
        mode = arguments.get("mode", "resolve")
        output_format = arguments.get("output_format", "toon")

        cache = self._get_cache()
        conn = cache._get_conn()
        row_count = conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
        if row_count == 0:
            return apply_toon_format_to_response(
                {
                    "success": False,
                    "verdict": "ERROR",
                    "error": "AST cache is empty. Run ast_cache mode=index first.",
                    "hint": "Use codegraph_symbol_search or ast_cache mode=index to build the index.",
                    "symbol": symbol,
                },
                output_format,
            )

        resolver = SymbolResolver(cache)

        if mode == "references":
            result = resolver.find_references(symbol)
        else:
            result = resolver.resolve(symbol)

        # Pain #23 (dogfood pass 3): symbol_resolve emitted no verdict.
        # NOT_FOUND when no definitions are found (agents should stop chasing);
        # INFO otherwise.
        response: dict[str, Any] = {
            "success": True,
            "verdict": "INFO" if result.definitions else "NOT_FOUND",
            "symbol": result.symbol,
            "mode": mode,
            "definition_count": len(result.definitions),
            "definitions": [d.to_dict() for d in result.definitions],
            "resolved_via": result.resolved_via,
        }
        if mode == "references":
            response["reference_count"] = len(result.references)
            response["references"] = [r.to_dict() for r in result.references]

        if not result.definitions:
            response["hint"] = (
                f"No definitions found for '{symbol}'. "
                "Check spelling or build the AST cache with more files."
            )

        return apply_toon_format_to_response(response, output_format)
