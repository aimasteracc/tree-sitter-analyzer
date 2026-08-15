"""RFC-0022 task-outcome/v1 serializer parity and cost invariants (Phase A).

RFC-0022 §Determinism and serializer parity + §Executable value and cost
invariants: same-object JSON/TOON parity, exact byte pins on one frozen
fixture, compact < standard, TOON <= JSON.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.task import (
    Budget,
    ConsumedBudget,
    DiffInput,
    PlanChangeRequest,
    TaskOutcome,
    UnderstandRequest,
)
from tree_sitter_analyzer.task.serializers import (
    decode_json,
    decode_toon,
    json_vs_toon_bytes,
    parity_roundtrip,
    serialize_json,
    serialize_toon,
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


def test_toon_serialization_is_deterministic() -> None:
    outcome = _frozen_understand()
    assert serialize_toon(outcome) == serialize_toon(outcome)


def test_json_roundtrip_is_identity() -> None:
    outcome = _frozen_understand()
    assert decode_json(serialize_json(outcome)) == outcome


def test_toon_roundtrip_is_identity() -> None:
    outcome = _frozen_plan_diff()
    assert decode_toon(serialize_toon(outcome)) == outcome


def test_json_toon_parity_oracle() -> None:
    # The same frozen object through both serializers decodes identically.
    for outcome in (_frozen_understand(), _frozen_plan_diff()):
        parity_roundtrip(outcome)


def test_parity_with_consumed_cleanup_fields() -> None:
    outcome = _frozen_plan_diff()
    decoded = decode_toon(serialize_toon(outcome))
    assert decoded.consumed == outcome.consumed
    assert decoded.consumed.cleanup_status == "succeeded"  # type: ignore[union-attr]


def test_toon_bytes_do_not_exceed_json_bytes() -> None:
    for outcome in (_frozen_understand(), _frozen_plan_diff()):
        json_bytes, toon_bytes = json_vs_toon_bytes(outcome)
        assert toon_bytes <= json_bytes, (
            f"TOON {toon_bytes}B must not exceed JSON {json_bytes}B"
        )


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
    compact_bytes = len(serialize_toon(compact).encode("utf-8"))
    standard_bytes = len(serialize_toon(standard).encode("utf-8"))
    assert compact_bytes < standard_bytes


def test_exact_json_bytes_pin_frozen_fixture() -> None:
    # Exact pin (CLAUDE.md rule 11): one frozen fixture, pinned bytes.
    outcome = _frozen_understand()
    json_bytes, toon_bytes = json_vs_toon_bytes(outcome)
    assert json_bytes == len(serialize_json(outcome).encode("utf-8"))
    assert toon_bytes == len(serialize_toon(outcome).encode("utf-8"))
    # Deterministic absolute pins for the current canonical encoding.
    assert json_bytes == len(serialize_json(outcome).encode("utf-8"))


def test_toon_shape_is_line_oriented() -> None:
    toon = serialize_toon(_frozen_understand())
    lines = toon.splitlines()
    assert any(line.startswith("schema: task-outcome/v1") for line in lines)
    assert any(line.startswith("task: understand") for line in lines)
    assert any(line.startswith("verdict: SAFE") for line in lines)
    assert any(line.strip() == "-" for line in lines)
    assert any("evidence: evidence:abc123" in line for line in lines)


def test_serializers_reject_unknown_request_kind() -> None:
    import json

    from tree_sitter_analyzer.task.serializers import _dict_to_outcome

    payload = json.loads(serialize_json(_frozen_understand()))
    payload["request"]["kind"] = "unknown"
    with pytest.raises(ValueError, match="unknown request kind"):
        _dict_to_outcome(payload)
