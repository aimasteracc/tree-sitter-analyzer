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


def test_understand_accepts_task_text_only() -> None:
    assert UnderstandRequest(task="explain dispatch").task == "explain dispatch"
    with pytest.raises(ValueError, match="task must not be empty"):
        UnderstandRequest()
    # RFC-0022: understand(diff) is invalid — the model has no diff field.
    import dataclasses

    assert "diff" not in dataclasses.fields(UnderstandRequest)


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


def test_task_outcome_uses_rfc_verdict_vocabulary() -> None:
    from tree_sitter_analyzer.task.models import CANONICAL_VERDICTS

    assert CANONICAL_VERDICTS == {
        "SAFE",
        "CAUTION",
        "REVIEW",
        "UNSAFE",
        "INFO",
        "WARN",
        "NOT_FOUND",
        "ERROR",
    }
    outcome = TaskOutcome(
        task="understand", request=UnderstandRequest(task="x"), verdict="SAFE"
    )
    assert outcome.verdict == "SAFE"
    with pytest.raises(ValueError, match="not in canonical set"):
        TaskOutcome(
            task="understand",
            request=UnderstandRequest(task="x"),
            verdict="OK",
        )  # RFC verdicts only — OK/PARTIAL are statuses, not verdicts


def test_task_outcome_error_forces_verdict_error() -> None:
    TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="x"),
        verdict="ERROR",
        error="boom",
    )
    with pytest.raises(ValueError, match="must be verdict=ERROR"):
        TaskOutcome(
            task="understand",
            request=UnderstandRequest(task="x"),
            verdict="WARN",
            error="boom",
        )
    with pytest.raises(ValueError, match="forbidden without an error"):
        TaskOutcome(
            task="understand",
            request=UnderstandRequest(task="x"),
            verdict="ERROR",
        )


def test_task_outcome_status_vocabulary() -> None:
    assert (
        TaskOutcome(
            task="understand",
            request=UnderstandRequest(task="x"),
            verdict="SAFE",
            status="complete",
        ).status
        == "complete"
    )
    with pytest.raises(ValueError, match="not in canonical set"):
        TaskOutcome(
            task="understand",
            request=UnderstandRequest(task="x"),
            verdict="SAFE",
            status="done",
        )


def test_task_text_boundaries() -> None:
    with pytest.raises(ValueError, match="task must be a string"):
        UnderstandRequest(task=123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must not contain NUL"):
        UnderstandRequest(task="bad\x00name")


def test_scope_paths_boundaries() -> None:
    from tree_sitter_analyzer.task.models import MAX_SCOPE_PATHS

    too_many = tuple(f"p{i}" for i in range(MAX_SCOPE_PATHS + 1))
    with pytest.raises(ValueError, match="exceeds"):
        DiffInput(source="workspace", scope_paths=too_many)
    with pytest.raises(ValueError, match="exceeds.*UTF-8 bytes"):
        DiffInput(source="workspace", scope_paths=("x" * 1025,))


def test_consumed_budget_cleanup_contract() -> None:
    with pytest.raises(ValueError, match="zero or one"):
        ConsumedBudget(
            primitive_calls=1, evidence_items=1, routing_wall_ms=1, cleanup_calls=2
        )
    with pytest.raises(ValueError, match="requires the stable error code"):
        ConsumedBudget(
            primitive_calls=1,
            evidence_items=1,
            routing_wall_ms=1,
            cleanup_status="failed",
        )
    ConsumedBudget(
        primitive_calls=1,
        evidence_items=1,
        routing_wall_ms=1,
        cleanup_status="failed",
        cleanup_error_code="DIFF_SNAPSHOT_CLEANUP_FAILED",
    )


def test_models_are_frozen_and_hashable() -> None:
    import dataclasses

    for cls in (
        Budget,
        DiffInput,
        UnderstandRequest,
        PlanChangeRequest,
        AssessChangeRequest,
        ConsumedBudget,
        TaskOutcome,
    ):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    budget = Budget(profile="compact")
    assert hash(budget) == hash(Budget(profile="compact"))


def test_scope_paths_total_bytes_boundary() -> None:
    # RFC-0022: 128 entries x 256 bytes each stays under the 32768 total.
    many = tuple(f"p{i}" + "x" * 250 for i in range(128))
    assert len(DiffInput(source="workspace", scope_paths=many).scope_paths) == 128
    with pytest.raises(ValueError, match="exceed .* total bytes"):
        DiffInput(source="workspace", scope_paths=("x" * 1024,) * 33)


def test_request_rejects_non_budget_budget() -> None:
    with pytest.raises(ValueError, match="budget must be a frozen Budget"):
        UnderstandRequest(task="x", budget="standard")  # type: ignore[arg-type]


def test_task_text_exceeding_max_bytes_rejected() -> None:
    with pytest.raises(ValueError, match="exceeds .* UTF-8 bytes"):
        UnderstandRequest(task="x" * 16_385)


def test_assess_change_diff_runs_budget_floor() -> None:
    # L181 coverage: the diff floor runs on the assess route too.
    AssessChangeRequest(diff=DiffInput("workspace"))
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        AssessChangeRequest(
            diff=DiffInput("workspace"),
            budget=Budget(profile="standard", max_primitive_calls=2),
        )


def test_consumed_budget_negative_durations_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        ConsumedBudget(primitive_calls=1, evidence_items=1, routing_wall_ms=-1)
    with pytest.raises(ValueError, match="cleanup_wall_ms must be non-negative"):
        ConsumedBudget(
            primitive_calls=1, evidence_items=1, routing_wall_ms=1, cleanup_wall_ms=-1
        )


def test_consumed_budget_unknown_cleanup_status_rejected() -> None:
    with pytest.raises(ValueError, match="unknown cleanup_status"):
        ConsumedBudget(
            primitive_calls=1,
            evidence_items=1,
            routing_wall_ms=1,
            cleanup_status="pending",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="must be null or"):
        ConsumedBudget(
            primitive_calls=1,
            evidence_items=1,
            routing_wall_ms=1,
            cleanup_error_code="OTHER",
        )


def test_task_outcome_unknown_task_name_rejected() -> None:
    with pytest.raises(ValueError, match="unknown task name"):
        TaskOutcome(  # type: ignore[arg-type]
            task="explain",
            request=UnderstandRequest(task="x"),
            verdict="SAFE",
        )


def test_task_outcome_rejects_non_consumed_budget() -> None:
    with pytest.raises(ValueError, match="consumed must be a frozen ConsumedBudget"):
        TaskOutcome(
            task="understand",
            request=UnderstandRequest(task="x"),
            verdict="SAFE",
            consumed={"primitive_calls": 1},  # type: ignore[arg-type]
        )


def test_plan_change_task_text_path_runs_validator() -> None:
    # L271/273 coverage: the task-text branch of the one-of validator.
    assert PlanChangeRequest(task="refactor dispatch").task == "refactor dispatch"
    with pytest.raises(ValueError, match="exactly one of task or diff"):
        PlanChangeRequest()


def test_task_outcome_rejects_non_dict_wire_fields() -> None:
    base = {
        "task": "understand",
        "request": UnderstandRequest(task="x"),
        "verdict": "INFO",
    }
    with pytest.raises(ValueError, match="subject must be a dict"):
        TaskOutcome(**base, subject=["task"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="artifacts must be a dict"):
        TaskOutcome(**base, artifacts=())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="budget and truncation must be dicts"):
        TaskOutcome(**base, budget=[])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="agent_summary must be a dict"):
        TaskOutcome(**base, agent_summary=[])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="next_step must be a string or null"):
        TaskOutcome(**base, next_step=3)  # type: ignore[arg-type]


def test_task_outcome_rejects_malformed_collections() -> None:
    base = {
        "task": "understand",
        "request": UnderstandRequest(task="x"),
        "verdict": "INFO",
    }
    with pytest.raises(ValueError, match="claims must be a tuple of dicts"):
        TaskOutcome(**base, claims=({"id": 1}, "junk"))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="evidence must be a tuple of dicts"):
        TaskOutcome(**base, evidence=("junk",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="errors must be a tuple of strings"):
        TaskOutcome(**base, errors=("OK", 1))  # type: ignore[arg-type]


def test_task_outcome_success_must_match_verdict() -> None:
    with pytest.raises(ValueError, match="contradicts verdict"):
        TaskOutcome(
            task="understand",
            request=UnderstandRequest(task="x"),
            verdict="SAFE",
            success=False,
        )
    with pytest.raises(ValueError, match="contradicts verdict"):
        TaskOutcome(
            task="understand",
            request=UnderstandRequest(task="x"),
            verdict="ERROR",
            error="boom",
            success=True,
        )


def test_builders_produce_fixed_wire_shapes() -> None:
    from tree_sitter_analyzer.task import (
        build_artifacts,
        build_budget_record,
        build_subject_diff,
        build_subject_task,
    )

    assert build_subject_task() == {"task": None}
    assert build_subject_diff("workspace", "ds_1", ["a.py"]) == {
        "diff": {
            "source": "workspace",
            "snapshot_id": "ds_1",
            "changed_paths": ["a.py"],
        }
    }
    budget = Budget(profile="compact")
    assert build_budget_record(budget)["effective_calls"] == 4
    artifacts = build_artifacts(
        relevant_symbols=["s"],
        relevant_paths=["p"],
        plan_steps=[],
        verification=[],
        edge_collections=None,
    )
    assert artifacts["edge_collections"] == []
    assert artifacts["relevant_paths"] == ["p"]
