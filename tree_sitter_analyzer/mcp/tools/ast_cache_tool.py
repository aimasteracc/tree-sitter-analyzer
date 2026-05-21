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
from ...incremental_sync import IncrementalSync
from ...utils import setup_logger
from .base_tool import BaseMCPTool, mirror_summary_line

logger = setup_logger(__name__)


def _build_ast_cache_envelope(
    mode: str,
    payload: dict[str, Any],
    summary_line: str,
    next_step: str,
) -> dict[str, Any]:
    """Wrap an ast_cache mode's raw payload in the canonical envelope.

    H5: every mode previously returned ``{"success": True, "mode": ..., **payload}``
    with no ``summary_line`` and no ``agent_summary`` — callers had to
    guess at the headline. This helper builds both, mirrors the
    summary_line to the top level (so the dispatch post-hook stays a
    no-op for direct ``await tool.execute(args)`` callers too), and
    leaves the raw payload keys exactly where they were.
    """
    response: dict[str, Any] = {
        "success": True,
        "mode": mode,
        **payload,
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": next_step,
            "verdict": "n/a",
        },
    }
    return mirror_summary_line(response)


class ASTCacheTool(BaseMCPTool):
    """MCP Tool for pre-indexed AST cache operations."""

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: ASTCache | None = None
        self._sync: IncrementalSync | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._cache = None
        self._sync = None

    def _get_cache(self) -> ASTCache:
        if self._cache is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            self._cache = ASTCache(self.project_root)
        return self._cache

    def _get_sync(self) -> IncrementalSync:
        if self._sync is None:
            self._sync = IncrementalSync(self._get_cache())
        return self._sync

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "ast_cache",
            "description": (
                "Pre-indexed AST cache with FTS5 search and incremental sync (CodeGraph parity). Modes: "
                "index (index project or single file), "
                "lookup (get cached parse data for a file), "
                "search (FTS5 full-text symbol search across indexed files), "
                "fts_search (ranked FTS5 search with multi-term support), "
                "sync (incremental sync — detect changed/new/deleted files via content hash), "
                "changes (preview changes without re-indexing), "
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
                    "enum": [
                        "index",
                        "lookup",
                        "search",
                        "fts_search",
                        "sync",
                        "changes",
                        "stats",
                        "invalidate",
                    ],
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
        valid_modes = {
            "index",
            "lookup",
            "search",
            "fts_search",
            "sync",
            "changes",
            "stats",
            "invalidate",
        }
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
                indexed_files = int(result.get("indexed", result.get("count", 1)) or 0)
                symbols = int(result.get("symbol_count", result.get("symbols", 0)) or 0)
                summary_line = f"ast_cache index file={file_path} symbols={symbols}"
                next_step = (
                    f"ast_cache mode=lookup file_path={file_path!r} "
                    "to retrieve the cached entry"
                )
            else:
                max_files = arguments.get("max_files", 5000)
                force = arguments.get("force", False)
                result = cache.index_project(max_files=max_files, force=force)
                indexed_files = int(
                    result.get("indexed", result.get("files_indexed", 0)) or 0
                )
                symbols = int(result.get("symbol_count", result.get("symbols", 0)) or 0)
                summary_line = (
                    f"ast_cache index project files={indexed_files} "
                    f"symbols={symbols} force={bool(force)}"
                )
                next_step = "ast_cache mode=stats to confirm the index size"
            return _build_ast_cache_envelope("index", result, summary_line, next_step)

        elif mode == "lookup":
            file_path = arguments.get("file_path", "")
            resolved = self.resolve_and_validate_file_path(file_path)
            result = cache.lookup(resolved)
            if result is None:
                summary_line = f"ast_cache lookup file={file_path} status=not_found"
                next_step = f"ast_cache mode=index file_path={file_path!r} to populate the cache"
                return _build_ast_cache_envelope(
                    "lookup",
                    {"file": file_path, "status": "not_found"},
                    summary_line,
                    next_step,
                )
            symbol_count = int(
                (result.get("symbol_count") if isinstance(result, dict) else 0) or 0
            )
            summary_line = f"ast_cache lookup file={file_path} symbols={symbol_count}"
            next_step = (
                "analyze_code_structure on this file for an interactive table view"
            )
            return _build_ast_cache_envelope("lookup", result, summary_line, next_step)

        elif mode == "search":
            query = arguments.get("query", "")
            language = arguments.get("language")
            results = cache.search_symbols(query, language=language)
            summary_line = f"ast_cache search query={query!r} results={len(results)}"
            next_step = (
                "ast_cache mode=fts_search for ranked full-text matching"
                if len(results) == 0
                else "ast_cache mode=lookup file_path=<result.file> for full entry"
            )
            return _build_ast_cache_envelope(
                "search",
                {
                    "query": query,
                    "results": results,
                    "count": len(results),
                },
                summary_line,
                next_step,
            )

        elif mode == "fts_search":
            query = arguments.get("query", "")
            language = arguments.get("language")
            limit = arguments.get("limit", 100)
            results = cache.fts_search(query, language=language, limit=limit)
            summary_line = (
                f"ast_cache fts_search query={query!r} "
                f"results={len(results)} fts5={cache._fts5_available}"
            )
            next_step = (
                "ast_cache mode=lookup file_path=<result.file> for the full entry"
                if results
                else "ast_cache mode=index to build the FTS index first"
            )
            return _build_ast_cache_envelope(
                "fts_search",
                {
                    "query": query,
                    "results": results,
                    "count": len(results),
                    "fts5_available": cache._fts5_available,
                },
                summary_line,
                next_step,
            )

        elif mode == "stats":
            stats = cache.get_stats()
            total_files = int(stats.get("total_files", 0) or 0)
            total_symbols = int(stats.get("total_symbols", 0) or 0)
            fts5_available = bool(stats.get("fts5_available", False))
            summary_line = (
                f"ast_cache stats files={total_files} "
                f"symbols={total_symbols} fts5={fts5_available}"
            )
            if total_files == 0:
                next_step = "ast_cache mode=index to populate the cache"
            else:
                next_step = "ast_cache mode=fts_search query=<symbol> to find a symbol"
            return _build_ast_cache_envelope("stats", stats, summary_line, next_step)

        elif mode == "sync":
            sync_engine = self._get_sync()
            max_files = arguments.get("max_files", 5000)
            sync_result = sync_engine.sync(max_files=max_files)
            sync_dict = sync_result.to_dict()
            added = int(sync_dict.get("added", sync_dict.get("new", 0)) or 0)
            modified = int(sync_dict.get("modified", 0) or 0)
            deleted = int(sync_dict.get("deleted", 0) or 0)
            summary_line = (
                f"ast_cache sync added={added} modified={modified} deleted={deleted}"
            )
            next_step = (
                "ast_cache mode=stats to confirm the new cache size"
                if (added + modified + deleted) > 0
                else "no changes — re-run sync after next edit"
            )
            return _build_ast_cache_envelope("sync", sync_dict, summary_line, next_step)

        elif mode == "changes":
            sync_engine = self._get_sync()
            changes = sync_engine.get_changes()
            total = sum(len(v) for v in changes.values())
            summary_line = (
                f"ast_cache changes new={len(changes['new'])} "
                f"modified={len(changes['modified'])} "
                f"deleted={len(changes['deleted'])} total={total}"
            )
            next_step = (
                "ast_cache mode=sync to apply these changes"
                if total > 0
                else "no changes pending"
            )
            return _build_ast_cache_envelope(
                "changes",
                {
                    "new_count": len(changes["new"]),
                    "modified_count": len(changes["modified"]),
                    "deleted_count": len(changes["deleted"]),
                    "total_changes": total,
                    "changes": changes,
                },
                summary_line,
                next_step,
            )

        elif mode == "invalidate":
            file_path = arguments.get("file_path", "")
            resolved = self.resolve_and_validate_file_path(file_path)
            removed = cache.invalidate(resolved)
            summary_line = (
                f"ast_cache invalidate file={file_path} removed={bool(removed)}"
            )
            next_step = (
                "ast_cache mode=index file_path=<path> to re-index"
                if removed
                else "no cache entry to invalidate"
            )
            return _build_ast_cache_envelope(
                "invalidate",
                {"file": file_path, "invalidated": removed},
                summary_line,
                next_step,
            )

        # Unknown mode — fall through to the canonical error envelope.
        summary_line = f"ast_cache: unknown mode={mode!r}"
        return mirror_summary_line(
            {
                "success": False,
                "mode": mode,
                "error": f"Unknown mode: {mode}",
                "summary_line": summary_line,
                "agent_summary": {
                    "summary_line": summary_line,
                    "next_step": (
                        "ast_cache mode=stats — see the tool schema for valid modes"
                    ),
                    "verdict": "INVALID_INPUT",
                },
            }
        )
