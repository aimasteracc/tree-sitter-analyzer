"""RFC-0022 task-outcome/v1 evidence, freshness, and route-table contracts.

Exact pins for evidence identity (RFC-0022 §Evidence and provenance
identity), freshness states (§Freshness and snapshot truth), and the
complete route decision table (§Complete V1 route decision table).
"""

from __future__ import annotations

import hashlib

import pytest

from tree_sitter_analyzer.task import (
    FRESHNESS_STATES,
    ROUTE_TABLE,
    SAFE_FANOUT_CAPS,
    EvidenceInput,
    SnapshotTruth,
    evidence_identity,
    normalized_result_hash,
)


def _base_evidence() -> EvidenceInput:
    return EvidenceInput(
        primitive_facade="edit",
        action="safe",
        action_version="edit.safe/v1",
        normalized_result_sha256=hashlib.sha256(b"{}").hexdigest(),
        source_snapshot_id="idxsnap_01",
        locator="src/app.py",
    )


def test_evidence_identity_is_exact_digest_prefix() -> None:
    identity = evidence_identity(_base_evidence())
    assert identity.startswith("evidence:")
    assert len(identity) == len("evidence:") + 64
    hex_part = identity[len("evidence:") :]
    assert all(char in "0123456789abcdef" for char in hex_part)


def test_evidence_identity_is_deterministic() -> None:
    assert evidence_identity(_base_evidence()) == evidence_identity(_base_evidence())


def test_evidence_identity_changes_with_each_owner_field() -> None:
    base = _base_evidence()
    baseline = evidence_identity(base)
    variants = {
        "facade": EvidenceInput(
            primitive_facade="nav",
            action=base.action,
            action_version=base.action_version,
            normalized_result_sha256=base.normalized_result_sha256,
            source_snapshot_id=base.source_snapshot_id,
            locator=base.locator,
        ),
        "action": EvidenceInput(
            primitive_facade=base.primitive_facade,
            action="classify",
            action_version=base.action_version,
            normalized_result_sha256=base.normalized_result_sha256,
            source_snapshot_id=base.source_snapshot_id,
            locator=base.locator,
        ),
        "version": EvidenceInput(
            primitive_facade=base.primitive_facade,
            action=base.action,
            action_version="edit.safe/v2",
            normalized_result_sha256=base.normalized_result_sha256,
            source_snapshot_id=base.source_snapshot_id,
            locator=base.locator,
        ),
        "result": EvidenceInput(
            primitive_facade=base.primitive_facade,
            action=base.action,
            action_version=base.action_version,
            normalized_result_sha256=hashlib.sha256(b"other").hexdigest(),
            source_snapshot_id=base.source_snapshot_id,
            locator=base.locator,
        ),
        "snapshot": EvidenceInput(
            primitive_facade=base.primitive_facade,
            action=base.action,
            action_version=base.action_version,
            normalized_result_sha256=base.normalized_result_sha256,
            source_snapshot_id="other-snap",
            locator=base.locator,
        ),
        "locator": EvidenceInput(
            primitive_facade=base.primitive_facade,
            action=base.action,
            action_version=base.action_version,
            normalized_result_sha256=base.normalized_result_sha256,
            source_snapshot_id=base.source_snapshot_id,
            locator="src/other.py",
        ),
    }
    for name, variant in variants.items():
        assert evidence_identity(variant) != baseline, name


def test_evidence_identity_same_locator_different_results_are_distinct() -> None:
    # Locator alone never identifies or deduplicates evidence.
    first = evidence_identity(_base_evidence())
    different_result = EvidenceInput(
        primitive_facade="edit",
        action="safe",
        action_version="edit.safe/v1",
        normalized_result_sha256=hashlib.sha256(b'{"x":1}').hexdigest(),
        source_snapshot_id="idxsnap_01",
        locator="src/app.py",
    )
    assert evidence_identity(different_result) != first


def test_evidence_input_rejects_bad_digest() -> None:
    with pytest.raises(ValueError, match="64-hex digest"):
        EvidenceInput(
            primitive_facade="edit",
            action="safe",
            action_version="edit.safe/v1",
            normalized_result_sha256="short",
            source_snapshot_id=None,
            locator="x",
        )


def test_normalized_result_hash_is_canonical() -> None:
    assert normalized_result_hash({"b": 1, "a": 2}) == normalized_result_hash(
        {"a": 2, "b": 1}
    )
    assert normalized_result_hash({"a": 2, "b": 1}) != normalized_result_hash(
        {"a": 2, "b": 1, "c": 3}
    )


def test_freshness_states_are_pinned() -> None:
    assert FRESHNESS_STATES == {
        "fresh",
        "stale",
        "missing",
        "not_applicable",
        "unknown",
    }


def test_freshness_not_applicable_without_graph_evidence() -> None:
    truth = SnapshotTruth(oracle_complete=True, snapshot_id="s1", graph_tokens=())
    assert truth.freshness == ("not_applicable", None)
    assert truth.graph_status_cap == "partial"


def test_freshness_fresh_requires_complete_oracle_and_matching_tokens() -> None:
    truth = SnapshotTruth(
        oracle_complete=True,
        snapshot_id="s1",
        graph_tokens=("s1",),
    )
    assert truth.freshness == ("fresh", None)
    assert truth.graph_status_cap == "complete"


def test_freshness_incomplete_oracle_is_unknown() -> None:
    truth = SnapshotTruth(
        oracle_complete=False,
        snapshot_id="s1",
        graph_tokens=("s1",),
    )
    assert truth.freshness == (
        "unknown",
        "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE",
    )
    assert truth.graph_status_cap == "partial"


def test_freshness_missing_snapshot_is_missing() -> None:
    truth = SnapshotTruth(oracle_complete=True, snapshot_id=None, graph_tokens=("s1",))
    assert truth.freshness == ("missing", "AUTHORITATIVE_SNAPSHOT_UNAVAILABLE")


def test_freshness_token_mismatch_is_stale() -> None:
    truth = SnapshotTruth(
        oracle_complete=True,
        snapshot_id="s1",
        graph_tokens=("s2",),
    )
    assert truth.freshness == ("stale", "SNAPSHOT_TOKEN_MISMATCH")
    assert truth.graph_status_cap == "partial"


def test_route_table_rows_are_pinned_exactly() -> None:
    assert [(row.operation, row.facade, row.action) for row in ROUTE_TABLE] == [
        ("all", "index", "status"),
        ("understand(task)", "nav", "context"),
        ("plan_change(task)", "nav", "context"),
        ("plan_change(task)", "edit", "safe"),
        ("diff operation", "edit", "impact"),
        ("diff operation", "edit", "constraints"),
        ("diff operation", "edit", "ast_diff"),
        ("diff operation", "edit", "classify"),
    ]


def test_route_table_orders_constraints_before_fanout() -> None:
    # Common routing rule 2: constraints is reserved before file fan-out and
    # follows a successful impact immediately.
    order = {id(row): index for index, row in enumerate(ROUTE_TABLE)}
    impact = next(row for row in ROUTE_TABLE if row.action == "impact")
    constraints = next(row for row in ROUTE_TABLE if row.action == "constraints")
    ast_diff = next(row for row in ROUTE_TABLE if row.action == "ast_diff")
    assert order[id(impact)] < order[id(constraints)] < order[id(ast_diff)]


def test_route_table_primitive_parameters_are_exact() -> None:
    params = {
        (row.operation, row.facade, row.action): row.parameters for row in ROUTE_TABLE
    }
    assert params[("all", "index", "status")] == (
        ("access_mode", "read_existing"),
        ("output_format", "json"),
    )
    assert params[("understand(task)", "nav", "context")] == (
        ("max_nodes", "12/30"),
        ("max_code_blocks", "3/5"),
        ("include_graph", "false"),
        ("access_mode", "read_existing"),
        ("output_format", "json"),
    )
    assert params[("diff operation", "edit", "constraints")] == (
        ("persist", "false"),
        ("access_mode", "read_existing"),
        ("output_format", "json"),
    )


def test_safe_fanout_caps_are_pinned() -> None:
    assert SAFE_FANOUT_CAPS == {"compact": 2, "standard": 5}


def test_route_table_has_no_llm_or_keyword_router() -> None:
    # RFC-0022: no task-layer keyword, regex, intent, or LLM router.
    for row in ROUTE_TABLE:
        assert row.facade in {"index", "nav", "edit"}
        assert row.action in {
            "status",
            "context",
            "safe",
            "impact",
            "constraints",
            "ast_diff",
            "classify",
        }
