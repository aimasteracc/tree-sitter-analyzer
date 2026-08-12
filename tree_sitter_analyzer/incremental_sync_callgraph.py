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
    """Run all three backfills and publish every suppressed stage failure."""
    clear_call_graph_built_strict(cache.get_conn())
    complete = True
    synapse_resolved = 0
    stages = (
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
