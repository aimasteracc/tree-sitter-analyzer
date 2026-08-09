"""Immutable fail-all orchestration for NO1-008A setup qualification."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.setup_qualification import (
    EXPECTED_CELLS,
    ZERO_COUNTERS,
    _bytes_hash,
    _write_exclusive,
)


def orchestrate_qualification(
    *,
    experiment_root: Path,
    producer: Callable[[str, str, Path], Mapping[str, Any]],
) -> dict[str, Any]:
    """Run exactly 14 immutable cells, collect every failure, and fail all."""

    experiment_root.mkdir(parents=True, exist_ok=False)
    _write_exclusive(
        experiment_root / "plan.json",
        {"schema_version": 1, "cells": EXPECTED_CELLS, "counters": ZERO_COUNTERS},
    )
    cells, failures = [], []
    for repo_id, arm_id in EXPECTED_CELLS:
        cell_root = experiment_root / "cells" / f"{repo_id}--{arm_id}"
        try:
            cells.append(dict(producer(repo_id, arm_id, cell_root)))
        except Exception as exc:  # noqa: BLE001 - fail-all evidence records every cell
            failures.append(
                {
                    "repo_id": repo_id,
                    "arm_id": arm_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    verdict = {
        "schema_version": 1,
        "status": "BLOCKED" if failures else "QUALIFIED",
        "publishable": False,
        "winner": None,
        "dominance_allowed": False,
        "expected_cells": 14,
        "observed_receipts": len(cells),
        "failures": failures,
        "counters": dict(ZERO_COUNTERS),
    }
    _write_exclusive(experiment_root / "verdict.json", verdict)
    _write_exclusive(
        experiment_root / "checksums.json",
        {
            path.relative_to(experiment_root).as_posix(): _bytes_hash(path.read_bytes())
            for path in sorted(experiment_root.rglob("*.json"))
        },
    )
    return verdict
