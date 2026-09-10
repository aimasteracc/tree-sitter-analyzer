#!/usr/bin/env python3
"""Refactor-priority formula and queue ranking — RFC-0027 §L8 item 2.

The formula below lived only in ``.claude/skills/tsa-refactor-queue/SKILL.md``.
A formula that lives only in a prompt has no regression protection, so it is
here, in code, with exact-value tests in ``tests/unit/test_refactor_queue.py``.

Reading of the markdown chosen (SKILL.md "Step 2 — Score and rank")::

    priority = (1 - health_score / 100)
             * log(1 + mod_count_30d_for_file)
             * (dead_symbol_count / total_symbols + 0.1)

Two points the markdown leaves implicit, resolved here:

* ``log`` is the **natural** logarithm (:func:`math.log`). SKILL.md writes bare
  ``log(1 + x)`` and justifies it only as damping ("so a single 50x file doesn't
  dominate"), which holds for any base; natural log is the reading that needs no
  extra assumption and is what ``math.log`` gives by default.
* the ``+ 0.1`` floor is part of the formula, not a rounding artefact —
  SKILL.md states its purpose explicitly ("ensures non-dead files can still
  rank if churn+grade alone justify it"). It is exported as
  :data:`DEAD_RATIO_FLOOR` so callers cannot re-derive it wrongly.

Everything here is pure: no I/O, no index access. The signal *collection* lives
in :mod:`tree_sitter_analyzer.mcp.tools.refactor_queue_tool`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# SKILL.md: the floor that lets a churny F-grade file with no dead code rank.
DEAD_RATIO_FLOOR: float = 0.1

# Weakest-dimension → concrete action. SKILL.md Step 4 emits one of
# ``split`` / ``delete dead`` / ``extract``.
_DUPLICATION_DIMENSIONS: frozenset[str] = frozenset({"duplication"})

# Above this dead fraction, pruning is the cheapest first move regardless of
# which dimension dragged the grade down.
_DEAD_DOMINANT_RATIO: float = 0.5


@dataclass(frozen=True)
class RefactorQueueRow:
    """One candidate file with its three joined signals.

    ``health_score`` ∈ [0, 100] (from ``health action=project``),
    ``churn_30d`` = summed ``mod_count_30d`` across the file's symbols,
    ``dead_symbols`` / ``total_symbols`` = the dead fraction.
    """

    file_path: str
    grade: str
    health_score: float
    weakest_dimension: str
    churn_30d: int
    dead_symbols: int
    total_symbols: int


def refactor_priority(
    *,
    health_score: float,
    churn_30d: int,
    dead_symbols: int,
    total_symbols: int,
) -> float:
    """Return the SKILL.md refactor priority for one file.

    Raises:
        ValueError: on inputs outside the documented domains — a negative
            churn or an out-of-range health score is a caller bug, and
            silently clamping it would hide a broken signal join.
    """
    if not 0.0 <= health_score <= 100.0:
        raise ValueError(f"health_score must be in [0, 100], got {health_score!r}")
    if churn_30d < 0:
        raise ValueError(f"churn_30d must be >= 0, got {churn_30d!r}")
    if dead_symbols < 0:
        raise ValueError(f"dead_symbols must be >= 0, got {dead_symbols!r}")
    if total_symbols < 0:
        raise ValueError(f"total_symbols must be >= 0, got {total_symbols!r}")

    grade_weight = 1.0 - health_score / 100.0
    churn_weight = math.log(1 + churn_30d)
    dead_ratio = (dead_symbols / total_symbols) if total_symbols else 0.0
    return grade_weight * churn_weight * (dead_ratio + DEAD_RATIO_FLOOR)


def _action_for(row: RefactorQueueRow) -> str:
    """Map a row to the concrete first move (SKILL.md Step 4)."""
    dead_ratio = (row.dead_symbols / row.total_symbols) if row.total_symbols else 0.0
    if dead_ratio > _DEAD_DOMINANT_RATIO:
        return "delete dead"
    if row.weakest_dimension in _DUPLICATION_DIMENSIONS:
        return "extract"
    return "split"


def rank_refactor_queue(
    rows: list[RefactorQueueRow], top_n: int
) -> list[dict[str, Any]]:
    """Rank ``rows`` by :func:`refactor_priority`, descending, and take ``top_n``.

    Ties break on ``file_path`` ascending so the queue is byte-stable for a
    given index generation — an ordering that flips between calls is not a
    queue an agent can act on.
    """
    scored = [
        (
            refactor_priority(
                health_score=row.health_score,
                churn_30d=row.churn_30d,
                dead_symbols=row.dead_symbols,
                total_symbols=row.total_symbols,
            ),
            row,
        )
        for row in rows
    ]
    scored.sort(key=lambda pair: (-pair[0], pair[1].file_path))

    return [
        {
            "rank": position,
            "file_path": row.file_path,
            "grade": row.grade,
            "health_score": row.health_score,
            "weakest_dimension": row.weakest_dimension,
            "churn_30d": row.churn_30d,
            "dead_symbols": row.dead_symbols,
            "total_symbols": row.total_symbols,
            "priority": priority,
            "action": _action_for(row),
        }
        for position, (priority, row) in enumerate(scored[: max(top_n, 0)], start=1)
    ]
