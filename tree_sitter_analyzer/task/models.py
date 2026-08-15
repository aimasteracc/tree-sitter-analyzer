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

BUDGET_PROFILES: dict[Profile, tuple[int, int, int]] = {
    # profile -> (max_primitive_calls, max_evidence_items, routing_deadline_ms)
    "compact": (4, 15, 5_000),
    "standard": (12, 50, 30_000),
}

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
    """A diff-based task input (exactly one of task/diff per request)."""

    source: Literal["workspace", "staged"]
    #: Passed unchanged only to ``edit.impact`` (RFC-0022 §Internal contract).
    scope_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source not in {"workspace", "staged"}:
            raise ValueError(f"unknown diff source {self.source!r}")
        if any(type(path) is not str or not path for path in self.scope_paths):
            raise ValueError("scope_paths must be non-empty strings")


@dataclass(frozen=True)
class TaskRequest:
    """Common request fields for the three task outcomes."""

    budget: Budget = field(default_factory=Budget)

    def __post_init__(self) -> None:
        # Force the frozen contract: subclasses re-validate their own fields.
        if type(self.budget) is not Budget:
            raise ValueError("budget must be a frozen Budget")


@dataclass(frozen=True)
class UnderstandRequest(TaskRequest):
    task: str = ""
    diff: DiffInput | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        _validate_task_or_diff(self.task, self.diff)


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
    """Reported primitive accounting (RFC-0022 §Budget and truncation)."""

    primitive_calls: int
    evidence_items: int
    routing_wall_ms: int
    deadline_overrun_ms: int = 0

    def __post_init__(self) -> None:
        if self.primitive_calls < 0 or self.evidence_items < 0:
            raise ValueError("consumed counters must be non-negative")
        if self.routing_wall_ms < 0 or self.deadline_overrun_ms < 0:
            raise ValueError("consumed durations must be non-negative")


@dataclass(frozen=True)
class TaskOutcome:
    """One task-outcome/v1 result (frozen; serializer must be deterministic)."""

    task: TaskName
    request: TaskRequest
    verdict: str
    evidence: tuple[dict[str, Any], ...] = ()
    consumed: ConsumedBudget | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.task not in {"understand", "plan_change", "assess_change"}:
            raise ValueError(f"unknown task name {self.task!r}")
        if self.error is None and self.verdict not in {"OK", "PARTIAL", "NOT_FOUND"}:
            raise ValueError(
                f"non-error outcome requires canonical verdict, got {self.verdict!r}"
            )


def _validate_task_or_diff(task: str, diff: DiffInput | None) -> None:
    """Exactly one of task/diff must be supplied (RFC-0022 §Internal contract)."""
    has_task = bool(task.strip())
    has_diff = diff is not None
    if has_task == has_diff:
        raise ValueError("task request must have exactly one of task or diff")
    if has_task and not isinstance(task, str):
        raise ValueError("task must be a string")
