"""Certified ordinary read-only execution for architectural constraints."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def run_read_only(
    tool: Any,
    db_path: Path,
    constraints: list[Any],
    *,
    path_filter: str,
    min_severity_rank: int,
    scope_paths: frozenset[str] | None = None,
    evaluator: Any = None,
    deadline: float | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Evaluate one certified private snapshot without project writes."""
    from .constraint_index_snapshot import evaluate_ordinary_snapshot

    del db_path
    absolute_deadline = time.monotonic() + 10.0 if deadline is None else deadline
    if time.monotonic() >= absolute_deadline:
        raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")
    return evaluate_ordinary_snapshot(
        tool,
        constraints,
        path_filter=path_filter,
        min_severity_rank=min_severity_rank,
        scope_paths=scope_paths,
        evaluator=evaluator,
        deadline=absolute_deadline,
    )
