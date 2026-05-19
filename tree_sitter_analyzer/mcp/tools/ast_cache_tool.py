#!/usr/bin/env python3
"""
AST Cache MCP Tool — Pre-indexed persistent AST cache.

Exposes SQLite-backed parse result storage via MCP protocol.
Modes: index (index project or file), lookup (get cached data),
search (search symbols), stats (cache statistics), invalidate (remove entry).

CodeGraph parity: equivalent to CodeGraph's pre-indexed code intelligence.
"""

from typing import Any

from ...ast_cache import ASTCache
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ASTCacheTool(BaseMCPTool):
    """MCP Tool for pre-indexed AST cache operations."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self._cache: ASTCache | None = None

    def set_project_path(self, project_path: str) -> None:
        super().set_project_path(project_path)
        self._cache = None

    def _get_cache(self) -> ASTCache:
        if self._cache is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            self._cache = ASTCache(self.project_root)
        return self._cache

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "ast_cache",
            "description": (
                "Pre-indexed AST cache with FTS5 full-text search (CodeGraph parity). Modes: "
                "index (index project or single file), "
                "lookup (get cached parse data for a file), "
                "search (FTS5 full-text symbol search across indexed files), "
                "fts_search (ranked FTS5 search with multi-term support), "
                "stats (cache statistics), "
                "invalidate (remove cached entry). "
                "No other tool provides persistent cross-session AST caching."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["index", "lookup", "search", "fts_search", "stats", "invalidate"],
                    "description": "Operation mode",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path (for lookup, index single file, invalidate)",
                },
                "language": {
                    "type": "string",
                    "description": "Language filter (optional, for search/fts_search)",
                },
                "query": {
                    "type": "string",
                    "description": "Symbol search query (for search/fts_search mode)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results for fts_search (default: 100)",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Max files to index (default: 5000)",
                },
                "force": {
                    "type": "boolean",
                    "description": "Force full re-index (default: false)",
                },
            },
            "required": ["mode"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "stats")
        valid_modes = {"index", "lookup", "search", "fts_search", "stats", "invalidate"}
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {valid_modes}")
        if mode in ("lookup", "invalidate") and not arguments.get("file_path"):
            raise ValueError(f"file_path is required for mode '{mode}'")
        if mode in ("search", "fts_search") and not arguments.get("query"):
            raise ValueError(f"query is required for {mode} mode")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        mode = arguments.get("mode", "stats")
        cache = self._get_cache()

        if mode == "index":
            file_path = arguments.get("file_path")
            if file_path:
                resolved = self.resolve_and_validate_file_path(file_path)
                result = cache.index_file(resolved)
            else:
                max_files = arguments.get("max_files", 5000)
                force = arguments.get("force", False)
                result = cache.index_project(max_files=max_files, force=force)
            return {"success": True, "mode": "index", **result}

        elif mode == "lookup":
            file_path = arguments.get("file_path", "")
            resolved = self.resolve_and_validate_file_path(file_path)
            result = cache.lookup(resolved)
            if result is None:
                return {"success": True, "file": file_path, "status": "not_found"}
            return {"success": True, "mode": "lookup", **result}

        elif mode == "search":
            query = arguments.get("query", "")
            language = arguments.get("language")
            results = cache.search_symbols(query, language=language)
            return {
                "success": True,
                "mode": "search",
                "query": query,
                "results": results,
                "count": len(results),
            }

        elif mode == "fts_search":
            query = arguments.get("query", "")
            language = arguments.get("language")
            limit = arguments.get("limit", 100)
            results = cache.fts_search(query, language=language, limit=limit)
            return {
                "success": True,
                "mode": "fts_search",
                "query": query,
                "results": results,
                "count": len(results),
                "fts5_available": cache._fts5_available,
            }

        elif mode == "stats":
            return {"success": True, "mode": "stats", **cache.get_stats()}

        elif mode == "invalidate":
            file_path = arguments.get("file_path", "")
            resolved = self.resolve_and_validate_file_path(file_path)
            removed = cache.invalidate(resolved)
            return {"success": True, "file": file_path, "invalidated": removed}

        return {"success": False, "error": f"Unknown mode: {mode}"}
