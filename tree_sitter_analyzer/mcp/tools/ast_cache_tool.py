#!/usr/bin/env python3
"""
AST Cache MCP Tool — Pre-indexed persistent AST cache.

Exposes SQLite-backed parse result storage via MCP protocol.
Modes: index (index project or file), lookup (get cached data),
search (search symbols), stats (cache statistics), invalidate (remove entry).

CodeGraph parity: equivalent to CodeGraph's pre-indexed code intelligence.
"""

import os
import re
import threading
from dataclasses import dataclass
from typing import Any

from ...ast_cache import ASTCache
from ...file_watcher import FileWatcherDaemon
from ...incremental_sync import IncrementalSync
from ...indexing_limits import normalize_index_max_files
from ...utils import setup_logger
from ._validators import invalid_enum_error
from .base_tool import BaseMCPTool, _canonicalize_verdict, mirror_summary_line

logger = setup_logger(__name__)

# K7: read-time defensive split for legacy ``kind=import`` rows where the
# ``name`` field still carries the entire ``from X import (A, B, C)``
# block. Fresh indices already emit one row per bound identifier (see
# ``ast_cache._walk_for_symbols``); this guard only kicks in when the
# user has an older DB and avoids forcing a full re-index for a quirk
# that would otherwise confuse FTS callers.
_IMPORT_NAME_LIMIT = 100
_BOUND_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class _WatchStartup:
    """一次 watcher 启动的精确所有权预约。"""

    raw_root: str | None
    token: Any
    cache: ASTCache | None = None
    daemon: FileWatcherDaemon | None = None
    starting: bool = True
    retired: bool = False
    authorized: bool = False


_IMPORT_KEYWORDS = frozenset(
    {
        "from",
        "import",
        "as",
        "use",
        "include",
        "package",
        "require",
        "pub",
        "self",
        "crate",
        "noqa",
        "F401",
    }
)


def _split_legacy_import_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one row per bound identifier when ``row['name']`` holds a
    multi-line / multi-symbol import block; otherwise return ``[row]``.

    K7: defensive shim for legacy ``.ast-cache`` databases that were
    written before the indexer learned to split imports. ``name`` length
    is the trigger — clean rows already cap at a single identifier.
    """
    if row.get("kind") != "import":
        return [row]
    name = row.get("name", "")
    if not isinstance(name, str) or len(name) <= _IMPORT_NAME_LIMIT:
        return [row]

    # Extract bound identifiers from the raw block. We honour the
    # ``X as Y`` alias rule by preferring the identifier after ``as``.
    bound: list[str] = []
    seen: set[str] = set()
    tokens = _BOUND_NAME_PATTERN.findall(name)
    skip_next = False  # set when we just consumed an ``as`` keyword
    for idx, tok in enumerate(tokens):
        if tok in _IMPORT_KEYWORDS:
            continue
        if skip_next:
            skip_next = False
            continue
        # ``A as B`` — emit B, swallow A's slot via lookahead.
        if idx + 1 < len(tokens) and tokens[idx + 1] == "as":
            alias = tokens[idx + 2] if idx + 2 < len(tokens) else ""
            if alias and alias not in seen:
                seen.add(alias)
                bound.append(alias)
            skip_next = True  # skip the ``as`` token next iteration
            continue
        if tok in seen:
            continue
        seen.add(tok)
        bound.append(tok)

    if not bound:
        # Couldn't identify any bound names — truncate to keep the row
        # scannable and return it as a single entry.
        compact = name.replace("\n", " ")[:_IMPORT_NAME_LIMIT]
        new_row = dict(row)
        new_row["name"] = compact
        return [new_row]

    split_rows: list[dict[str, Any]] = []
    for n in bound:
        new_row = dict(row)
        new_row["name"] = n
        split_rows.append(new_row)
    return split_rows


def _apply_legacy_import_split(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply ``_split_legacy_import_row`` across an FTS result list."""
    cleaned: list[dict[str, Any]] = []
    for row in results:
        cleaned.extend(_split_legacy_import_row(row))
    return cleaned


def _build_unknown_mode_response(mode: str) -> dict[str, Any]:
    """Canonical INVALID_INPUT envelope for unknown ``mode=`` values."""
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
    # F1 (round-37f7): ast_cache modes are informational (stats /
    # lookup / search). They have no analysis result to gate on, so
    # the canonical verdict is ``INFO`` from the shared vocabulary —
    # not the legacy ``"n/a"`` sentinel which lives outside
    # :data:`_LEGAL_VERDICTS`.
    canonical_verdict = _canonicalize_verdict("n/a")  # → "INFO"
    response: dict[str, Any] = {
        "success": True,
        "mode": mode,
        **payload,
        "summary_line": summary_line,
        # r37x (envelope ratchet): top-level verdict mirror (r37u contract).
        "verdict": canonical_verdict,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": next_step,
            "verdict": canonical_verdict,
        },
    }
    return mirror_summary_line(response)


class ASTCacheTool(BaseMCPTool):
    """MCP Tool for pre-indexed AST cache operations."""

    def __init__(
        self, project_root: str | None = None, lifecycle_manager: Any = None
    ) -> None:
        self._cache: ASTCache | None = None
        self._sync: IncrementalSync | None = None
        self._watcher: FileWatcherDaemon | None = None
        self._watcher_pending_stop = False
        self._lifecycle_manager = lifecycle_manager
        self._watch_token: Any = None
        self._watch_state_lock = threading.Lock()
        self._watch_startup: _WatchStartup | None = None
        self._watcher_stopping = False
        self._cache_raw_root: str | None = None
        self._root_generation = 0
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        with self._watch_state_lock:
            self._root_generation += 1
            startup = self._watch_startup
            if startup is not None:
                startup.retired = True
            token = self._watch_token or (startup.token if startup else None)
            self._cache = None
            self._cache_raw_root = None
            self._sync = None
        # starter 尚未返回时由它清理自己的确切候选，避免丢失未启动实例。
        if startup is not None and startup.starting:
            if self._lifecycle_manager is not None:
                self._lifecycle_manager.revoke_watch_token(token)
            return
        try:
            self._retire_watcher(clear_stopped=True)
        except Exception:  # pragma: no cover — defensive
            logger.debug("watcher stop on project change failed", exc_info=True)

    def _check_watcher_shutdown(self) -> None:
        """旧项目后台任务未退出时，拒绝建立新项目运行状态。"""
        with self._watch_state_lock:
            startup = self._watch_startup
            watcher = self._watcher
            pending = self._watcher_pending_stop
            stopping = self._watcher_stopping
        if startup is not None and startup.starting:
            raise TimeoutError(
                "Watcher startup from the previous project is still running"
            )
        if stopping:
            raise TimeoutError(
                "Watcher shutdown from the previous project is still running"
            )
        if not pending:
            return
        if watcher is not None and watcher.is_running():
            raise TimeoutError(
                "Watcher from the previous project is still stopping. "
                "Retry watch_stop before accessing the new project cache."
            )
        with self._watch_state_lock:
            if self._watcher is watcher:
                self._watcher = None
                self._watcher_pending_stop = False

    def shutdown_application_watcher(self) -> None:
        """应用退出时撤销回调并停止已构造的 watcher。"""
        _, running = self._retire_watcher(clear_stopped=False)
        if running:
            raise TimeoutError("Application watcher shutdown is still pending")

    def _retire_watcher(self, *, clear_stopped: bool) -> tuple[Any, bool]:
        """按身份停止当前 watcher，并在整个 join 窗口保留所有权。"""
        with self._watch_state_lock:
            if self._watcher_stopping:
                raise TimeoutError("Watcher shutdown is already in progress")
            startup = self._watch_startup
            if startup is not None and startup.starting:
                startup.retired = True
                token = self._watch_token or startup.token
                watcher = None
                startup_pending = True
            else:
                watcher = self._watcher
                token = self._watch_token
                startup_pending = False
                self._watch_token = None
                if watcher is not None:
                    self._watcher_stopping = True
        if self._lifecycle_manager is not None:
            self._lifecycle_manager.revoke_watch_token(token)
        if startup_pending:
            raise TimeoutError("Watcher startup is still pending")
        if watcher is None:
            return None, False
        try:
            stats = watcher.get_stats() if watcher.is_running() else None
            if watcher.is_running():
                watcher.stop()
        finally:
            running = watcher.is_running()
            with self._watch_state_lock:
                self._watcher_pending_stop = running
                self._watcher_stopping = False
                if clear_stopped and not running:
                    self._watcher = None
        return stats, running

    def _get_cache(self) -> ASTCache:
        self._check_watcher_shutdown()
        with self._watch_state_lock:
            current = self._cache
            raw_root = self._project_root
            generation = self._root_generation
        if current is not None:
            return current
        if not raw_root:
            raise ValueError("Project root not set. Call set_project_path first.")
        candidate = ASTCache(raw_root)
        with self._watch_state_lock:
            valid = (
                generation == self._root_generation
                and raw_root == self._project_root
                and self._cache is None
            )
            if valid:
                self._cache = candidate
                self._cache_raw_root = raw_root
        if valid:
            return candidate
        candidate.close()
        raise TimeoutError("Project changed during cache construction")

    def get_cache(self) -> ASTCache:
        """Public alias for _get_cache() — use this instead of accessing _cache directly."""
        return self._get_cache()

    @property
    def cache_initialized(self) -> bool:
        """True if the AST cache has been lazily initialized (i.e. cached)."""
        return self._cache is not None

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
                "search (symbol search — FTS5-ranked with multi-term support when available, LIKE fallback otherwise), "
                "sync (incremental sync — detect changed/new/deleted files via content hash), "
                "changes (preview changes without re-indexing), "
                "stats (cache statistics), "
                "invalidate (remove cached entry), "
                "watch_start (start background FileWatcherDaemon for auto-sync), "
                "watch_stop (stop the background watcher and return final stats), "
                "watch_status (report whether a watcher is running and its stats). "
                "Note: ``fts_search`` is accepted as a deprecated alias for ``search`` and behaves identically. "
                "No other tool provides persistent cross-session AST caching."
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
                    "enum": [
                        "index",
                        "lookup",
                        "search",
                        "sync",
                        "changes",
                        "stats",
                        "invalidate",
                        "watch_start",
                        "watch_stop",
                        "watch_status",
                    ],
                    "description": (
                        "Operation mode. ``fts_search`` is also accepted as a "
                        "deprecated alias for ``search``."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": "File path (for lookup, index single file, invalidate)",
                },
                "language": {
                    "type": "string",
                    "description": "Language filter (optional, for search mode)",
                },
                "query": {
                    "type": "string",
                    "description": "Symbol search query (for search mode)",
                },
                "symbol": {
                    "type": "string",
                    "description": (
                        "Alias for query (the facade's canonical identifier); "
                        "searching for this symbol (#575)."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results for search (default: 100)",
                },
                "max_files": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Positive maximum files to index or sync; zero is invalid "
                        "(default: 20000)"
                    ),
                    "default": 20000,
                },
                "force": {
                    "type": "boolean",
                    "description": "Force full re-index (default: false)",
                },
                "include_activation": {
                    "type": "boolean",
                    "description": (
                        "Compute temporal git activation during project indexing. "
                        "Default false for fast warm-cache builds; single-file "
                        "indexing still computes activation unless disabled by "
                        "TSA_INDEX_ACTIVATION=0."
                    ),
                    "default": False,
                },
                "poll_interval": {
                    "type": "number",
                    "description": (
                        "watch_start: polling interval in seconds for the "
                        "background FileWatcherDaemon (default: 5.0; floor 1.0)."
                    ),
                },
                "backend": {
                    "type": "string",
                    "enum": ["poll", "watchdog"],
                    "description": (
                        "watch_start: file watcher backend. ``poll`` (default) "
                        "uses pure stdlib polling; ``watchdog`` uses OS-native "
                        "events when the optional ``watchdog`` package is "
                        "installed and falls back to polling otherwise."
                    ),
                },
            },
            # Wave 1b (audit index-10): ``mode`` is resolved at runtime
            # (defaults to ``search`` when a query is supplied, else ``stats``),
            # so it is NOT required — a required ``mode`` made strict MCP clients
            # reject a valid ``{query: X}`` call before dispatch.
            "required": [],
            "additionalProperties": False,
        }

    @staticmethod
    def _resolve_mode(arguments: dict[str, Any]) -> str:
        """Effective mode.

        Wave 1b (audit index-10): ``cache query=X`` with no explicit mode used to
        default to ``stats`` and silently drop the query. Default to ``search``
        when a query is supplied (the obvious intent), else ``stats``.
        """
        mode = arguments.get("mode")
        if mode:
            return str(mode)
        return "search" if arguments.get("query") else "stats"

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = self._resolve_mode(arguments)
        # ``fts_search`` is a deprecated alias for ``search`` — it remains
        # accepted at the validate boundary so existing MCP callers do not
        # break, but it is no longer in the schema enum (J1).
        valid_modes = {
            "index",
            "lookup",
            "search",
            "fts_search",
            "sync",
            "changes",
            "stats",
            "invalidate",
            "watch_start",
            "watch_stop",
            "watch_status",
        }
        if mode not in valid_modes:
            # ``fts_search`` is still accepted above (deprecated alias, J1) but is
            # intentionally omitted from the enumerated guidance so agents are
            # steered to the supported ``search`` name.
            raise invalid_enum_error("mode", mode, sorted(valid_modes - {"fts_search"}))
        if mode in ("lookup", "invalidate") and not arguments.get("file_path"):
            raise ValueError(f"file_path is required for mode '{mode}'")
        if mode in ("search", "fts_search") and not arguments.get("query"):
            raise ValueError(f"query is required for {mode} mode")
        arguments["max_files"] = normalize_index_max_files(arguments.get("max_files"))
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch ast_cache by ``mode``.

        r37bv (dogfood): tool flagged this at 199 lines. Refactor splits
        each of the 7 modes into a focused ``_handle_*`` method. M15 / J1
        / J8 / K7 contracts preserved exactly.
        """
        # #575: ``symbol`` is the facade's canonical identifier; accept it as an
        # alias for ``query`` so ``index action=cache symbol=X`` searches for the
        # symbol instead of silently falling back to ``stats`` (the facade used
        # to strip ``symbol`` → no query → mode=stats → wrong answer, no hint).
        if arguments.get("symbol") and not arguments.get("query"):
            arguments = {**arguments, "query": arguments["symbol"]}
        self.validate_arguments(arguments)
        mode = self._resolve_mode(arguments)

        # Watch modes are dispatched before the cache is materialised so
        # ``watch_status`` / ``watch_stop`` can answer "no watcher yet"
        # without forcing a SQLite open. ``watch_start`` does need a
        # cache, but it gets one via ``_get_cache()`` inside its handler.
        if mode == "watch_start":
            return self._handle_watch_start(arguments)
        if mode == "watch_stop":
            return self._handle_watch_stop()
        if mode == "watch_status":
            return self._handle_watch_status()

        cache = self._get_cache()

        if mode == "index":
            return self._handle_index(arguments, cache)
        if mode == "lookup":
            return self._handle_lookup(arguments, cache)
        if mode in ("search", "fts_search"):
            return self._handle_search(arguments, cache, mode)
        if mode == "stats":
            return self._handle_stats(cache)
        if mode == "sync":
            return self._handle_sync(arguments)
        if mode == "changes":
            return self._handle_changes()
        if mode == "invalidate":
            return self._handle_invalidate(arguments, cache)
        return _build_unknown_mode_response(mode)

    def _handle_index(self, arguments: dict[str, Any], cache: Any) -> dict[str, Any]:
        """``mode=index``: per-file or whole-project AST cache build."""
        file_path = arguments.get("file_path")
        if file_path:
            resolved = self.resolve_and_validate_file_path(file_path)
            result = cache.index_file(resolved)
            symbols = int(result.get("symbol_count", result.get("symbols", 0)) or 0)
            summary_line = f"ast_cache index file={file_path} symbols={symbols}"
            next_step = (
                f"ast_cache mode=lookup file_path={file_path!r} "
                "to retrieve the cached entry"
            )
        else:
            max_files = arguments["max_files"]
            force = arguments.get("force", False)
            include_activation = bool(arguments.get("include_activation", False))
            # #1018: honor the language scope on the index path. Without this the
            # filter was accepted but dropped, so e.g. --ast-cache-language python
            # still parsed .swift files and emitted "grammar not installed" errors.
            language_filter = arguments.get("language") or None
            result = cache.index_project(
                max_files=max_files,
                force=force,
                include_activation=include_activation,
                language_filter=language_filter,
            )
            files_indexed_fallback = result.get("files_indexed", 0)
            indexed_files = int(result.get("indexed", files_indexed_fallback) or 0)
            # Get total symbol count from the cache after indexing completes
            stats = cache.get_stats()
            symbols = int(stats.get("total_symbols", 0) or 0)
            summary_line = (
                f"ast_cache index project files={indexed_files} "
                f"symbols={symbols} force={bool(force)}"
            )
            next_step = "ast_cache mode=stats to confirm the index size"
        return _build_ast_cache_envelope("index", result, summary_line, next_step)

    def _handle_lookup(self, arguments: dict[str, Any], cache: Any) -> dict[str, Any]:
        """``mode=lookup``: read a single file's cached AST entry."""
        file_path = arguments.get("file_path", "")
        resolved = self.resolve_and_validate_file_path(file_path)
        result = cache.lookup(resolved)
        if result is None:
            summary_line = f"ast_cache lookup file={file_path} status=not_found"
            next_step = (
                f"ast_cache mode=index file_path={file_path!r} to populate the cache"
            )
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
        next_step = "analyze_code_structure on this file for an interactive table view"
        return _build_ast_cache_envelope("lookup", result, summary_line, next_step)

    @staticmethod
    def _handle_search(
        arguments: dict[str, Any], cache: Any, mode: str
    ) -> dict[str, Any]:
        """``mode=search`` / ``fts_search``: J1 unified FTS lookup with K7 split.

        ``fts_search`` is a deprecated alias for ``search`` — both call
        ``cache.fts_search`` and echo the invoked alias name verbatim.
        """
        query = arguments.get("query", "")
        language = arguments.get("language")
        limit = arguments.get("limit", 100)
        fts5_available = cache.fts5_available
        # G2: use BM25-ranked search for queries >= 2 chars when FTS5 is available.
        use_ranked = fts5_available and len(query) >= 2 and mode != "fts_search"
        if use_ranked:
            raw_results = cache.fts_search_ranked(query, language=language, limit=limit)
        else:
            raw_results = cache.fts_search(query, language=language, limit=limit)
        # #737: measure truncation BEFORE _apply_legacy_import_split — that helper
        # can expand rows (multi-symbol imports), so post-split len may exceed limit
        # even without the DB capping results, producing a false positive.
        truncated = len(raw_results) >= limit
        # K7: defensively split legacy multi-symbol import rows.
        results = _apply_legacy_import_split(raw_results)
        summary_line = (
            f"ast_cache {mode} query={query!r} "
            f"results={len(results)} fts5={fts5_available}"
        )
        # Wave 1b (audit index-05): only tell the agent to (re)build the index
        # when FTS is actually unavailable. When FTS5 is available an empty
        # result is a genuine no-match — don't mislead with "populate the index".
        if results:
            next_step = (
                "ast_cache mode=lookup file_path=<result.file> for the full entry"
            )
        elif not fts5_available:
            next_step = (
                "FTS5 unavailable — ast_cache mode=index to (re)build the index, "
                "then retry the search"
            )
        else:
            next_step = (
                f"No symbols match {query!r} — broaden the term, or use "
                "search action=symbol / codegraph_symbol_search to discover names"
            )
        payload: dict[str, Any] = {
            "query": query,
            "results": results,
            "count": len(results),
            "truncated": truncated,
            "fts5_available": fts5_available,
        }
        if use_ranked and results:
            payload["ranked"] = True
            payload["ranking_method"] = "fts5_bm25"
        if mode == "fts_search":
            payload["deprecated_alias"] = (
                "use mode='search' — 'fts_search' is a deprecated alias"
            )
        return _build_ast_cache_envelope(mode, payload, summary_line, next_step)

    @staticmethod
    def _handle_stats(cache: Any) -> dict[str, Any]:
        """``mode=stats``: aggregate row counts + FTS5 capability flag.

        r37f7-U3: promote summary-line scalars to top-level envelope fields.
        Before the fix, ``summary_line`` carried ``files=1263 symbols=30238
        fts5=True`` but the only top-level scalars were ``total_files`` /
        ``total_symbols`` / ``fts5_available``. Agents that read the
        envelope by the agent-friendly aliases (``indexed_files``,
        ``db_size_mb``) saw ``null`` and had to string-parse the headline
        to recover the numbers. We now mirror the canonical counts under
        the alias names and compute the SQLite file size on disk.
        """
        stats = cache.get_stats()
        total_files = int(stats.get("total_files", 0) or 0)
        total_symbols = int(stats.get("total_symbols", 0) or 0)
        fts5_available = bool(stats.get("fts5_available", False))

        # U3: ``indexed_files`` is the agent-friendly alias for
        # ``total_files``. Both keys carry the same number so callers
        # branching on either field see consistent data.
        stats.setdefault("indexed_files", total_files)

        # U3: compute the on-disk db size in megabytes for agents that
        # want a quick capacity check without re-reading ``db_path``.
        # ``os.path.getsize`` may raise ``OSError`` if the cache file
        # has been removed between ``get_stats()`` and now — we treat
        # that as "unknown" and emit ``0.0`` so the field is never
        # ``None`` (agents that branch on ``is None`` would otherwise
        # see a regression from the no-cache path).
        db_path = stats.get("db_path")
        db_size_mb = 0.0
        if isinstance(db_path, str) and db_path:
            try:
                db_size_bytes = os.path.getsize(db_path)
                db_size_mb = round(db_size_bytes / (1024 * 1024), 3)
            except OSError:
                db_size_mb = 0.0
        stats.setdefault("db_size_mb", db_size_mb)

        summary_line = (
            f"ast_cache stats files={total_files} "
            f"symbols={total_symbols} fts5={fts5_available}"
        )
        if total_files == 0:
            next_step = "ast_cache mode=index to populate the cache"
        else:
            next_step = "ast_cache mode=fts_search query=<symbol> to find a symbol"
        return _build_ast_cache_envelope("stats", stats, summary_line, next_step)

    def _handle_sync(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """``mode=sync``: drift-detect + reconcile + M15 considered alias."""
        sync_engine = self._get_sync()
        max_files = arguments["max_files"]
        sync_result = sync_engine.sync(max_files=max_files)
        sync_dict = sync_result.to_dict()
        # M15: surface J8's ``considered`` vocabulary at the top level too.
        sync_dict.setdefault("considered", sync_dict.get("scanned", 0))
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

    def _handle_changes(self) -> dict[str, Any]:
        """``mode=changes``: pending new/modified/deleted file list."""
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

    def _handle_invalidate(
        self, arguments: dict[str, Any], cache: Any
    ) -> dict[str, Any]:
        """``mode=invalidate``: drop a single file's cached AST entry."""
        file_path = arguments.get("file_path", "")
        resolved = self.resolve_and_validate_file_path(file_path)
        removed = cache.invalidate(resolved)
        summary_line = f"ast_cache invalidate file={file_path} removed={bool(removed)}"
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

    def _handle_watch_start(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """``mode=watch_start``: spawn (or reuse) the FileWatcherDaemon.

        Idempotent — if a watcher is already running, returns
        ``status='already_running'`` with the same envelope shape so
        callers can branch on ``status`` instead of error-handling.
        """
        self._check_watcher_shutdown()
        # 已运行时沿用当前项目监听器。
        stale_token = None
        with self._watch_state_lock:
            current_watcher = self._watcher
            current_token = self._watch_token
            current_running = (
                current_watcher is not None and current_watcher.is_running()
            )
            if current_watcher is not None and not current_running:
                stale_token = current_token
                self._watch_token = None
        if current_running and current_watcher is not None:
            if not self._watch_token_is_current(current_token):
                raise TimeoutError("Watcher project changed before rebind cleanup")
            return self._already_running_response(current_watcher)
        if self._lifecycle_manager is not None and stale_token is not None:
            self._lifecycle_manager.revoke_watch_token(stale_token)

        raw_root = self._project_root
        if not raw_root:
            raise ValueError("Project root not set. Call set_project_path first.")
        token = None
        if self._lifecycle_manager is not None:
            token = self._lifecycle_manager.issue_watch_token(raw_root)
        startup = _WatchStartup(raw_root, token)
        with self._watch_state_lock:
            token_current = self._watch_token_is_current(token)
            winner = self._watcher
            winner_token = self._watch_token
            winner_running = winner is not None and winner.is_running()
            busy = (
                self._watch_startup is not None
                or self._watcher_stopping
                or self._watcher_pending_stop
            )
            if winner_running or busy or not token_current:
                startup.retired = True
            else:
                self._watch_startup = startup
        if startup.retired:
            if self._lifecycle_manager is not None:
                self._lifecycle_manager.revoke_watch_token(token)
            if winner_running and self._watch_token_is_current(winner_token):
                return self._already_running_response(winner)
            raise TimeoutError("Watcher project changed during startup")

        daemon = None
        try:
            cache = self._cache_for_watch_startup(startup)
            poll_interval = float(arguments.get("poll_interval", 5.0))
            backend = str(arguments.get("backend", "poll"))
            from ..watch_push_bridge import make_on_sync_callback
        except Exception:
            self._rollback_watch_startup(startup, daemon)
            raise

        on_sync = None
        if self._lifecycle_manager is not None:
            on_sync = make_on_sync_callback(
                startup.raw_root, self._lifecycle_manager, startup.token
            )

        try:
            daemon = FileWatcherDaemon(
                cache,
                poll_interval=poll_interval,
                backend=backend,
                on_sync=on_sync,
            )
            with self._watch_state_lock:
                startup.daemon = daemon
                if startup.retired or not self._watch_token_is_current(startup.token):
                    raise TimeoutError("Watcher project changed during startup")
                self._watcher = daemon
                self._watch_token = startup.token
                startup.authorized = True
            daemon.start()
        except Exception:
            self._rollback_watch_startup(startup, daemon)
            raise

        with self._watch_state_lock:
            retired = startup.retired or not self._watch_token_is_current(startup.token)
            if not retired:
                startup.starting = False
            if not retired and self._watch_startup is startup:
                self._watch_startup = None
        if retired:
            if self._lifecycle_manager is not None:
                self._lifecycle_manager.revoke_watch_token(startup.token)
            try:
                daemon.stop()
            finally:
                with self._watch_state_lock:
                    running = daemon.is_running()
                    startup.starting = False
                    self._watcher_pending_stop = running
                    if not running:
                        self._watcher = None
                    self._watch_token = None
                    self._watch_startup = None
            raise TimeoutError("Watcher project changed during startup")

        # Read back the actual values the daemon enforced (poll_interval
        # has a min of 1.0 inside the daemon, so echo what was applied).
        applied_poll = float(daemon.poll_interval)
        applied_backend = str(daemon.backend)
        summary_line = (
            f"ast_cache watch_start status=started "
            f"backend={applied_backend} poll_interval={applied_poll}"
        )
        payload = {
            "status": "started",
            "poll_interval": applied_poll,
            "backend": applied_backend,
        }
        return _build_ast_cache_envelope(
            "watch_start",
            payload,
            summary_line,
            "ast_cache mode=watch_status to inspect the daemon",
        )

    def _watch_token_is_current(self, token: Any) -> bool:
        """核验预约 token；无 manager 的兼容路径只依赖本地 retirement。"""
        if self._lifecycle_manager is None:
            return True
        return bool(self._lifecycle_manager.is_watch_token_current(token))

    def _already_running_response(self, watcher: FileWatcherDaemon) -> dict[str, Any]:
        """构造不改变现有 daemon 所有权的幂等启动响应。"""
        poll_interval = float(watcher.poll_interval)
        backend = str(watcher.backend)
        summary_line = (
            f"ast_cache watch_start status=already_running "
            f"backend={backend} poll_interval={poll_interval}"
        )
        return _build_ast_cache_envelope(
            "watch_start",
            {
                "status": "already_running",
                "poll_interval": poll_interval,
                "backend": backend,
            },
            summary_line,
            "ast_cache mode=watch_status to check progress",
        )

    def _rollback_watch_startup(
        self, startup: _WatchStartup, daemon: FileWatcherDaemon | None
    ) -> None:
        """失败时撤销预约；仅活跃的部分 daemon 继续占有 slot。"""
        if self._lifecycle_manager is not None:
            self._lifecycle_manager.revoke_watch_token(startup.token)
        running = bool(daemon is not None and daemon.is_running())
        with self._watch_state_lock:
            self._watch_token = None
            startup.starting = False
            self._watcher_pending_stop = running
            if running:
                self._watcher = daemon
            elif self._watcher is daemon:
                self._watcher = None
            self._watch_startup = None

    def _cache_for_watch_startup(self, startup: _WatchStartup) -> ASTCache:
        """为预约 root 构造 cache，并在发布前重验预约身份。"""
        with self._watch_state_lock:
            valid = (
                self._watch_startup is startup
                and not startup.retired
                and self._watch_token_is_current(startup.token)
            )
            current = (
                self._cache
                if valid and self._cache_raw_root == startup.raw_root
                else None
            )
        if current is not None:
            startup.cache = current
            return current
        candidate = ASTCache(startup.raw_root)
        with self._watch_state_lock:
            valid = (
                self._watch_startup is startup
                and not startup.retired
                and self._watch_token_is_current(startup.token)
            )
            published = (
                self._cache
                if valid and self._cache_raw_root == startup.raw_root
                else None
            )
            if valid and published is None:
                self._cache = candidate
                self._cache_raw_root = startup.raw_root
                startup.cache = candidate
            elif valid:
                startup.cache = published
        if valid and published is not None:
            candidate.close()
            return published
        if valid:
            return candidate
        candidate.close()
        raise TimeoutError("Watcher project changed during cache construction")

    def _handle_watch_stop(self) -> dict[str, Any]:
        """``mode=watch_stop``: stop the running watcher and return stats.

        If no watcher was ever started (or one was already stopped),
        return ``status='not_running'`` without raising. The envelope
        still carries ``success=True`` so callers can treat stop as
        idempotent.
        """
        final_stats, running = self._retire_watcher(clear_stopped=False)
        if final_stats is None:
            summary_line = "ast_cache watch_stop status=not_running"
            return _build_ast_cache_envelope(
                "watch_stop",
                {"status": "not_running"},
                summary_line,
                "ast_cache mode=watch_start to begin watching",
            )

        if running:
            raise TimeoutError(
                "Watcher shutdown timed out; background work is still running. "
                "Retry watch_stop before closing or replacing the cache."
            )
        summary_line = (
            f"ast_cache watch_stop status=stopped "
            f"uptime={final_stats.get('uptime_seconds', 0.0)}"
        )
        return _build_ast_cache_envelope(
            "watch_stop",
            {"status": "stopped", "final_stats": final_stats},
            summary_line,
            "ast_cache mode=stats to confirm cache state",
        )

    def _handle_watch_status(self) -> dict[str, Any]:
        """``mode=watch_status``: report watcher liveness and stats.

        Three states surfaced:
          - never created → ``running=False, watcher_created=False``
          - created but stopped → ``running=False, watcher_created=True``
          - running → ``running=True, watcher_created=True`` + ``stats``
        """
        if self._watcher is None:
            summary_line = "ast_cache watch_status running=false watcher_created=false"
            return _build_ast_cache_envelope(
                "watch_status",
                {"running": False, "watcher_created": False},
                summary_line,
                "ast_cache mode=watch_start to begin watching",
            )

        running = self._watcher.is_running()
        payload: dict[str, Any] = {
            "running": running,
            "watcher_created": True,
        }
        if running:
            payload["stats"] = self._watcher.get_stats()
            summary_line = "ast_cache watch_status running=true watcher_created=true"
            next_step = "ast_cache mode=watch_stop to halt the watcher"
        else:
            summary_line = "ast_cache watch_status running=false watcher_created=true"
            next_step = "ast_cache mode=watch_start to resume watching"
        return _build_ast_cache_envelope(
            "watch_status",
            payload,
            summary_line,
            next_step,
        )
