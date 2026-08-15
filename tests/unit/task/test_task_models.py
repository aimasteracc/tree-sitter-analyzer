"""RFC-0022 task-outcome/v1 model and budget contracts (Phase A).

Exact pins for the frozen models, budget profiles, and boundary rules
(RFC-0022 RED-first acceptance items 3-4 groundwork).
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.task import (
    BUDGET_PROFILES,
    AssessChangeRequest,
    Budget,
    ConsumedBudget,
    DiffInput,
    PlanChangeRequest,
    TaskOutcome,
    UnderstandRequest,
)


def test_budget_profiles_are_pinned_exactly() -> None:
    assert BUDGET_PROFILES == {
        "compact": (4, 15, 5_000),
        "standard": (12, 50, 30_000),
    }


def test_budget_defaults_to_standard_profile() -> None:
    budget = Budget()
    assert budget.profile == "standard"
    assert budget.effective_calls == 12
    assert budget.effective_evidence == 50
    assert budget.effective_deadline_ms == 30_000


def test_budget_compact_effective_values() -> None:
    budget = Budget(profile="compact")
    assert budget.effective_calls == 4
    assert budget.effective_evidence == 15
    assert budget.effective_deadline_ms == 5_000


def test_budget_explicit_values_may_only_lower() -> None:
    assert Budget(profile="compact", max_primitive_calls=2).effective_calls == 2
    assert Budget(profile="standard", max_evidence_items=20).effective_evidence == 20
    assert (
        Budget(profile="standard", routing_deadline_ms=10_000).effective_deadline_ms
        == 10_000
    )


def test_budget_rejects_raising_explicit_value() -> None:
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        Budget(profile="compact", max_primitive_calls=5)
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        Budget(profile="standard", max_evidence_items=60)


def test_budget_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        Budget(profile="wide")  # type: ignore[arg-type]


def test_budget_require_calls_rejects_below_floor() -> None:
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        Budget(profile="standard", max_primitive_calls=2).require_calls(3)
    Budget(profile="compact").require_calls(3)  # compact 4 >= 3 is fine


def test_diff_input_requires_valid_source() -> None:
    assert DiffInput(source="workspace").source == "workspace"
    assert DiffInput(source="staged").source == "staged"
    with pytest.raises(ValueError, match="unknown diff source"):
        DiffInput(source="mixed")  # type: ignore[arg-type]


def test_diff_input_rejects_empty_scope_paths() -> None:
    with pytest.raises(ValueError, match="non-empty strings"):
        DiffInput(source="workspace", scope_paths=("",))


def test_understand_requires_exactly_one_task_or_diff() -> None:
    assert UnderstandRequest(task="explain dispatch").task == "explain dispatch"
    assert UnderstandRequest(diff=DiffInput("staged")).diff is not None
    with pytest.raises(ValueError, match="exactly one of task or diff"):
        UnderstandRequest()
    with pytest.raises(ValueError, match="exactly one of task or diff"):
        UnderstandRequest(task="x", diff=DiffInput("workspace"))


def test_plan_change_diff_requires_three_calls_floor() -> None:
    PlanChangeRequest(diff=DiffInput("workspace"))  # standard 12 >= 3
    PlanChangeRequest(  # compact 4 >= 3 is fine
        diff=DiffInput("workspace"), budget=Budget(profile="compact")
    )
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        PlanChangeRequest(
            diff=DiffInput("workspace"),
            budget=Budget(profile="standard", max_primitive_calls=2),
        )


def test_assess_change_requires_diff() -> None:
    with pytest.raises(ValueError, match="exactly one diff"):
        AssessChangeRequest()


def test_consumed_budget_rejects_negative_counters() -> None:
    ConsumedBudget(primitive_calls=3, evidence_items=10, routing_wall_ms=100)
    with pytest.raises(ValueError, match="non-negative"):
        ConsumedBudget(primitive_calls=-1, evidence_items=0, routing_wall_ms=0)


def test_task_outcome_requires_canonical_verdict_without_error() -> None:
    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="x"),
        verdict="OK",
    )
    assert outcome.verdict == "OK"
    with pytest.raises(ValueError, match="canonical verdict"):
        TaskOutcome(
            task="understand",
            request=UnderstandRequest(task="x"),
            verdict="FANCY",
        )
    # error outcomes may carry any verdict
    TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="x"),
        verdict="ERROR",
        error="boom",
    )


def test_models_are_frozen_and_hashable() -> None:
    import dataclasses

    for cls in (Budget, DiffInput, UnderstandRequest, PlanChangeRequest, TaskOutcome):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    budget = Budget(profile="compact")
    assert hash(budget) == hash(Budget(profile="compact"))
