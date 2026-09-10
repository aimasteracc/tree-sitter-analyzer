"""RFC-0022 task-outcome/v1 internal models (Phase A, experiment only).

Frozen value objects for the three task outcomes. This package is
deliberately internal: no MCP facade, no CLI flags, no codemap surface
(RFC-0022 §Public surface: Phase A is internal experiment only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Profile = Literal["compact", "standard"]
TaskName = Literal["understand", "plan_change", "assess_change"]
Verdict = Literal[
    "SAFE", "CAUTION", "REVIEW", "UNSAFE", "INFO", "WARN", "NOT_FOUND", "ERROR"
]
Status = Literal["complete", "partial", "unknown"]

BUDGET_PROFILES: dict[Profile, tuple[int, int, int]] = {
    # profile -> (max_primitive_calls, max_evidence_items, routing_deadline_ms)
    "compact": (4, 15, 5_000),
    "standard": (12, 50, 30_000),
}

#: RFC-0022 fixed wire verdict vocabulary (strict clients reject unknown values).
CANONICAL_VERDICTS: frozenset[str] = frozenset(
    {"SAFE", "CAUTION", "REVIEW", "UNSAFE", "INFO", "WARN", "NOT_FOUND", "ERROR"}
)

#: RFC-0022 fixed wire status vocabulary.
CANONICAL_STATUSES: frozenset[str] = frozenset({"complete", "partial", "unknown"})

#: RFC-0022 boundary limits (§Fixed task-outcome/v1 semantics).
MAX_SCOPE_PATHS = 128
MAX_SCOPE_PATH_BYTES = 1024
MAX_SCOPE_TOTAL_BYTES = 32_768
MAX_TASK_BYTES = 16_384

_BUDGET_FIELD_NAMES = (
    "max_primitive_calls",
    "max_evidence_items",
    "routing_deadline_ms",
)


@dataclass(frozen=True)
class Budget:
    """One pinned routing budget for a task-outcome request.

    Explicit values may only lower a profile value; raising one is
    BUDGET_INVALID and rejected before any primitive call (RFC-0022
    §Internal Python contract).
    """

    profile: Profile = "standard"
    max_primitive_calls: int | None = None
    max_evidence_items: int | None = None
    routing_deadline_ms: int | None = None

    def __post_init__(self) -> None:
        if self.profile not in BUDGET_PROFILES:
            raise ValueError(f"BUDGET_INVALID: unknown profile {self.profile!r}")
        pinned_calls, pinned_evidence, pinned_deadline = BUDGET_PROFILES[self.profile]
        for name, value, ceiling in (
            ("max_primitive_calls", self.max_primitive_calls, pinned_calls),
            ("max_evidence_items", self.max_evidence_items, pinned_evidence),
            ("routing_deadline_ms", self.routing_deadline_ms, pinned_deadline),
        ):
            if value is not None and (value < 1 or value > ceiling):
                raise ValueError(
                    f"BUDGET_INVALID: {name}={value} must be 1..{ceiling} "
                    f"for profile {self.profile!r}"
                )

    @property
    def effective_calls(self) -> int:
        ceiling = BUDGET_PROFILES[self.profile][0]
        return self.max_primitive_calls or ceiling

    @property
    def effective_evidence(self) -> int:
        ceiling = BUDGET_PROFILES[self.profile][1]
        return self.max_evidence_items or ceiling

    @property
    def effective_deadline_ms(self) -> int:
        ceiling = BUDGET_PROFILES[self.profile][2]
        return self.routing_deadline_ms or ceiling

    def require_calls(self, minimum: int) -> None:
        """Reject budgets below a routing floor (e.g. diff requests >= 3)."""
        if self.effective_calls < minimum:
            raise ValueError(
                f"BUDGET_INVALID: requires max_primitive_calls >= {minimum}, "
                f"got {self.effective_calls}"
            )


@dataclass(frozen=True)
class DiffInput:
    """A diff-based task input (diff is the only subject for two operations)."""

    source: Literal["workspace", "staged"]
    #: Passed unchanged only to ``edit.impact`` (RFC-0022 §Internal contract).
    scope_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source not in {"workspace", "staged"}:
            raise ValueError(f"unknown diff source {self.source!r}")
        if len(self.scope_paths) > MAX_SCOPE_PATHS:
            raise ValueError(f"scope_paths exceeds {MAX_SCOPE_PATHS} entries")
        total_bytes = 0
        for path in self.scope_paths:
            if type(path) is not str or not path:
                raise ValueError("scope_paths must be non-empty strings")
            raw = path.encode("utf-8")
            if len(raw) > MAX_SCOPE_PATH_BYTES:
                raise ValueError(
                    f"scope path exceeds {MAX_SCOPE_PATH_BYTES} UTF-8 bytes"
                )
            total_bytes += len(raw)
        if total_bytes > MAX_SCOPE_TOTAL_BYTES:
            raise ValueError(f"scope_paths exceed {MAX_SCOPE_TOTAL_BYTES} total bytes")


@dataclass(frozen=True)
class TaskRequest:
    """Common request fields for the three task outcomes."""

    budget: Budget = field(default_factory=Budget)

    def __post_init__(self) -> None:
        if type(self.budget) is not Budget:
            raise ValueError("budget must be a frozen Budget")


def _validate_task_text(task: str) -> None:
    """Bound untrusted task text (RFC-0022: 1..16384 UTF-8 bytes, no NUL)."""
    if type(task) is not str:
        raise ValueError("task must be a string")
    if not task.strip():
        raise ValueError("task must not be empty")
    raw = task.encode("utf-8")
    if len(raw) > MAX_TASK_BYTES:
        raise ValueError(f"task exceeds {MAX_TASK_BYTES} UTF-8 bytes")
    if "\x00" in task:
        raise ValueError("task must not contain NUL")


@dataclass(frozen=True)
class UnderstandRequest(TaskRequest):
    #: RFC-0022: understand(diff) is invalid — task text only.
    task: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        _validate_task_text(self.task)


@dataclass(frozen=True)
class PlanChangeRequest(TaskRequest):
    task: str = ""
    diff: DiffInput | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        _validate_task_or_diff(self.task, self.diff)
        if self.diff is not None:
            self.budget.require_calls(3)


@dataclass(frozen=True)
class AssessChangeRequest(TaskRequest):
    diff: DiffInput | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.diff is None:
            raise ValueError("assess_change requires exactly one diff")
        self.budget.require_calls(3)


@dataclass(frozen=True)
class ConsumedBudget:
    """Reported primitive accounting (RFC-0022 §Budget and truncation).

    ``routing_deadline_ms`` is a routing deadline, not a wall-time SLA:
    ``routing_wall_ms`` may exceed it, with ``deadline_overrun_ms`` reported
    exactly. Cleanup accounting is fixed per RFC: the host records the four
    cleanup fields after the unconditional release runs in an outer finally.
    """

    primitive_calls: int
    evidence_items: int
    routing_wall_ms: int
    deadline_overrun_ms: int = 0
    cleanup_calls: int = 0
    cleanup_wall_ms: int = 0
    cleanup_status: Literal["not_required", "succeeded", "failed"] = "not_required"
    cleanup_error_code: str | None = None

    def __post_init__(self) -> None:
        if self.primitive_calls < 0 or self.evidence_items < 0:
            raise ValueError("consumed counters must be non-negative")
        if self.routing_wall_ms < 0 or self.deadline_overrun_ms < 0:
            raise ValueError("consumed durations must be non-negative")
        if self.cleanup_calls not in {0, 1}:
            raise ValueError("cleanup_calls must be zero or one")
        if self.cleanup_wall_ms < 0:
            raise ValueError("cleanup_wall_ms must be non-negative")
        if self.cleanup_status not in {"not_required", "succeeded", "failed"}:
            raise ValueError(f"unknown cleanup_status {self.cleanup_status!r}")
        if self.cleanup_error_code not in {
            None,
            "DIFF_SNAPSHOT_CLEANUP_FAILED",
        }:
            raise ValueError(
                f"cleanup_error_code must be null or DIFF_SNAPSHOT_CLEANUP_FAILED, "
                f"got {self.cleanup_error_code!r}"
            )
        if self.cleanup_status == "failed" and self.cleanup_error_code is None:
            raise ValueError("failed cleanup requires the stable error code")


#: Fixed scalar replacing raw task text in every frozen model, hash, and
#: provenance record (RFC-0022 §Fixed task-outcome/v1 semantics: the frozen
#: model contains no raw or normalized task field).
TASK_TEXT_OMITTED = "TASK_TEXT_OMITTED"

#: Fixed wire fragment vocabularies (RFC-0022 route decision table).
PLAN_STEP_KINDS = frozenset(
    {
        "inspect_context",
        "check_file_safety",
        "review_changed_file",
        "check_constraint",
        "review_structure",
        "review_classification",
    }
)
CLAIM_ASSERTIONS = frozenset({"supported", "contradicted", "unknown"})

#: Canonical verdict severity order (RFC-0022 §Static verification truth
#: table): UNSAFE > WARN > REVIEW > CAUTION > SAFE > INFO > NOT_FOUND.
VERDICT_SEVERITY: dict[str, int] = {
    "UNSAFE": 7,
    "WARN": 6,
    "REVIEW": 5,
    "CAUTION": 4,
    "SAFE": 3,
    "INFO": 2,
    "NOT_FOUND": 1,
    "ERROR": 0,
}


def _require_tuple_of_dicts(value: object, name: str) -> None:
    if type(value) is not tuple or any(type(item) is not dict for item in value):
        raise ValueError(f"{name} must be a tuple of dicts")


def _require_tuple_of_strings(value: object, name: str) -> None:
    if type(value) is not tuple or any(type(item) is not str for item in value):
        raise ValueError(f"{name} must be a tuple of strings")


@dataclass(frozen=True)
class TaskOutcome:
    """One task-outcome/v1 result (frozen; serializer must be deterministic).

    RFC-0022 fixed wire: ``status`` (complete|partial|unknown) is separate
    from ``verdict`` (SAFE|CAUTION|REVIEW|UNSAFE|INFO|WARN|NOT_FOUND|ERROR).
    A failed outcome is always ``success=false`` and ``verdict=ERROR``;
    ``ERROR`` is forbidden when ``success=true``. Arrays stay present when
    empty; ``subject.task`` is always null (task text never frozen).
    """

    task: TaskName
    request: TaskRequest
    verdict: Verdict
    status: Status = "unknown"
    success: bool | None = None
    subject: dict[str, Any] = field(default_factory=dict)
    claims: tuple[dict[str, Any], ...] = ()
    artifacts: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[dict[str, Any], ...] = ()
    provenance: tuple[dict[str, Any], ...] = ()
    freshness: tuple[dict[str, Any], ...] = ()
    unknowns: tuple[dict[str, Any], ...] = ()
    errors: tuple[str, ...] = ()
    budget: dict[str, Any] = field(default_factory=dict)
    truncation: dict[str, Any] = field(default_factory=dict)
    next_step: str | None = None
    agent_summary: dict[str, Any] = field(default_factory=dict)
    consumed: ConsumedBudget | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.task not in {"understand", "plan_change", "assess_change"}:
            raise ValueError(f"unknown task name {self.task!r}")
        if self.verdict not in CANONICAL_VERDICTS:
            raise ValueError(
                f"verdict {self.verdict!r} not in canonical set "
                f"{sorted(CANONICAL_VERDICTS)}"
            )
        if self.status not in CANONICAL_STATUSES:
            raise ValueError(
                f"status {self.status!r} not in canonical set "
                f"{sorted(CANONICAL_STATUSES)}"
            )
        if self.error is not None:
            if self.verdict != "ERROR":
                raise ValueError("failed outcome must be verdict=ERROR")
        elif self.verdict == "ERROR":
            raise ValueError("verdict=ERROR is forbidden without an error")
        if self.success is None:
            object.__setattr__(self, "success", self.verdict != "ERROR")
        if self.success != (self.verdict != "ERROR"):
            raise ValueError(
                f"success={self.success} contradicts verdict={self.verdict}"
            )
        if type(self.consumed) not in {ConsumedBudget, type(None)}:
            raise ValueError("consumed must be a frozen ConsumedBudget")
        if type(self.subject) is not dict:
            raise ValueError("subject must be a dict")
        if type(self.artifacts) is not dict:
            raise ValueError("artifacts must be a dict")
        if type(self.budget) is not dict or type(self.truncation) is not dict:
            raise ValueError("budget and truncation must be dicts")
        if type(self.agent_summary) is not dict:
            raise ValueError("agent_summary must be a dict")
        if self.next_step is not None and type(self.next_step) is not str:
            raise ValueError("next_step must be a string or null")
        _require_tuple_of_dicts(self.claims, "claims")
        _require_tuple_of_dicts(self.evidence, "evidence")
        _require_tuple_of_dicts(self.provenance, "provenance")
        _require_tuple_of_dicts(self.freshness, "freshness")
        _require_tuple_of_dicts(self.unknowns, "unknowns")
        _require_tuple_of_strings(self.errors, "errors")


def build_subject_task() -> dict[str, Any]:
    """Task-mode subject: ``subject.task`` is always null (text never frozen)."""
    return {"task": None}


def build_subject_diff(
    source: str, snapshot_id: str, changed_paths: list[str]
) -> dict[str, Any]:
    """Fixed diff subject record (RFC-0022 §Fixed model)."""
    return {
        "diff": {
            "source": source,
            "snapshot_id": snapshot_id,
            "changed_paths": list(changed_paths),
        }
    }


def build_budget_record(budget: Budget) -> dict[str, Any]:
    """Fixed budget wire record (profile + explicit + effective values)."""
    return {
        "profile": budget.profile,
        "max_primitive_calls": budget.max_primitive_calls,
        "max_evidence_items": budget.max_evidence_items,
        "routing_deadline_ms": budget.routing_deadline_ms,
        "effective_calls": budget.effective_calls,
        "effective_evidence": budget.effective_evidence,
        "effective_deadline_ms": budget.effective_deadline_ms,
    }


def build_artifacts(
    *,
    relevant_symbols: list[str],
    relevant_paths: list[str],
    plan_steps: list[dict[str, Any]],
    verification: list[dict[str, Any]],
    edge_collections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fixed artifacts wire record (arrays stay present when empty)."""
    return {
        "relevant_symbols": list(relevant_symbols),
        "relevant_paths": list(relevant_paths),
        "plan_steps": list(plan_steps),
        "verification": list(verification),
        "edge_collections": list(edge_collections or []),
    }


def _validate_task_or_diff(task: str, diff: DiffInput | None) -> None:
    """Exactly one of task/diff must be supplied (RFC-0022 §Internal contract)."""
    has_task = bool(task.strip()) if type(task) is str else True
    has_diff = diff is not None
    if has_task == has_diff:
        raise ValueError("task request must have exactly one of task or diff")
    if has_task:
        _validate_task_text(task)
