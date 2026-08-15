"""RFC-0023 edge-evidence validator contracts (Phase A).

Validates the five checked-in artifacts: the golden bundle is accepted,
every denial case is rejected with its exact expected reason, the stable
sort base stays accepted, and the generated rule registry is structurally
sound (RFC-0023 §7 Acceptance).
"""

from __future__ import annotations

import json

import pytest

from tree_sitter_analyzer.task.edge_evidence import (
    FIXTURES_DIR,
    SCHEMA_PATH,
    validate_fixture,
    validate_negative_cases,
    validate_shape,
)


def _load_fixture(name: str) -> dict:
    return json.loads(
        (FIXTURES_DIR / f"edge-evidence-v1-{name}.json").read_text(encoding="utf-8")
    )


def test_golden_bundle_is_accepted() -> None:
    result = validate_fixture("golden")
    assert result.accepted is True
    assert len(result.evidence_ids) == 2
    assert all(item.startswith("evidence:sha256:") for item in result.evidence_ids)


def test_golden_evidence_ids_are_recomputed() -> None:
    from tree_sitter_analyzer.task.edge_evidence import evidence_id

    bundle = _load_fixture("golden")
    for record in bundle["records"]:
        if record["schema"] == "edge-evidence/v1":
            assert record["evidence_id"] == evidence_id(record)


def test_stable_sort_base_is_accepted() -> None:
    assert validate_fixture("stable-sort-base").accepted is True


def test_schema_is_draft_2020_12() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_golden_passes_json_schema_shape() -> None:
    validate_shape(_load_fixture("golden"))


def test_negative_cases_all_rejected_with_exact_reason() -> None:
    negative = _load_fixture("negative")
    results = validate_negative_cases(negative)
    assert len(results) == len(negative["cases"])
    for case in negative["cases"]:
        result = results[case["id"]]
        assert result.accepted is False, f"{case['id']} must be rejected"
        assert result.reasons == (case["expected"]["reason"],), (
            f"{case['id']}: expected {case['expected']['reason']}, got {result.reasons}"
        )
        assert result.evidence_ids == ()


def test_negative_cases_cover_all_reason_vocabulary() -> None:
    negative = _load_fixture("negative")
    reasons = {case["expected"]["reason"] for case in negative["cases"]}
    assert reasons == {
        "ACTION_MISSING",
        "ACTION_VERSION_MISSING",
        "AMBIGUOUS_TARGET",
        "EDGE_KIND_MISMATCH",
        "FACADE_MISSING",
        "FRESHNESS_SIGNAL_MISSING",
        "MALFORMED_RESULT",
        "NO_TARGET",
        "OWNER_MISMATCH",
        "PROPOSED_EDGE_KEY_MISSING",
        "RULE_ID_MISSING",
        "RULE_VERSION_MISSING",
        "SNAPSHOT_MISMATCH",
        "STALE_SNAPSHOT",
        "TARGET_DECLARATION_MISMATCH",
        "UNRESOLVED_TARGET",
        "UNSUPPORTED_KIND",
    }


def test_generated_rule_registry_is_structurally_sound() -> None:
    registry = _load_fixture("generated-rule-registry")
    entries = registry["entries"]
    assert len(entries) == 2
    pairs = [
        (entry["producer_rule_id"], entry["producer_rule_version"]) for entry in entries
    ]
    assert len(set(pairs)) == len(pairs)
    for entry in entries:
        assert entry["allowed_edge_kinds"]
        assert entry["allowed_observation_states"]
        assert entry["entry_id"]


def test_reason_priority_follows_rfc_document_order() -> None:
    from tree_sitter_analyzer.task.edge_evidence import _REASON_PRIORITY

    assert _REASON_PRIORITY.index("EDGE_KIND_MISMATCH") > _REASON_PRIORITY.index(
        "TARGET_DECLARATION_MISMATCH"
    )
    assert _REASON_PRIORITY.index("MALFORMED_RESULT") > _REASON_PRIORITY.index(
        "UNSUPPORTED_KIND"
    )


def test_mutation_runner_appends_and_removes() -> None:
    from tree_sitter_analyzer.task.edge_evidence import _apply_mutations

    doc = {"items": [1, 2]}
    mutated = _apply_mutations(doc, [{"op": "add", "path": "/items/-", "value": 3}])
    assert mutated == {"items": [1, 2, 3]}
    mutated = _apply_mutations(mutated, [{"op": "remove", "path": "/items/0"}])
    assert mutated == {"items": [2, 3]}


def test_float_request_preimage_rejected() -> None:
    from tree_sitter_analyzer.task.edge_evidence import _reject_floats

    _reject_floats({"a": 1})
    with pytest.raises(ValueError, match="float"):
        _reject_floats({"a": 1.5})


def test_id_formulas_recompute_from_components() -> None:
    from tree_sitter_analyzer.task.edge_evidence import (
        collection_id,
        contradiction_group_id,
        provenance_id,
    )

    scope = {"edge_kind": "calls"}
    snapshot = {"snapshot_id": "s1"}
    primitive = {"facade": "nav", "action": "edges"}
    cid = collection_id(scope, snapshot, primitive)
    assert cid.startswith("collection:sha256:")
    assert len(cid) == len("collection:sha256:") + 64
    assert collection_id(scope, snapshot, primitive) == cid

    pid = provenance_id(
        primitive,
        "request-hash",
        "result-hash",
        snapshot,
        True,
        "OK",
        {"state": "not_truncated"},
        [],
    )
    assert pid.startswith("provenance:sha256:")
    assert (
        provenance_id(
            primitive,
            "request-hash",
            "result-hash",
            snapshot,
            True,
            "OK",
            {"state": "not_truncated"},
            [],
        )
        == pid
    )

    gid = contradiction_group_id("calls:src/a.py>src/b.py", "s1")
    assert gid.startswith("contradiction:sha256:")
    assert contradiction_group_id("calls:src/a.py>src/b.py", "s1") == gid


def test_mutation_defenses_reject_structural_breaks() -> None:
    """Defense-in-depth: corpus-external mutations are rejected (review #1269)."""
    from tree_sitter_analyzer.task.edge_evidence import (
        _apply_mutations,
        semantic_validate,
    )

    bundle = _load_fixture("golden")
    cases = [
        # Drop a collection preimage -> record preimage missing.
        (
            [{"op": "remove", "path": "/canonical_preimages/2"}],
            "MALFORMED_RESULT",
        ),
        # Cross-collection item ref.
        (
            [
                {
                    "op": "replace",
                    "path": "/records/0/collection_id",
                    "value": "collection:sha256:0000000000000000000000000000000000000000000000000000000000000000",
                }
            ],
            "MALFORMED_RESULT",
        ),
        # Provenance owner drift.
        (
            [
                {
                    "op": "replace",
                    "path": "/records/5/primitive/facade",
                    "value": "wrong",
                }
            ],
            "MALFORMED_RESULT",
        ),
        # Diagnostic owner drift.
        (
            [
                {
                    "op": "replace",
                    "path": "/records/2/primitive/facade",
                    "value": "wrong",
                }
            ],
            "MALFORMED_RESULT",
        ),
    ]
    for mutations, expected_reason in cases:
        mutated = _apply_mutations(bundle, mutations)
        result = semantic_validate(mutated)
        assert result.accepted is False, mutations
        assert result.reasons == (expected_reason,), (mutations, result.reasons)


def test_preimage_defense_mutations() -> None:
    """Preimage-closure defenses: bad digests and extra entries are rejected."""
    from tree_sitter_analyzer.task.edge_evidence import (
        _apply_mutations,
        semantic_validate,
    )

    bundle = _load_fixture("golden")
    # Corrupt an evidence preimage digest.
    mutated = _apply_mutations(
        bundle,
        [
            {
                "op": "replace",
                "path": "/canonical_preimages/0/canonical_json",
                "value": '{"corrupted":true}',
            }
        ],
    )
    result = semantic_validate(mutated)
    assert result.accepted is False
    assert result.reasons == ("MALFORMED_RESULT",)

    # Add an extra preimage.
    extra = {
        "canonical_json": '{"a":1}',
        "id": "evidence:sha256:" + "0" * 64,
    }
    mutated = _apply_mutations(
        bundle, [{"op": "add", "path": "/canonical_preimages/-", "value": extra}]
    )
    result = semantic_validate(mutated)
    assert result.accepted is False
    assert result.reasons == ("MALFORMED_RESULT",)


def test_request_preimage_defense_mutations() -> None:
    from tree_sitter_analyzer.task.edge_evidence import (
        _apply_mutations,
        semantic_validate,
    )

    bundle = _load_fixture("golden")
    # Non-canonical request preimage (whitespace) is rejected.
    mutated = _apply_mutations(
        bundle,
        [
            {
                "op": "replace",
                "path": "/normalized_request_preimages/0/canonical_json",
                "value": '{"action": "edges", "arguments": {"edge_kind": "calls", "source_node_id": "py:src/a.py:caller"}, "facade": "nav"}',
            }
        ],
    )
    result = semantic_validate(mutated)
    assert result.accepted is False
    assert result.reasons == ("MALFORMED_RESULT",)


def test_projection_defense_mutations() -> None:
    """Corpus-external projection breaks are rejected with precise reasons."""
    from tree_sitter_analyzer.task.edge_evidence import (
        _apply_mutations,
        semantic_validate,
    )

    bundle = _load_fixture("golden")
    cases = [
        # Snapshot drift on the evidence record.
        (
            [
                {
                    "op": "replace",
                    "path": "/records/0/snapshot/snapshot_id",
                    "value": "idx:other",
                }
            ],
            "MALFORMED_RESULT",
        ),
        # Proposed edge key removed from the observation.
        (
            [{"op": "remove", "path": "/raw_observations/0/proposed_edge_key"}],
            "PROPOSED_EDGE_KEY_MISSING",
        ),
        # Owner field removed from the observation (field classifier).
        (
            [{"op": "remove", "path": "/raw_observations/0/primitive/facade"}],
            "FACADE_MISSING",
        ),
        # Observation moves to unresolved with an evidence still referencing
        # it: the schema conditional rejects this shape, so the bundle is
        # malformed before the semantic state machine runs.
        (
            [
                {
                    "op": "replace",
                    "path": "/raw_observations/0/state",
                    "value": "unresolved",
                },
                {
                    "op": "replace",
                    "path": "/raw_observations/0/candidates",
                    "value": [],
                },
                {
                    "op": "replace",
                    "path": "/raw_observations/0/proposed_edge_key/target_node_id",
                    "value": None,
                },
            ],
            "MALFORMED_RESULT",
        ),
    ]
    for mutations, expected_reason in cases:
        mutated = _apply_mutations(bundle, mutations)
        result = semantic_validate(mutated)
        assert result.accepted is False, mutations
        assert result.reasons == (expected_reason,), (mutations, result.reasons)


def test_owner_missing_field_classifier_mutations() -> None:
    from tree_sitter_analyzer.task.edge_evidence import (
        _apply_mutations,
        semantic_validate,
    )

    bundle = _load_fixture("golden")
    field_reasons = {
        "action": "ACTION_MISSING",
        "action_version": "ACTION_VERSION_MISSING",
        "producer_rule_id": "RULE_ID_MISSING",
        "producer_rule_version": "RULE_VERSION_MISSING",
    }
    for field, reason in field_reasons.items():
        mutated = _apply_mutations(
            bundle,
            [{"op": "remove", "path": f"/raw_observations/0/primitive/{field}"}],
        )
        result = semantic_validate(mutated)
        assert result.accepted is False
        assert result.reasons == (reason,), (field, result.reasons)


def test_state_machine_defense_mutations() -> None:
    from tree_sitter_analyzer.task.edge_evidence import (
        _apply_mutations,
        semantic_validate,
    )

    bundle = _load_fixture("golden")
    # Ambiguous with a selected target is contradictory.
    mutated = _apply_mutations(
        bundle,
        [
            {
                "op": "replace",
                "path": "/raw_observations/2/state",
                "value": "ambiguous",
            },
            {
                "op": "replace",
                "path": "/raw_observations/2/target_endpoint",
                "value": {"node_id": "py:src/b.py:callee"},
            },
        ],
    )
    result = semantic_validate(mutated)
    assert result.accepted is False
    assert result.reasons == ("MALFORMED_RESULT",)


def test_collection_defense_mutations() -> None:
    """Collection structure breaks are rejected (review #1269)."""
    from tree_sitter_analyzer.task.edge_evidence import (
        _apply_mutations,
        semantic_validate,
    )

    bundle = _load_fixture("golden")
    cases = [
        # Duplicate item ref (two identical entries).
        (
            [
                {
                    "op": "replace",
                    "path": "/records/3/item_refs",
                    "value": [
                        "evidence:sha256:411eaadcea3da0871ec905a00827a4d79fb5bd34105cf1751209cac22b6ef469",
                        "evidence:sha256:411eaadcea3da0871ec905a00827a4d79fb5bd34105cf1751209cac22b6ef469",
                    ],
                },
                {"op": "replace", "path": "/records/3/returned_count", "value": 2},
                {"op": "replace", "path": "/records/3/total_count", "value": 2},
            ],
            "MALFORMED_RESULT",
        ),
        # Unsorted item refs.
        (
            [
                {
                    "op": "replace",
                    "path": "/records/3/item_refs",
                    "value": [
                        "evidence:sha256:bbdb44951ea3b6060be944b858d9675c30bde1919df8359c70d61f466372817f",
                        "evidence:sha256:411eaadcea3da0871ec905a00827a4d79fb5bd34105cf1751209cac22b6ef469",
                    ],
                },
                {"op": "replace", "path": "/records/3/returned_count", "value": 2},
                {"op": "replace", "path": "/records/3/total_count", "value": 2},
            ],
            "MALFORMED_RESULT",
        ),
        # Exact total missing.
        (
            [{"op": "replace", "path": "/records/3/total_count", "value": None}],
            "MALFORMED_RESULT",
        ),
        # Non-exact total present.
        (
            [
                {
                    "op": "replace",
                    "path": "/records/3/total_count_state",
                    "value": "approximate",
                }
            ],
            "MALFORMED_RESULT",
        ),
        # Collection link pointing at a non-collection record.
        (
            [
                {
                    "op": "replace",
                    "path": "/records/0/collection_id",
                    "value": "provenance:sha256:0000000000000000000000000000000000000000000000000000000000000000",
                }
            ],
            "MALFORMED_RESULT",
        ),
    ]
    for mutations, expected in cases:
        mutated = _apply_mutations(bundle, mutations)
        result = semantic_validate(mutated)
        assert result.accepted is False, mutations
        assert result.reasons == (expected,), (mutations, result.reasons)


def test_exhaustive_collection_defenses() -> None:
    """Unit-level: every collection structural defense fires."""
    from tree_sitter_analyzer.task import edge_evidence as m
    from tree_sitter_analyzer.task.edge_evidence import _apply_mutations

    bundle = _load_fixture("golden")
    evidence_ref = bundle["records"][3]["item_refs"][0]
    # Collection link pointing at an existing non-collection record.
    provenance_id = bundle["records"][5]["provenance_id"]
    bad = _apply_mutations(
        bundle,
        [{"op": "replace", "path": "/records/0/collection_id", "value": provenance_id}],
    )
    with pytest.raises(ValueError, match="collection link not a collection"):
        m._check_collections(bad)
    # Duplicate item refs.
    bad = _apply_mutations(
        bundle,
        [
            {
                "op": "replace",
                "path": "/records/3/item_refs",
                "value": [evidence_ref, evidence_ref],
            }
        ],
    )
    with pytest.raises(ValueError, match="duplicate collection item ref"):
        m._check_collections(bad)
    # returned_count mismatch.
    bad = _apply_mutations(
        bundle, [{"op": "replace", "path": "/records/3/returned_count", "value": 7}]
    )
    with pytest.raises(ValueError, match="returned_count mismatch"):
        m._check_collections(bad)
    # Exact total missing.
    bad = _apply_mutations(
        bundle, [{"op": "replace", "path": "/records/3/total_count", "value": None}]
    )
    with pytest.raises(ValueError, match="exact total missing"):
        m._check_collections(bad)
    # Non-exact total present.
    bad = _apply_mutations(
        bundle,
        [{"op": "replace", "path": "/records/3/total_count_state", "value": "approx"}],
    )
    with pytest.raises(ValueError, match="non-exact total present"):
        m._check_collections(bad)


def test_exhaustive_preimage_defenses() -> None:
    from tree_sitter_analyzer.task import edge_evidence as m
    from tree_sitter_analyzer.task.edge_evidence import _apply_mutations

    bundle = _load_fixture("golden")
    # Corrupted evidence preimage digest (evidence entries are at 5/6).
    bad = _apply_mutations(
        bundle,
        [
            {
                "op": "replace",
                "path": "/canonical_preimages/5/canonical_json",
                "value": '{"x":1}',
            }
        ],
    )
    with pytest.raises(ValueError, match="evidence preimage mismatch"):
        m._check_preimages(bad, m._recompute_evidence_ids(bad))
    # Extra preimage.
    bad = _apply_mutations(
        bundle,
        [
            {
                "op": "add",
                "path": "/canonical_preimages/-",
                "value": {
                    "canonical_json": '{"x":1}',
                    "id": "evidence:sha256:" + "9" * 64,
                },
            }
        ],
    )
    with pytest.raises(ValueError, match="extra preimage"):
        m._check_preimages(bad, m._recompute_evidence_ids(bad))
    # Missing record preimage (provenance at index 2).
    bad = _apply_mutations(bundle, [{"op": "remove", "path": "/canonical_preimages/2"}])
    with pytest.raises(ValueError, match="record preimage missing"):
        m._check_preimages(bad, m._recompute_evidence_ids(bad))


def test_exhaustive_request_preimage_defenses() -> None:
    from tree_sitter_analyzer.task import edge_evidence as m
    from tree_sitter_analyzer.task.edge_evidence import _apply_mutations

    bundle = _load_fixture("golden")
    # Missing provenance request preimage.
    bad = _apply_mutations(
        bundle,
        [
            {
                "op": "replace",
                "path": "/normalized_request_preimages/0/request_sha256",
                "value": "f" * 64,
            }
        ],
    )
    with pytest.raises(ValueError, match="request preimage hash mismatch"):
        m._check_request_preimages(bad)
    # Float inside request preimage.
    bad = _apply_mutations(
        bundle,
        [
            {
                "op": "replace",
                "path": "/normalized_request_preimages/0/canonical_json",
                "value": '{"a":1.5}',
            }
        ],
    )
    with pytest.raises(ValueError, match="float"):
        m._check_request_preimages(bad)
    # Non-canonical (whitespace) preimage.
    bad = _apply_mutations(
        bundle,
        [
            {
                "op": "replace",
                "path": "/normalized_request_preimages/0/canonical_json",
                "value": '{"a": 1}',
            }
        ],
    )
    with pytest.raises(ValueError, match="not canonical"):
        m._check_request_preimages(bad)


def test_exhaustive_diagnostic_reason_defenses() -> None:
    from tree_sitter_analyzer.task import edge_evidence as m
    from tree_sitter_analyzer.task.edge_evidence import _apply_mutations

    bundle = _load_fixture("golden")
    # Duplicate reasons.
    bad = _apply_mutations(
        bundle,
        [
            {
                "op": "replace",
                "path": "/records/2/reasons",
                "value": ["AMBIGUOUS_TARGET", "AMBIGUOUS_TARGET"],
            }
        ],
    )
    with pytest.raises(ValueError, match="reasons not unique"):
        m._check_diagnostic_reasons(bad)
    # Out of priority order.
    bad = _apply_mutations(
        bundle,
        [
            {
                "op": "replace",
                "path": "/records/2/reasons",
                "value": ["MALFORMED_RESULT", "AMBIGUOUS_TARGET"],
            }
        ],
    )
    with pytest.raises(ValueError, match="out of priority order"):
        m._check_diagnostic_reasons(bad)
    # Freshness reason mismatch.
    bad = _apply_mutations(
        bundle,
        [
            {
                "op": "replace",
                "path": "/records/2/freshness/reason",
                "value": "NO_TARGET",
            }
        ],
    )
    with pytest.raises(ValueError, match="freshness reason mismatch"):
        m._check_diagnostic_reasons(bad)
