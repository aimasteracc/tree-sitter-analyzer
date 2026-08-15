"""RFC-0023 edge-evidence validator contracts (Phase A).

Validates the five checked-in artifacts: the golden bundle is accepted,
every denial case is rejected with its exact expected reason, the stable
sort base stays accepted, and the generated rule registry is structurally
sound (RFC-0023 §7 Acceptance).
"""

from __future__ import annotations

import json

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
