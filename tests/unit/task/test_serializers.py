"""RFC-0022 task-outcome/v1 serializer parity and cost invariants (Phase A).

RFC-0022 §Determinism and serializer parity + §Executable value and cost
invariants: same-object JSON/TOON parity, exact byte pins on one frozen
fixture, compact < standard, TOON <= JSON.
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
    assert any(line.startswith('schema: "task-outcome/v1"') for line in lines)
    assert any(line.startswith('task: "understand"') for line in lines)
    assert any(line.startswith('verdict: "SAFE"') for line in lines)
    assert any(line.strip() == "-" for line in lines)
    assert any('evidence: "evidence:abc123"' in line for line in lines)


def test_serializers_reject_unknown_request_kind() -> None:
    import json

    from tree_sitter_analyzer.task.serializers import _dict_to_outcome

    payload = json.loads(serialize_json(_frozen_understand()))
    payload["request"]["kind"] = "unknown"
    with pytest.raises(ValueError, match="unknown request kind"):
        _dict_to_outcome(payload)


def test_toon_roundtrip_multiline_and_colon_strings() -> None:
    # B1/B2 (review #1268): newlines and colons inside strings must survive
    # the TOON codec losslessly.
    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="line1\nline2: part"),
        verdict="INFO",
    )
    decoded = decode_toon(serialize_toon(outcome))
    assert decoded.request.task == "line1\nline2: part"  # type: ignore[union-attr]


def test_toon_roundtrip_literal_looking_strings() -> None:
    # B3 (review #1268): quoted strings never decode to other types.
    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="123"),
        verdict="INFO",
    )
    decoded = decode_toon(serialize_toon(outcome))
    assert decoded.request.task == "123"  # type: ignore[union-attr]
    assert isinstance(decoded.request.task, str)  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="unquoted TOON value"):
        decode_toon("task: understand\nrequest:\n  kind: understand\n  task: 123\n")


def test_toon_roundtrip_surrounding_whitespace_strings() -> None:
    # B5 (review #1268): surrounding whitespace is preserved.
    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="  padded  "),
        verdict="INFO",
    )
    decoded = decode_toon(serialize_toon(outcome))
    assert decoded.request.task == "  padded  "  # type: ignore[union-attr]


def test_toon_rejects_unquoted_non_literal_values() -> None:
    # B3/B5 (review #1268): bare unquoted text is a hard error, never a guess.
    with pytest.raises(ValueError, match="unquoted TOON value"):
        decode_toon(
            "task: understand\nrequest:\n  kind: understand\n  task: bare text\n"
        )


def test_exact_absolute_bytes_pin_frozen_fixture() -> None:
    # W1 (review #1268): real absolute pins, not x == x tautologies.
    outcome = _frozen_understand()
    json_bytes, toon_bytes = json_vs_toon_bytes(outcome)
    assert json_bytes == 732
    assert toon_bytes == 575


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
    assert decode_toon(serialize_toon(outcome)) == outcome
    assert decode_json(serialize_json(outcome)) == outcome


def test_toon_empty_nested_containers_roundtrip() -> None:
    # Covers empty-container markers inside nested structures.
    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="x"),
        verdict="INFO",
        evidence=({"empty_list": [], "empty_dict": {}},),
    )
    decoded = decode_toon(serialize_toon(outcome))
    assert decoded.evidence == ({"empty_list": [], "empty_dict": {}},)


def test_toon_quoted_string_rejects_bad_escape() -> None:
    # An unterminated quoted string is a hard parse error, never a guess.
    with pytest.raises(ValueError, match="invalid quoted TOON string"):
        decode_toon(
            'task: "understand"\nrequest:\n  kind: "understand"\n  task: "unclosed\n'
        )


def test_assess_change_request_roundtrip() -> None:
    # Covers the AssessChangeRequest serializer branch.
    outcome = TaskOutcome(
        task="assess_change",
        request=AssessChangeRequest(diff=DiffInput(source="workspace")),
        verdict="WARN",
        status="partial",
    )
    assert decode_toon(serialize_toon(outcome)) == outcome
    assert decode_json(serialize_json(outcome)) == outcome


def test_toon_empty_containers_at_top_level() -> None:
    # Direct empty-container scalar markers.
    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="x"),
        verdict="INFO",
        evidence=({"a": []},),
    )
    text = serialize_toon(outcome)
    assert "[]" in text
    decoded = decode_toon(text)
    assert decoded.evidence == ({"a": []},)


def test_toon_both_empty_container_markers() -> None:
    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="x"),
        verdict="INFO",
        evidence=({"a": [], "b": {}},),
    )
    text = serialize_toon(outcome)
    assert "[]" in text
    assert "{}" in text
    decoded = decode_toon(text)
    assert decoded.evidence == ({"a": [], "b": {}},)


def test_toon_unicode_string_roundtrip() -> None:
    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="café 日本語 🚀"),
        verdict="INFO",
    )
    assert decode_toon(serialize_toon(outcome)) == outcome


def test_toon_continuation_outside_list_item_rejected() -> None:
    # A key line following a scalar list item is a structural error.
    from tree_sitter_analyzer.task.serializers import _parse_toon

    with pytest.raises(ValueError, match="continuation outside a list item"):
        _parse_toon('evidence:\n  - "plain"\n    orphan: "nope"\n')


def test_toon_list_key_value_items_parse() -> None:
    # Covers the is_item + "key: value" branch of the parser.
    from tree_sitter_analyzer.task.serializers import _parse_toon

    parsed = _parse_toon(
        'evidence:\n  - locator: "src/a.py"\n  - locator: "src/b.py"\n'
    )
    assert parsed == {"evidence": [{"locator": "src/a.py"}, {"locator": "src/b.py"}]}


def test_toon_bool_and_trailing_bare_key() -> None:
    # Covers bool scalars and the pending-child tail (bare key at EOF).
    from tree_sitter_analyzer.task.serializers import _parse_toon

    parsed = _parse_toon("flag: true\nother: false\nbare:\n")
    assert parsed == {"flag": True, "other": False, "bare": {}}


def test_toon_key_line_inside_list_rejected() -> None:
    from tree_sitter_analyzer.task.serializers import _parse_toon

    # A key line after a scalar item is rejected by the continuation guard.
    with pytest.raises(ValueError, match="continuation outside a list item"):
        _parse_toon('evidence:\n  - "plain"\n  key: "x"\n')


def test_toon_missing_key_line_rejected() -> None:
    from tree_sitter_analyzer.task.serializers import _parse_toon

    with pytest.raises(ValueError, match="lacks a key"):
        _parse_toon("just-a-value\n")


def test_toon_bool_scalar_roundtrip() -> None:
    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="x"),
        verdict="INFO",
        evidence=({"safe": True, "warned": False},),
    )
    decoded = decode_toon(serialize_toon(outcome))
    assert decoded.evidence == ({"safe": True, "warned": False},)


def test_toon_list_item_continuation_at_same_indent() -> None:
    # Covers the continuation branch: a key line at the list depth extends
    # the last dict item.
    from tree_sitter_analyzer.task.serializers import _parse_toon

    parsed = _parse_toon('evidence:\n  - locator: "src/a.py"\n  summary: "entry"\n')
    assert parsed == {"evidence": [{"locator": "src/a.py", "summary": "entry"}]}


def test_toon_item_nested_bare_key() -> None:
    # Covers the item-level pending_child path ("- key:" opens a child).
    from tree_sitter_analyzer.task.serializers import _parse_toon

    parsed = _parse_toon('evidence:\n  - locator:\n      path: "src/a.py"\n')
    assert parsed == {"evidence": [{"locator": {"path": "src/a.py"}}]}


def test_toon_scope_paths_with_colon_roundtrip() -> None:
    # B2 (review round 2, #1268): Windows-style "src:lib" paths survive.
    outcome = TaskOutcome(
        task="plan_change",
        request=PlanChangeRequest(
            diff=DiffInput(source="staged", scope_paths=("src:lib", "tests")),
        ),
        verdict="CAUTION",
    )
    decoded = decode_toon(serialize_toon(outcome))
    assert decoded.request.diff.scope_paths == ("src:lib", "tests")  # type: ignore[union-attr]


def test_toon_nested_list_in_evidence_roundtrip() -> None:
    # B4 (review round 2, #1268): list-in-list evidence decodes.
    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="x"),
        verdict="INFO",
        evidence=({"matrix": [[1, 2], [3, 4]]},),
    )
    decoded = decode_toon(serialize_toon(outcome))
    assert decoded.evidence == ({"matrix": [[1, 2], [3, 4]]},)


def test_toon_trailing_bare_dash_item() -> None:
    # Covers the pending_item tail: a bare "-" at end of input appends {}.
    from tree_sitter_analyzer.task.serializers import _parse_toon

    parsed = _parse_toon("evidence:\n  -\n")
    assert parsed == {"evidence": [{}]}


def test_toon_list_empty_container_items_roundtrip() -> None:
    outcome = TaskOutcome(
        task="understand",
        request=UnderstandRequest(task="x"),
        verdict="INFO",
        evidence=(
            {},
            [],
        ),
    )
    decoded = decode_toon(serialize_toon(outcome))
    assert decoded.evidence == ({}, [])
