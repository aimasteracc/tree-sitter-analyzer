"""Authoritative call-graph pipeline repair for incremental synchronization."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .cache.callgraph_state import clear_call_graph_built_strict

logger = logging.getLogger(__name__)


def pipeline_repair_required(result: Any, marker_current: bool) -> bool:
    """Return whether source changes or stale certification require repair."""
    return bool(
        result.new_files
        or result.updated_files
        or result.deleted_files
        or result.changed_during_run
        or not marker_current
    )


def _record_pipeline_warning(result: Any, stage_name: str, reason: str) -> None:
    """Publish one exact warning diagnostic for a failed pipeline stage."""
    if result is None:
        return
    result.backfill_errors += 1
    result.errors += 1
    result.details.append(
        {
            "stage": stage_name,
            "considered": "backfill",
            "action": "backfill",
            "status": "warning",
            "reason": reason,
        }
    )


def run_call_graph_pipeline(cache: Any, result: Any = None) -> tuple[bool, int]:
    """Run all three backfills and publish every suppressed stage failure.

    #1696：能界定依赖时只重新解析受影响的边（``cache.backfill_scope``），否则全量。
    """
    from .cache import backfill_scope

    conn = cache.get_conn()
    decision = backfill_scope.decide(cache, conn, _changed_count(result))
    if result is not None:
        result.backfill_scope = decision.to_dict()
    # #1723：发布后内存调用图按同一范围增量更新。
    from . import call_graph_incremental

    call_graph_incremental.note_scope(cache, decision)
    with backfill_scope.active(conn, decision.scope):
        return _run_stages(cache, result)


def _changed_count(result: Any) -> int | None:
    """本轮改动的文件数；不知道或运行中源码又变了时为 None（全量）。"""
    if result is None or getattr(result, "changed_during_run", None):
        return None
    total = 0
    for name in ("new_files", "updated_files", "deleted_files"):
        count: object = getattr(result, name, None)
        if type(count) is not int:
            return None
        total += count
    # #1735：稳定失败（缺少可选语法等）的文件不写任何行，也就没有可记录的写入；
    # 它们在全新重建中同样没有行，不属于需要界定的改动。
    return total - _stable_failure_count(result)


def _stable_failure_count(result: Any) -> int:
    from .cache.publication_policy import FAILURE_KIND, STABLE

    return sum(
        1
        for detail in getattr(result, "details", None) or ()
        if isinstance(detail, Mapping)
        and detail.get("status") == "error"
        and detail.get(FAILURE_KIND) == STABLE
        and detail.get("file")
    )


def _resolve_import_specifiers(cache: Any) -> Mapping[str, int]:
    from .cache.import_specifier_edges import resolve_import_specifier_edges

    return resolve_import_specifier_edges(cache.get_conn())


def _run_stages(cache: Any, result: Any) -> tuple[bool, int]:
    clear_call_graph_built_strict(cache.get_conn())
    complete = True
    synapse_resolved = 0
    stages = (
        # #1746：相对导入说明符按最终文件集合解析（与索引顺序无关），先于其他回填。
        ("import_specifiers", lambda: _resolve_import_specifiers(cache)),
        ("cross_file", cache.backfill_cross_file_edges),
        ("synapse", cache._run_synapse_backfill),
        ("unresolved", cache._run_unresolved_refs_backfill),
    )
    for stage_name, stage in stages:
        reason: str | None = None
        try:
            stats = stage()
            if not isinstance(stats, Mapping):
                reason = "BACKFILL_RESULT_NOT_MAPPING"
            else:
                stage_errors = stats.get("errors", 0)
                if type(stage_errors) is not int or stage_errors != 0:
                    reason = "BACKFILL_REPORTED_ERRORS"
                if stage_name == "synapse":
                    resolved = stats.get("resolved", 0)
                    if type(resolved) is int:
                        synapse_resolved = resolved
        except Exception as exc:
            reason = f"BACKFILL_EXCEPTION:{type(exc).__name__}"
            logger.debug("incremental %s backfill failed", stage_name, exc_info=True)
        if reason is not None:
            complete = False
            _record_pipeline_warning(result, stage_name, reason)
    return complete, synapse_resolved
