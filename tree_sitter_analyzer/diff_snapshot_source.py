"""Resolve the source-generation token shared by diff and index snapshots."""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from typing import Any, cast

from .source_oracle import SourceOracleError


def resolve_shared_source_generation(
    project_root: str,
    deadline: float,
    *,
    oracle_generation: Callable[..., tuple[str, Any]],
) -> str:
    """Return the P0.1 source-oracle token, replaying its certified scope."""
    from .index_snapshot import lease_existing_snapshot, lease_reusable_snapshot
    from .index_source_snapshot import capture_current_source_snapshot

    if time.monotonic() > deadline:
        raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT")
    # Lightweight injected registry seams predate the shared-oracle bridge.
    # Production oracle_generation always exposes epoch_out.
    if "epoch_out" not in inspect.signature(oracle_generation).parameters:
        generation, _identity = oracle_generation(
            project_root, "diff", deadline=deadline
        )
        return generation
    reusable = _lease_with_optional_deadline(
        lease_reusable_snapshot, project_root, deadline
    )
    with reusable as reusable_snapshot:
        if (
            reusable_snapshot is not None
            and reusable_snapshot.source_generation is not None
        ):
            return cast(str, reusable_snapshot.source_generation)
    existing = _lease_with_optional_deadline(
        lease_existing_snapshot, project_root, deadline
    )
    with existing as existing_snapshot:
        if existing_snapshot.source_generation is not None:
            return cast(str, existing_snapshot.source_generation)
    # An unusable index is not authoritative for source-only consumers.
    current = capture_current_source_snapshot(project_root, deadline=deadline)
    if current.state != "exact" or current.generation is None:
        raise SourceOracleError(current.reason or "DIFF_SNAPSHOT_SOURCE_CHANGED")
    return current.generation


def _lease_with_optional_deadline(
    lease: Callable[..., Any], project_root: str, deadline: float
) -> Any:
    if "deadline" in inspect.signature(lease).parameters:
        return lease(project_root, deadline=deadline)
    return lease(project_root)
