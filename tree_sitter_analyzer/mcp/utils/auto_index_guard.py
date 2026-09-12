#!/usr/bin/env python3
"""
Auto-Index Guard — Transparent AST cache warming for codegraph tools.

Problem: codegraph_callers, codegraph_callees, codegraph_metrics and others
read the AST cache, so an agent would otherwise have to call
``ast_cache mode=index`` before any analysis tool.  Two-step.

Solution: ``AutoIndexGuard`` is a thin singleton that a tool calls before
accessing the cache.  On first invocation per project-root it triggers
``ASTCache.index_project()``, so the first call warms what it needs instead of
failing on a cold cache.  Subsequent calls are instant (one dict lookup + one
SQLite COUNT).

Usage in a tool::

    from ..utils.auto_index_guard import ensure_indexed
    cache = ensure_indexed(project_root)
    if cache is not None:
        callers = cache.query_callers(func_name)

Pass ``auto_build=False`` for a strictly read-only lookup that must not write
the cache.

Current call sites: ``incremental_sync_tool``, ``codegraph_visualization_hub``,
``codegraph_refactor_tool`` and ``auto_index_tool`` warm with the default
``auto_build=True``; ``codegraph_metrics_tool`` reads with ``auto_build=False``.

``codegraph_symbol_search_tool`` is deliberately **not** a call site.  Warming
can leave an empty or partial index, and symbol search must never convert that
into a "the symbol is absent" verdict; it keeps an explicit ``INDEX_NOT_READY``
with a recovery hint instead.  That guarantee is pinned by
``test_empty_index_does_not_claim_symbol_absence`` and
``TestCodeGraphSymbolSearchNoCache::test_search_on_empty_project`` (2026-09-09).
Do not wire ``ensure_indexed`` into that tool, and do not read its absence there
as a missing integration.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from ...indexing_limits import normalize_index_max_files

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_indexed_roots: dict[str, bool] = {}


def ensure_indexed(
    project_root: str | None,
    max_files: int = 20_000,
    *,
    auto_build: bool = True,
) -> Any:
    """Return a queryable cache and repair stale pipeline certification.

    Populated caches remain useful as a fallback, but only a cache carrying the
    exact current call-graph pipeline marker enters the process fast-path.  A
    legacy/non-current marker is repaired by a normal cached ``index_project``
    run so all three graph backfill stages execute and the current marker is
    stamped.  ``auto_build=False`` is strictly read-only at this layer.
    """
    max_files = normalize_index_max_files(max_files)
    if project_root is None:
        return None

    if _indexed_roots.get(project_root):
        cache = _open_cache(project_root)
        if cache is not None:
            if not auto_build or _call_graph_marker_is_current(cache):
                return cache
            # Persisted invalidation must defeat the in-process fast path.
            try:
                cache.close()
            finally:
                _indexed_roots.pop(project_root, None)

    with _lock:
        if _indexed_roots.get(project_root):
            cache = _open_cache(project_root)
            if cache is not None:
                if not auto_build or _call_graph_marker_is_current(cache):
                    return cache
                try:
                    cache.close()
                finally:
                    _indexed_roots.pop(project_root, None)

        cache = _open_cache(project_root)
        if cache is None:
            return None

        stats = cache.get_stats()
        populated = stats.get("total_files", 0) > 0
        if not auto_build:
            return cache if populated else None

        if populated and _call_graph_marker_is_current(cache):
            if not _resolution_converged(cache):
                if _resolve_pending_unresolved_refs(cache):
                    _mark_resolution_converged(cache)
            _indexed_roots[project_root] = True
            return cache

        logger.info("auto-index: warming cache for %s", project_root)
        try:
            # Deliberately not resolve_only: legacy markers need the complete
            # cached indexing/backfill/certification pipeline.
            cache.index_project(max_files=max_files)
        except Exception:
            logger.exception("auto-index: failed for %s", project_root)
            return cache if populated else None

        if _call_graph_marker_is_current(cache):
            _indexed_roots[project_root] = True
        else:
            logger.warning(
                "auto-index: pipeline marker remains non-current for %s", project_root
            )
        return cache


def _open_cache(project_root: str) -> Any:
    try:
        from ...ast_cache import ASTCache

        return ASTCache(project_root)
    except Exception:
        return None


def _call_graph_marker_is_current(cache: Any) -> bool:
    """Read the exact versioned marker without creating or updating it."""
    try:
        from ...cache.callgraph_state import call_graph_marker_is_current

        return bool(call_graph_marker_is_current(cache.get_conn()))
    except Exception:
        return False


def _resolve_pending_unresolved_refs(cache: Any) -> bool:
    """Attempt the resolve-only pass. Returns True on success, False if it failed."""
    try:
        from tree_sitter_analyzer.cache.unresolved import pending_unresolved_count

        if pending_unresolved_count(cache.get_conn()) > 0:
            cache.index_project(resolve_only=True)
        return True
    except Exception:
        logger.debug("auto-index: unresolved_refs resolve-only failed", exc_info=True)
        return False


def _resolution_converged(cache: Any) -> bool:
    try:
        from tree_sitter_analyzer.cache.unresolved import resolution_converged

        return bool(resolution_converged(cache.get_conn()))
    except Exception:
        return False


def _mark_resolution_converged(cache: Any) -> None:
    try:
        from tree_sitter_analyzer.cache.unresolved import mark_resolution_converged

        if getattr(cache, "_generation_managed", False):
            from ...cache.generation_indexing import mutate_published_cache

            mutate_published_cache(
                cache, lambda writable: mark_resolution_converged(writable.get_conn())
            )
        else:
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


def empty_index_diagnostic(cache: Any) -> dict[str, Any]:
    """仅诊断未初始化的空索引，不证明已有索引的完整性或新鲜度。"""
    conn = cache.get_conn()
    populated = conn.execute(
        "SELECT EXISTS(SELECT 1 FROM ast_index) "
        "OR EXISTS(SELECT 1 FROM ast_index_snapshot_manifest)"
    ).fetchone()[0]
    if populated or _call_graph_marker_is_current(cache):
        return {}
    next_step = (
        "From the project root, run tree-sitter-analyzer --ast-cache "
        "--ast-cache-mode index --format json, or call index action=cache mode=index "
        "for the bound project, then retry the query."
    )
    return {
        "success": False,
        "verdict": "ERROR",
        "error_type": "validation",
        "error_code": "INDEX_NOT_READY",
        "error": "INDEX_NOT_READY: No indexed files or completed indexing run. "
        "An empty lookup cannot establish that the requested symbol is absent.",
        "next_step": next_step,
        "recovery_hint": next_step,
        "suggested_tool": "index action=cache mode=index",
        "agent_summary": {
            "verdict": "ERROR",
            "summary_line": "INDEX_NOT_READY: Build the index before querying symbols.",
            "next_step": next_step,
        },
    }
