#!/usr/bin/env python3
"""
CodeGraph Cross-Reference MCP Tool — Instant multi-dimension symbol lookup.

Combines definitions, callers, callees, import dependents, and file-level
blast radius into a single cache-backed query. No re-parsing.

Modes:
  - symbol: Full cross-ref for a named symbol (function/class/variable)
  - file:   Full cross-ref for a file (all symbols, deps, dependents)

CodeGraph parity: equivalent to CodeGraph's "xref" / "find all references"
with added call-graph and import-graph dimensions.
"""

from __future__ import annotations

from typing import Any

from ...utils import setup_logger
from ...xref import XRefEngine
from ..utils.format_helper import apply_toon_format_to_response
from ._response_builder import build_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphXRefTool(BaseMCPTool):
    """MCP Tool for instant cross-reference queries (CodeGraph parity)."""

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
            "name": "codegraph_xref",
            "description": (
                "Instant multi-dimension cross-reference from pre-indexed AST cache "
                "(CodeGraph parity). For a symbol: definition + callers + callees + "
                "import dependents + file blast radius. For a file: all symbols + deps. "
                "Requires ast_cache index (run ast_cache mode=index). "
                "No other tool provides unified cross-file cross-reference."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["symbol", "file"],
                    "default": "symbol",
                    "description": (
                        "symbol=full xref for a named symbol, "
                        "file=full xref for a file path"
                    ),
                },
                "symbol": {
                    "type": "string",
                    "description": "Symbol name (for mode=symbol)",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path to disambiguate (symbol mode) or target (file mode)",
                },
                "include_callers": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include who calls this symbol",
                },
                "include_callees": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include what this symbol calls",
                },
                "include_imports": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include import dependents",
                },
                "include_file_deps": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include file-level blast radius",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": "Output format",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "symbol")
        if mode not in ("symbol", "file"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'symbol' or 'file'")
        if mode == "symbol" and not arguments.get("symbol"):
            raise ValueError("symbol is required for mode=symbol")
        if mode == "file" and not arguments.get("file_path"):
            raise ValueError("file_path is required for mode=file")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        mode = arguments.get("mode", "symbol")
        output_format = arguments.get("output_format", "toon")
        cache = self._get_cache()
        engine = XRefEngine(cache)

        if mode == "file":
            file_path = arguments.get("file_path", "")
            file_result = engine.file_xref(file_path)
            verdict = "INFO" if file_result.get("symbol_count", 0) > 0 else "NOT_FOUND"
            # build_response prepends success+verdict; remaining file_xref
            # payload merges in via **kwargs preserving every existing key.
            result = build_response(verdict=verdict, mode="file", **file_result)
        else:
            symbol = arguments.get("symbol", "")
            file_path = arguments.get("file_path")
            include_callers = arguments.get("include_callers", True)
            include_callees = arguments.get("include_callees", True)
            include_imports = arguments.get("include_imports", True)
            include_file_deps = arguments.get("include_file_deps", True)

            xref_result = engine.xref(
                symbol,
                file_path,
                include_callers=include_callers,
                include_callees=include_callees,
                include_imports=include_imports,
                include_file_deps=include_file_deps,
            )
            xref_dict = xref_result.to_dict()
            has_data = bool(
                xref_result.definitions or xref_result.callers or xref_result.callees
            )
            verdict = "INFO" if has_data else "NOT_FOUND"
            result = build_response(verdict=verdict, mode="symbol", **xref_dict)

        return apply_toon_format_to_response(result, output_format)
