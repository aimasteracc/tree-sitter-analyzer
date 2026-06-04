#!/usr/bin/env python3
"""
Auto-Index Guard — Transparent AST cache warming for codegraph tools.

Problem: codegraph_callers, codegraph_callees, codegraph_symbol_search, etc.
all depend on the AST cache being populated.  Today an agent must first call
``ast_cache mode=index`` and only then call the analysis tools.  Two-step.

Solution: ``AutoIndexGuard`` is a thin singleton that any tool can call before
accessing the cache.  On first invocation per project-root it triggers
``ASTCache.index_project()`` automatically, so the first ``codegraph_callers``
call "just works" even if the agent never called ``ast_cache``.

Subsequent calls are instant (one dict lookup + one SQLite COUNT).

Usage in a tool::

    from ..utils.auto_index_guard import ensure_indexed
    cache = ensure_indexed(project_root)
    if cache is not None:
        callers = cache.query_callers(func_name)

Integration points:
  - callers_tool.py, callees_tool.py: replace ``_try_get_cache()``
  - codegraph_metrics_tool.py: replace ``_get_cache()``
  - codegraph_symbol_search_tool.py: replace ``_get_cache()``
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_indexed_roots: dict[str, bool] = {}


def ensure_indexed(
    project_root: str | None,
    max_files: int = 20_000,
    *,
    auto_build: bool = True,
) -> Any:
    """Return a ready-to-query ASTCache, optionally auto-indexing if empty.

    Returns ``None`` when ``project_root`` is ``None``, when indexing
    fails, or when ``auto_build=False`` and the cache is empty.
    Thread-safe: concurrent calls for the same root block on a single
    index build.

    ``auto_build`` controls the cold-start behaviour:

    * **True** (default, legacy) — synchronously index the project if
      the cache is empty. Can take 30-60 s on a 1500-file repo and
      regularly trips MCP clients' default 30 s tool-call timeouts,
      surfacing as a "stuck server" report from the operator.
    * **False** — fail fast. If the cache is empty, return ``None``
      immediately so the calling tool can surface "run
      codegraph_autoindex first" rather than blocking. Read-only
      tools that don't *need* to build the cache (``codegraph_metrics``,
      ``codegraph_status``) should pass this.
    """
    if project_root is None:
        return None

    if _indexed_roots.get(project_root):
        cache = _open_cache(project_root)
        if cache is not None:
            return cache

    with _lock:
        if _indexed_roots.get(project_root):
            cache = _open_cache(project_root)
            if cache is not None:
                return cache

        cache = _open_cache(project_root)
        if cache is None:
            return None

        stats = cache.get_stats()
        if stats.get("total_files", 0) > 0:
            # Cold-start fast path: a fully-indexed cache is already queryable.
            # The cross-file resolve pass converges in one pass and is re-run by
            # the indexing path on every file change, so re-running it here when
            # the index is UNCHANGED is a ~40 s no-op (the surviving pending refs
            # are terminal — external bases / dynamic dispatch). Skip it when the
            # resolve already converged for this exact index state; the first
            # retrieval then returns in ms instead of blocking for ~40 s.
            if not _resolution_converged(cache):
                _resolve_pending_unresolved_refs(cache)
                _mark_resolution_converged(cache)
            _indexed_roots[project_root] = True
            return cache

        if not auto_build:
            # Cache is empty and the caller opted out of synchronous
            # indexing — return ``None`` so the tool can surface a
            # "cache empty, run codegraph_autoindex first" hint
            # instead of blocking the MCP request for 30-60 s and
            # tripping the client timeout.
            return None

        logger.info("auto-index: warming cache for %s", project_root)
        try:
            cache.index_project(max_files=max_files)
        except Exception:
            logger.exception("auto-index: failed for %s", project_root)
            return None

        _indexed_roots[project_root] = True
        return cache


def _open_cache(project_root: str) -> Any:
    try:
        from ...ast_cache import ASTCache

        return ASTCache(project_root)
    except Exception:
        return None


def _resolve_pending_unresolved_refs(cache: Any) -> None:
    try:
        from ..._ast_cache_unresolved import pending_unresolved_count

        if pending_unresolved_count(cache.get_conn()) > 0:
            cache.index_project(resolve_only=True)
    except Exception:
        logger.debug("auto-index: unresolved_refs resolve-only failed", exc_info=True)


def _resolution_converged(cache: Any) -> bool:
    try:
        from ..._ast_cache_unresolved import resolution_converged

        return bool(resolution_converged(cache.get_conn()))
    except Exception:
        return False


def _mark_resolution_converged(cache: Any) -> None:
    try:
        from ..._ast_cache_unresolved import mark_resolution_converged

        mark_resolution_converged(cache.get_conn())
    except Exception:
        logger.debug("auto-index: could not mark resolution converged", exc_info=True)


def mark_dirty(project_root: str) -> None:
    """Mark a project root as needing re-index on next ``ensure_indexed``."""
    _indexed_roots.pop(project_root, None)


def reset() -> None:
    """Clear all cached state (for testing)."""
    with _lock:
        _indexed_roots.clear()


def is_indexed(project_root: str) -> bool:
    return _indexed_roots.get(project_root, False)
