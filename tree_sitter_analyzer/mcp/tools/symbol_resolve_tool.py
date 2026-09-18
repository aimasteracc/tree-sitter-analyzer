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
from ..utils.format_helper import apply_output_format_to_response
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
            "enum": ["json"],
            "default": "json",
            "description": "Output format: JSON",
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
                "[NICHE — prefer codegraph_navigate which combines this with "
                "callers/callees in ONE call.] "
                "Pure go-to-definition / find-all-references (CodeGraph parity). "
                "Use only when you specifically want JUST the definition or "
                "JUST the references, without the call hierarchy that "
                "codegraph_navigate adds. Supports qualified names "
                "(module.Class.method). Requires ast_cache index."
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
        return TOOL_SCHEMA

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("symbol"):
            raise ValueError("symbol is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        if self.project_root is None:
            raise ValueError("Project root not set. Call set_project_path first.")
        from ... import index_snapshot
        from ...api.pulse_evidence import PulseSourceError, certified_source_read

        try:
            with certified_source_read(self.project_root) as (owner, evidence):
                response = self._execute_resolve(
                    arguments, owner.query_cache(), evidence, owner.read_source
                )
                if not response.get("definitions"):
                    index_snapshot.verify_snapshot_source_current(
                        owner.snapshot, deadline=owner.deadline
                    )
                return response
        except PulseSourceError as exc:
            if not exc.allows_coordinate_fallback():
                response = exc.to_response("Symbol resolve")
                response.update(
                    verdict="ERROR",
                    symbol=arguments["symbol"],
                    mode=arguments.get("mode", "resolve"),
                    definition_count=0,
                    definitions=[],
                )
                if arguments.get("mode", "resolve") == "references":
                    response.update(reference_count=0, references=[])
                return response
            response = self._execute_resolve(
                arguments, self._get_cache(), exc.evidence(), None
            )
            response["source_evidence"] = exc.evidence()
            if response.get("success") is True:
                response["verdict"] = "WARN"
            if response.get("success") is True and not response.get("definitions"):
                response["next_step"] = (
                    "Build or synchronize the project index, then repeat nav.resolve."
                )
            return response

    def _execute_resolve(
        self,
        arguments: dict[str, Any],
        cache: Any,
        source_evidence: dict[str, Any],
        source_reader: Any,
    ) -> dict[str, Any]:
        """在指定 owner 连接上解析，并认证每个将要发布的位置。"""
        symbol = arguments["symbol"]
        mode = arguments.get("mode", "resolve")
        output_format = arguments.get("output_format", "json")
        conn = cache.get_conn()
        row_count = conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
        if row_count == 0:
            return apply_output_format_to_response(
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

        if source_reader is not None:
            paths = dict.fromkeys(
                [location.file for location in result.definitions]
                + [location.file for location in result.references]
            )
            for path in paths:
                source_reader(path)

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
            "source_evidence": source_evidence,
        }
        if mode == "references":
            response["reference_count"] = len(result.references)
            response["references"] = [r.to_dict() for r in result.references]

        if not result.definitions:
            response["hint"] = (
                f"No definitions found for '{symbol}'. "
                "Check spelling or build the AST cache with more files."
            )

        return apply_output_format_to_response(response, output_format)
