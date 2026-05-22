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
from ...file_watcher import FileWatcherDaemon
from ...incremental_sync import IncrementalSync
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ASTCacheTool(BaseMCPTool):
    """MCP Tool for pre-indexed AST cache operations."""

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: ASTCache | None = None
        self._sync: IncrementalSync | None = None
        self._watcher: FileWatcherDaemon | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        if self._watcher is not None and self._watcher.is_running():
            self._watcher.stop()
        self._watcher = None
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

    def _get_watcher(
        self, poll_interval: float = 5.0, backend: str = "poll"
    ) -> FileWatcherDaemon:
        if self._watcher is None:
            self._watcher = FileWatcherDaemon(
                self._get_cache(),
                poll_interval=poll_interval,
                backend=backend,
            )
        return self._watcher

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "ast_cache",
            "description": (
                "Pre-indexed AST cache with FTS5 search, incremental sync, and file watcher "
                "(CodeGraph parity). Modes: "
                "index (index project or single file), "
                "lookup (get cached parse data for a file), "
                "search (FTS5 full-text symbol search across indexed files), "
                "fts_search (ranked FTS5 search with multi-term support), "
                "sync (incremental sync — detect changed/new/deleted files via content hash), "
                "changes (preview changes without re-indexing), "
                "watch_start (start background file watcher for auto-sync), "
                "watch_stop (stop file watcher), "
                "watch_status (watcher status and stats), "
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
                        "watch_start",
                        "watch_stop",
                        "watch_status",
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
                "poll_interval": {
                    "type": "number",
                    "description": "Watcher poll interval in seconds (default: 5.0)",
                },
                "backend": {
                    "type": "string",
                    "enum": ["poll", "watchdog"],
                    "description": "Watcher backend: poll (default) or watchdog",
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
            "watch_start",
            "watch_stop",
            "watch_status",
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
            else:
                max_files = arguments.get("max_files", 5000)
                force = arguments.get("force", False)
                result = cache.index_project(max_files=max_files, force=force)
            return {"success": True, "mode": "index", "verdict": "INFO", **result}

        elif mode == "lookup":
            file_path = arguments.get("file_path", "")
            resolved = self.resolve_and_validate_file_path(file_path)
            result = cache.lookup(resolved)
            if result is None:
                return {
                    "success": True,
                    "file": file_path,
                    "status": "not_found",
                    "verdict": "NOT_FOUND",
                }
            return {"success": True, "mode": "lookup", "verdict": "INFO", **result}

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
                "verdict": "INFO" if results else "NOT_FOUND",
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
                "verdict": "INFO" if results else "NOT_FOUND",
            }

        elif mode == "stats":
            return {
                "success": True,
                "mode": "stats",
                "verdict": "INFO",
                **cache.get_stats(),
            }

        elif mode == "sync":
            sync_engine = self._get_sync()
            max_files = arguments.get("max_files", 5000)
            sync_result = sync_engine.sync(max_files=max_files)
            return {
                "success": True,
                "mode": "sync",
                "verdict": "INFO",
                **sync_result.to_dict(),
            }

        elif mode == "changes":
            sync_engine = self._get_sync()
            changes = sync_engine.get_changes()
            total = sum(len(v) for v in changes.values())
            return {
                "success": True,
                "mode": "changes",
                "new_count": len(changes["new"]),
                "modified_count": len(changes["modified"]),
                "deleted_count": len(changes["deleted"]),
                "total_changes": total,
                "changes": changes,
                "verdict": "INFO",
            }

        elif mode == "invalidate":
            file_path = arguments.get("file_path", "")
            resolved = self.resolve_and_validate_file_path(file_path)
            removed = cache.invalidate(resolved)
            return {
                "success": True,
                "file": file_path,
                "invalidated": removed,
                "verdict": "INFO",
            }

        elif mode == "watch_start":
            poll_interval = arguments.get("poll_interval", 5.0)
            backend = arguments.get("backend", "poll")
            watcher = self._get_watcher(
                poll_interval=float(poll_interval), backend=backend
            )
            if watcher.is_running():
                return {
                    "success": True,
                    "mode": "watch_start",
                    "status": "already_running",
                    "stats": watcher.get_stats(),
                    "verdict": "INFO",
                }
            watcher.start()
            return {
                "success": True,
                "mode": "watch_start",
                "status": "started",
                "backend": backend,
                "poll_interval": poll_interval,
                "stats": watcher.get_stats(),
                "verdict": "INFO",
            }

        elif mode == "watch_stop":
            if self._watcher is None or not self._watcher.is_running():
                return {
                    "success": True,
                    "mode": "watch_stop",
                    "status": "not_running",
                    "verdict": "INFO",
                }
            final_stats = self._watcher.get_stats()
            self._watcher.stop()
            return {
                "success": True,
                "mode": "watch_stop",
                "status": "stopped",
                "final_stats": final_stats,
                "verdict": "INFO",
            }

        elif mode == "watch_status":
            if self._watcher is None:
                return {
                    "success": True,
                    "mode": "watch_status",
                    "running": False,
                    "watcher_created": False,
                    "verdict": "INFO",
                }
            return {
                "success": True,
                "mode": "watch_status",
                "running": self._watcher.is_running(),
                "watcher_created": True,
                "stats": self._watcher.get_stats(),
                "verdict": "INFO",
            }

        return {"success": False, "error": f"Unknown mode: {mode}", "verdict": "ERROR"}
