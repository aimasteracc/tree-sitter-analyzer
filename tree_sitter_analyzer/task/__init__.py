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
    CLAIM_ASSERTIONS,
    PLAN_STEP_KINDS,
    TASK_TEXT_OMITTED,
    VERDICT_SEVERITY,
    AssessChangeRequest,
    Budget,
    ConsumedBudget,
    DiffInput,
    PlanChangeRequest,
    TaskOutcome,
    TaskRequest,
    UnderstandRequest,
    build_artifacts,
    build_budget_record,
    build_subject_diff,
    build_subject_task,
)
from .projection import STEP_KINDS, StepFragment, project_plan_steps
from .route_table import ROUTE_TABLE, SAFE_FANOUT_CAPS, RouteRow
from .router import PrimitiveExecutor, assess_change, plan_change, understand
from .truth_table import (
    FRESH,
    MISSING,
    NOT_APPLICABLE,
    UNKNOWN,
    Contribution,
    aggregate_status,
    aggregate_status_and_verdict,
    aggregate_verdict,
    contribute,
    degrade,
)

__all__ = [
    "AssessChangeRequest",
    "CLAIM_ASSERTIONS",
    "Contribution",
    "EvidenceInput",
    "FRESH",
    "FRESHNESS_STATES",
    "MISSING",
    "NOT_APPLICABLE",
    "PLAN_STEP_KINDS",
    "PrimitiveExecutor",
    "ROUTE_TABLE",
    "RouteRow",
    "SAFE_FANOUT_CAPS",
    "STEP_KINDS",
    "SnapshotTruth",
    "SourceSnapshotRecord",
    "TASK_TEXT_OMITTED",
    "UNKNOWN",
    "VERDICT_SEVERITY",
    "aggregate_status",
    "aggregate_status_and_verdict",
    "aggregate_verdict",
    "assess_change",
    "build_artifacts",
    "build_budget_record",
    "build_subject_diff",
    "build_subject_task",
    "contribute",
    "degrade",
    "evidence_identity",
    "normalized_result_hash",
    "plan_change",
    "project_plan_steps",
    "understand",
    "Budget",
    "BUDGET_PROFILES",
    "ConsumedBudget",
    "DiffInput",
    "PlanChangeRequest",
    "StepFragment",
    "TaskOutcome",
    "TaskRequest",
    "UnderstandRequest",
]
