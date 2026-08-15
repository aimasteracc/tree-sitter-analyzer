"""RFC-0022 task-outcome/v1 package (Phase A, internal experiment only).

Not registered as an MCP facade, CLI command, or codemap surface
(RFC-0022 §Public surface: Phase A — internal experiment only).
"""

from __future__ import annotations

from .evidence import (
    EvidenceInput,
    SourceSnapshotRecord,
    evidence_identity,
    normalized_result_hash,
)
from .freshness import FRESHNESS_STATES, SnapshotTruth
from .models import (
    BUDGET_PROFILES,
    AssessChangeRequest,
    Budget,
    ConsumedBudget,
    DiffInput,
    PlanChangeRequest,
    TaskOutcome,
    TaskRequest,
    UnderstandRequest,
)
from .route_table import ROUTE_TABLE, SAFE_FANOUT_CAPS, RouteRow

__all__ = [
    "AssessChangeRequest",
    "EvidenceInput",
    "FRESHNESS_STATES",
    "ROUTE_TABLE",
    "RouteRow",
    "SAFE_FANOUT_CAPS",
    "SnapshotTruth",
    "SourceSnapshotRecord",
    "evidence_identity",
    "normalized_result_hash",
    "Budget",
    "BUDGET_PROFILES",
    "ConsumedBudget",
    "DiffInput",
    "PlanChangeRequest",
    "TaskOutcome",
    "TaskRequest",
    "UnderstandRequest",
]
