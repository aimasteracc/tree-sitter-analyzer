"""RFC-0022 plan-steps projection (Phase A).

The table-driven projection from RFC-0022 §Complete V1 route decision table:
``plan_steps`` are read-only preparation/review steps, not edit instructions
or implementation authorization. Each step has exactly
``{ordinal, kind, path, symbol, evidence_ids}``. The projection emits one
step per successful exact primitive fragment in this group order, then sorts
within a group by ``(path|nulls-first, symbol|nulls-first, locator)`` and
assigns 1-based ordinals.

Fields are copied, never inferred; ``evidence_ids`` contains only that
fragment's ID. Failed, malformed, ``NO_CONFIG``, and omitted fragments emit
no step and are represented by ``unknowns``/status. ``assess_change`` uses
the same route but leaves ``plan_steps=[]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Fixed step kinds per route fragment (RFC-0022 plan_steps table).
STEP_KINDS: dict[str, str] = {
    "nav.context": "inspect_context",
    "edit.safe": "check_file_safety",
    "edit.impact": "review_changed_file",
    "edit.constraints": "check_constraint",
    "edit.ast_diff": "review_structure",
    "edit.classify": "review_classification",
}

#: Group order: steps emit in this order, sorted within each group.
_GROUP_ORDER: dict[str, int] = {
    "nav.context": 0,
    "edit.safe": 1,
    "edit.impact": 2,
    "edit.constraints": 3,
    "edit.ast_diff": 4,
    "edit.classify": 5,
}


@dataclass(frozen=True)
class StepFragment:
    """One successful exact primitive fragment eligible for a plan step."""

    route: str  # "nav.context" | "edit.safe" | "impact" | "constraints" | ...
    path: str | None
    symbol: str | None
    locator: str | None
    evidence_id: str | None


def project_plan_steps(fragments: list[StepFragment]) -> list[dict[str, Any]]:
    """Emit ordered plan_steps from successful fragments.

    Groups emit in fixed route order; within a group, fragments sort by
    ``(path|nulls-first, symbol|nulls-first, locator)``. Ordinals are
    1-based over the emitted list. A fragment without an evidence ID is a
    failed/malformed contribution and emits no step.
    """
    with_evidence = [f for f in fragments if f.evidence_id is not None]
    grouped: dict[int, list[StepFragment]] = {}
    for fragment in with_evidence:
        order = _GROUP_ORDER.get(fragment.route)
        if order is None:  # pragma: no cover - guarded by router
            continue
        grouped.setdefault(order, []).append(fragment)
    steps: list[dict[str, Any]] = []
    for order in sorted(grouped):
        for fragment in sorted(
            grouped[order],
            key=lambda f: (
                f.path is not None,
                f.path or "",
                f.symbol is not None,
                f.symbol or "",
                f.locator or "",
            ),
        ):
            steps.append(
                {
                    "ordinal": len(steps) + 1,
                    "kind": STEP_KINDS[fragment.route],
                    "path": fragment.path,
                    "symbol": fragment.symbol,
                    "evidence_ids": [fragment.evidence_id],
                }
            )
    return steps
