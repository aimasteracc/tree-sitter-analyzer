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


def run_call_graph_pipeline(cache: Any) -> tuple[bool, int]:
    """Run all three backfills in order and fail closed on any bad result."""
    clear_call_graph_built_strict(cache.get_conn())
    complete = True
    synapse_resolved = 0
    stages = (
        ("cross_file", cache.backfill_cross_file_edges),
        ("synapse", cache._run_synapse_backfill),
        ("unresolved", cache._run_unresolved_refs_backfill),
    )
    for stage_name, stage in stages:
        try:
            stats = stage()
            clean = isinstance(stats, Mapping) and stats.get("errors", 0) == 0
            complete = bool(complete and clean)
            if stage_name == "synapse" and isinstance(stats, Mapping):
                resolved = stats.get("resolved", 0)
                if type(resolved) is int:
                    synapse_resolved = resolved
        except Exception:
            complete = False
            logger.debug("incremental %s backfill failed", stage_name, exc_info=True)
    return complete, synapse_resolved
