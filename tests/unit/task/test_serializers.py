"""RFC-0022 task-outcome/v1 serializer determinism and cost invariants (Phase A).

RFC-0022 §Determinism + §Executable value and cost invariants: JSON
roundtrip identity, exact byte pins on one frozen fixture, compact < standard.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.task import (
    AssessChangeRequest,
    Budget,
    ConsumedBudget,
    DiffInput,
    PlanChangeRequest,
    TaskOutcome,
    UnderstandRequest,
)
from tree_sitter_analyzer.task.serializers import (
    decode_json,
    serialize_json,
)


def _frozen_understand() -> TaskOutcome:
    return TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="explain dispatch"),
        verdict="SAFE",
        status="complete",
        evidence=(
            {
                "evidence": "evidence:abc123",
                "locator": "src/app.py",
                "summary": "entry point",
            },
        ),
        consumed=ConsumedBudget(
            primitive_calls=2,
            evidence_items=1,
            routing_wall_ms=120,
            deadline_overrun_ms=0,
        ),
    )


def _frozen_plan_diff() -> TaskOutcome:
    return TaskOutcome(
        task="plan_change",
        request=PlanChangeRequest(
            diff=DiffInput(source="staged", scope_paths=("src/", "tests/")),
            budget=Budget(profile="compact"),
        ),
        verdict="CAUTION",
        status="partial",
        evidence=(),
        consumed=ConsumedBudget(
            primitive_calls=3,
            evidence_items=4,
            routing_wall_ms=2_400,
            cleanup_calls=1,
            cleanup_wall_ms=15,
            cleanup_status="succeeded",
        ),
    )


def test_json_serialization_is_deterministic() -> None:
    outcome = _frozen_understand()
    assert serialize_json(outcome) == serialize_json(outcome)


def test_json_roundtrip_is_identity() -> None:
    outcome = _frozen_understand()
    assert decode_json(serialize_json(outcome)) == outcome


def test_compact_bytes_are_strictly_less_than_standard() -> None:
    # Same request semantics, different profile: the profile name and its
    # pinned ceilings are the only difference, so compact must be smaller.
    base = _frozen_plan_diff().request
    compact = TaskOutcome(
        task="plan_change",
        request=PlanChangeRequest(
            task=base.task,
            diff=DiffInput(source="staged", scope_paths=("src/", "tests/")),
            budget=Budget(profile="compact"),
        ),
        verdict="CAUTION",
        status="partial",
    )
    standard = TaskOutcome(
        task="plan_change",
        request=PlanChangeRequest(
            task=base.task,
            diff=DiffInput(source="staged", scope_paths=("src/", "tests/")),
            budget=Budget(profile="standard"),
        ),
        verdict="CAUTION",
        status="partial",
    )
    compact_bytes = len(serialize_json(compact).encode("utf-8"))
    standard_bytes = len(serialize_json(standard).encode("utf-8"))
    assert compact_bytes < standard_bytes


def test_serializers_reject_unknown_request_kind() -> None:
    import json

    from tree_sitter_analyzer.task.serializers import _dict_to_outcome

    payload = json.loads(serialize_json(_frozen_understand()))
    payload["request"]["kind"] = "unknown"
    with pytest.raises(ValueError, match="unknown request kind"):
        _dict_to_outcome(payload)


def test_exact_json_bytes_pin_frozen_fixture() -> None:
    # W1 (review #1268): real absolute pin, not a tautology.
    outcome = _frozen_understand()
    assert len(serialize_json(outcome).encode("utf-8")) == 961


def test_decode_rejects_unknown_fields() -> None:
    # W2 (review #1268): strict clients reject unknown values.
    import json

    payload = json.loads(serialize_json(_frozen_understand()))
    payload["sneaky"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        decode_json(json.dumps(payload))
    payload = json.loads(serialize_json(_frozen_understand()))
    payload["request"]["budget"]["sneaky"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        decode_json(json.dumps(payload))


def test_plan_change_task_request_roundtrip() -> None:
    # Covers the PlanChangeRequest task-branch and assess_change dict paths.
    outcome = TaskOutcome(
        task="plan_change",
        request=PlanChangeRequest(task="refactor dispatch"),
        verdict="SAFE",
    )
    assert decode_json(serialize_json(outcome)) == outcome


def test_assess_change_request_roundtrip() -> None:
    # Covers the AssessChangeRequest serializer branch.
    outcome = TaskOutcome(
        task="assess_change",
        request=AssessChangeRequest(diff=DiffInput(source="workspace")),
        verdict="WARN",
        status="partial",
    )
    assert decode_json(serialize_json(outcome)) == outcome


def test_decode_wire_with_plan_steps_validates_step_shape() -> None:
    import json

    outcome = TaskOutcome(
        task="plan_change",
        request=PlanChangeRequest(task="refactor x"),
        verdict="WARN",
        status="partial",
        artifacts={
            "relevant_symbols": ["sym"],
            "relevant_paths": ["src/a.py"],
            "plan_steps": [
                {
                    "ordinal": 1,
                    "kind": "check_file_safety",
                    "path": "src/a.py",
                    "symbol": None,
                    "evidence_ids": ["evidence:e1"],
                }
            ],
            "verification": [],
            "edge_collections": [],
        },
    )
    wire = json.loads(serialize_json(outcome))
    assert decode_json(json.dumps(wire)) == outcome
    wire["artifacts"]["plan_steps"][0]["sneaky"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        decode_json(json.dumps(wire))


def test_decoder_rejects_missing_required_wire_fields() -> None:
    import json

    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="x"),
        verdict="INFO",
    )
    wire = json.loads(serialize_json(outcome))
    for field in (
        "subject",
        "artifacts",
        "budget",
        "truncation",
        "claims",
        "provenance",
        "freshness",
        "unknowns",
        "errors",
        "success",
        "operation",
        "next_step",
        "agent_summary",
    ):
        trimmed = dict(wire)
        del trimmed[field]
        with pytest.raises(ValueError, match="missing required fields"):
            decode_json(json.dumps(trimmed))
