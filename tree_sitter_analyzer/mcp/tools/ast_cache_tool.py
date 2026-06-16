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
from typing import Any

from ...ast_cache import ASTCache
from ...file_watcher import FileWatcherDaemon
from ...incremental_sync import IncrementalSync
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

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: ASTCache | None = None
        self._sync: IncrementalSync | None = None
        self._watcher: FileWatcherDaemon | None = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._cache = None
        self._sync = None
        # Stop any running watcher when project root changes — it was
        # snapshotting a different tree and would emit confusing events.
        if self._watcher is not None:
            try:
                if self._watcher.is_running():
                    self._watcher.stop()
            except Exception:  # pragma: no cover — defensive
                logger.debug("watcher stop on project change failed", exc_info=True)
        self._watcher = None

    def _get_cache(self) -> ASTCache:
        if self._cache is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            self._cache = ASTCache(self.project_root)
        return self._cache

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
                    "description": "Max files to index (default: 20000)",
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
            max_files = arguments.get("max_files", 20_000)
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
        max_files = arguments.get("max_files", 20_000)
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
        # Already running? Don't double-start.
        if self._watcher is not None and self._watcher.is_running():
            poll_interval = float(self._watcher.poll_interval)
            backend = str(self._watcher.backend)
            summary_line = (
                f"ast_cache watch_start status=already_running "
                f"backend={backend} poll_interval={poll_interval}"
            )
            payload: dict[str, Any] = {
                "status": "already_running",
                "poll_interval": poll_interval,
                "backend": backend,
            }
            return _build_ast_cache_envelope(
                "watch_start",
                payload,
                summary_line,
                "ast_cache mode=watch_status to check progress",
            )

        # Lazily build the cache + daemon. Tests always pass project_root,
        # so _get_cache() won't raise; if it does, the ValueError surfaces
        # to the caller as a typical input error.
        cache = self._get_cache()
        poll_interval = float(arguments.get("poll_interval", 5.0))
        backend = str(arguments.get("backend", "poll"))
        from ..watch_push_bridge import make_on_sync_callback

        self._watcher = FileWatcherDaemon(
            cache,
            poll_interval=poll_interval,
            backend=backend,
            on_sync=make_on_sync_callback(self._project_root),
        )
        self._watcher.start()

        # Read back the actual values the daemon enforced (poll_interval
        # has a min of 1.0 inside the daemon, so echo what was applied).
        applied_poll = float(self._watcher.poll_interval)
        applied_backend = str(self._watcher.backend)
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

    def _handle_watch_stop(self) -> dict[str, Any]:
        """``mode=watch_stop``: stop the running watcher and return stats.

        If no watcher was ever started (or one was already stopped),
        return ``status='not_running'`` without raising. The envelope
        still carries ``success=True`` so callers can treat stop as
        idempotent.
        """
        if self._watcher is None or not self._watcher.is_running():
            summary_line = "ast_cache watch_stop status=not_running"
            return _build_ast_cache_envelope(
                "watch_stop",
                {"status": "not_running"},
                summary_line,
                "ast_cache mode=watch_start to begin watching",
            )

        # Snapshot stats BEFORE stopping so uptime_seconds is non-zero
        # even when the daemon stops mid-poll-tick.
        final_stats = self._watcher.get_stats()
        self._watcher.stop()
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
