"""Issue #1376：receipt_authentication 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import json
import os
import sys
from functools import partial
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_qualification_helpers import (
    _qualification_plans,
    _qualification_verifier_config,
    _resign_qualification_receipt,
    _validate_qualification_receipt,
    _write_valid_qualification_receipt,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


@pytest.mark.parametrize(
    ("value", "canonicalization_failure"),
    ((float("nan"), True), (float("inf"), True), (True, False)),
)
def test_strict_validator_rejects_nonfinite_or_boolean_resource_value(
    tmp_path: Path, value, canonicalization_failure
):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["resource_observation"]["wall_seconds"] = value
    _resign_qualification_receipt(receipt)
    expected = (
        ("RECEIPT_SCHEMA_MISMATCH",)
        if canonicalization_failure
        else (
            "RECEIPT_SCHEMA_MISMATCH",
            "RESOURCE_LIMIT_VIOLATION",
            "INDEX_PROVENANCE_MISSING",
            "OS_AUDIT_MISSING",
            "HUMAN_ORACLE_APPROVAL_MISSING",
        )
    )
    assert (
        _validate_qualification_receipt(
            receipt,
            plan=plan,
            cell_root=cell_root,
            verifier_config=_qualification_verifier_config(),
        )
        == expected
    )


def test_strict_validator_rejects_unknown_schema_version(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["schema_version"] = 1
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("RECEIPT_SCHEMA_MISMATCH",)


def test_strict_validator_rejects_incomplete_index_partition(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["index_partition"]["indexed_paths"] = []
    from benchmarks.codegraph_compare.integrity import _sha256

    receipt["index_partition"]["indexed_paths_hash"] = _sha256([])
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "INDEX_PARTITION_MISMATCH",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_forged_executor_signature(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["index_provenance"]["signature"] = "00" * 64
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("INDEX_PROVENANCE_MISSING",)


def test_validator_authenticates_quiescence_before_tree_hash(
    tmp_path: Path, monkeypatch
):
    # PR #1247: an untrusted snapshot signature must fail before index bytes are read.
    import benchmarks.codegraph_compare.setup_qualification_validation as validation

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["snapshot_audit"]["signature"] = "00" * 64
    _resign_qualification_receipt(receipt)
    hash_calls = 0

    def forbidden_hash(*_args, **_kwargs):
        nonlocal hash_calls
        hash_calls += 1
        raise AssertionError("tree hash ran before quiescence authentication")

    monkeypatch.setattr(validation, "_snapshot_tree_at", forbidden_hash)
    failures = _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    )

    assert (failures[0], hash_calls) == ("SNAPSHOT_AUDIT_MISSING", 0)


def test_strict_validator_rejects_forged_audit_signature(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["os_audit"]["signature"] = "00" * 64
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("OS_AUDIT_MISSING",)


def test_strict_validator_rejects_forged_approver_signature(tmp_path: Path):
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["human_oracle_approval"]["signature"] = "00" * 64
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("HUMAN_ORACLE_APPROVAL_MISSING",)


@pytest.mark.parametrize(
    ("blob_name", "payload"),
    (
        ("query_bytes", b'{"name":"Wrong"}'),
        ("stdout_bytes", b'{"line":2,"path":"wrong.ts"}'),
    ),
)
def test_strict_validator_rejects_wrong_normalized_oracle_evidence(
    tmp_path: Path, blob_name: str, payload: bytes
):
    from benchmarks.codegraph_compare.setup_qualification import (
        _bytes_hash,
    )

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    blob = receipt["raw_executions"][3][blob_name]
    (cell_root / blob["path"]).write_bytes(payload)
    blob["size_bytes"] = len(payload)
    blob["sha256"] = _bytes_hash(payload)
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_unplanned_parse_error_allowlist(tmp_path: Path):
    from benchmarks.codegraph_compare.integrity import _sha256

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    partition = receipt["index_partition"]
    partition["indexed_paths"] = []
    partition["indexed_paths_hash"] = _sha256([])
    partition["parse_error_paths"] = ["main.ts"]
    partition["parse_error_allowlist"] = ["main.ts"]
    partition["parse_error_paths_hash"] = _sha256(["main.ts"])
    _resign_qualification_receipt(receipt)
    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "INDEX_PARTITION_MISMATCH",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_rejects_arbitrarily_large_integer_observation(tmp_path: Path):
    # PR #1247: resource validation must fail closed rather than raise OverflowError.
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["resource_observation"]["wall_seconds"] = 10**400
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RESOURCE_LIMIT_VIOLATION",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_validator_rejects_null_digest_signatures_after_core_failure(tmp_path: Path):
    # PR #1247: a non-canonical evidence core cannot authenticate as a null digest.
    import copy
    import json

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["raw_executions"][1]["oracle_spec_hash"] = float("inf")
    executor_payload = {
        "schema_version": 1,
        "plan_hash": plan.digest,
        "evidence_core_digest": None,
    }

    def sign(seed: bytes, payload):
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return Ed25519PrivateKey.from_private_bytes(seed * 32).sign(encoded).hex()

    receipt["index_provenance"]["payload"] = executor_payload
    receipt["index_provenance"]["signature"] = sign(b"\x02", executor_payload)
    receipt["os_audit"]["payload"] = executor_payload
    receipt["os_audit"]["signature"] = sign(b"\x02", executor_payload)
    approval_payload = dict(receipt["human_oracle_approval"]["payload"])
    approval_payload["evidence_core_digest"] = None
    receipt["human_oracle_approval"]["payload"] = approval_payload
    receipt["human_oracle_approval"]["signature"] = sign(b"\x01", approval_payload)
    _resign_qualification_receipt(receipt)

    failures = _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    )
    assert failures == ("RECEIPT_SCHEMA_MISMATCH",)


def test_strict_validator_rejects_receipt_extension_even_with_matching_hash(
    tmp_path: Path,
):
    # PR #1247: direct validator callers receive a fail-closed schema failure.

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    receipt["extension"] = "unsigned"
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == ("RECEIPT_SCHEMA_MISMATCH",)


def test_validator_rejects_default_reopen_through_symlinked_ancestor(tmp_path: Path):
    # PR #1247: untrusted evidence has no path-reopen fallback.
    from benchmarks.codegraph_compare.setup_qualification import validate_cell_receipt

    plan = _qualification_plans(tmp_path)[0]
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    cell = real_parent / "cell"
    receipt = _write_valid_qualification_receipt(cell, plan)
    alias = tmp_path / "alias"
    alias.symlink_to(real_parent, target_is_directory=True)

    failures = validate_cell_receipt(
        receipt,
        plan=plan,
        cell_root=alias / "cell",
        verifier_config=_qualification_verifier_config(),
    )

    assert failures[0] == "CELL_ROOT_ISOLATION_MISMATCH"


def test_validator_uses_pinned_experiment_descriptor_after_path_replacement(
    tmp_path: Path,
):
    from benchmarks.codegraph_compare.setup_qualification import validate_cell_receipt
    from benchmarks.codegraph_compare.setup_qualification_paths import (
        _open_root,
        _stable_directory_identity,
    )

    plan = _qualification_plans(tmp_path)[0]
    experiment = tmp_path / "experiment"
    cell = experiment / "cells/vscode--tsa-warm"
    receipt = _write_valid_qualification_receipt(cell, plan)
    root_fd = _open_root(experiment)
    moved = tmp_path / "moved"
    experiment.rename(moved)
    outside = tmp_path / "outside"
    outside.mkdir()
    experiment.symlink_to(outside, target_is_directory=True)
    try:
        assert (
            validate_cell_receipt(
                receipt,
                plan=plan,
                cell_root=cell,
                verifier_config=_qualification_verifier_config(),
                trusted_root_fd=root_fd,
                trusted_root_identity=_stable_directory_identity(os.fstat(root_fd)),
                cell_relative="cells/vscode--tsa-warm",
            )
            == ()
        )
    finally:
        os.close(root_fd)


def test_strict_validator_rejects_decoy_receipt_index_path(tmp_path: Path):
    # PR #1247: receipt-selected decoy trees cannot replace the plan-bound index.
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    decoy = cell_root / "decoy"
    decoy.mkdir()
    (decoy / "index.bin").write_bytes(b"frozen index")
    receipt["index_path"] = f"cells/{plan.repo_id}/{plan.arm_id}/decoy"
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "PLAN_BINDING_MISMATCH",
        "SNAPSHOT_AUDIT_MISSING",
        "INDEX_BYTES_MISMATCH",
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_strict_validator_requires_exact_ordered_frozen_commands(tmp_path: Path):
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = copy.deepcopy(_write_valid_qualification_receipt(cell_root, plan))
    receipt["raw_executions"][0]["argv"] = ["true"]
    _resign_qualification_receipt(receipt)

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
    ) == (
        "RAW_EXECUTION_EVIDENCE_MISSING",
        "INDEX_PROVENANCE_MISSING",
        "OS_AUDIT_MISSING",
        "HUMAN_ORACLE_APPROVAL_MISSING",
    )


def test_verifier_trust_roots_are_immutable_config():
    from dataclasses import FrozenInstanceError

    import pytest

    config = _qualification_verifier_config()
    with pytest.raises(FrozenInstanceError):
        config.executor_public_key = b"\x00" * 32


def test_validator_exports_no_mutable_trust_key_globals():
    import benchmarks.codegraph_compare.setup_qualification as qualification

    assert (
        hasattr(qualification, "TRUSTED_EXECUTOR_PUBLIC_KEY"),
        hasattr(qualification, "TRUSTED_APPROVER_PUBLIC_KEY"),
    ) == (False, False)


def test_validator_rejects_missing_retained_receipt(tmp_path: Path):
    # PR #1247 review 3743050577: supplied mappings cannot replace retained evidence.
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    (cell_root / "cell-receipt.json").unlink()

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


def test_validator_rejects_stale_retained_receipt(tmp_path: Path):
    # PR #1247 review 3743050577: retained and supplied hashes must match exactly.
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    stale = copy.deepcopy(receipt)
    stale["resource_observation"]["wall_seconds"] = 2
    _resign_qualification_receipt(stale)
    (cell_root / "cell-receipt.json").write_text(
        json.dumps(stale, sort_keys=True), encoding="utf-8"
    )

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


def test_validator_rejects_type_different_retained_receipt(tmp_path: Path):
    # PR #1247 review 3743050577: JSON true never aliases integer one.
    import copy

    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    type_different = copy.deepcopy(receipt)
    type_different["resource_observation"]["wall_seconds"] = True
    _resign_qualification_receipt(type_different)
    (cell_root / "cell-receipt.json").write_text(
        json.dumps(type_different, sort_keys=True), encoding="utf-8"
    )

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


def test_validator_rejects_empty_retained_receipt_object(tmp_path: Path):
    # PR #1247 review 3743050577: an empty retained JSON object is not evidence.
    plan = _qualification_plans(tmp_path)[0]
    cell_root = tmp_path / "cell"
    receipt = _write_valid_qualification_receipt(cell_root, plan)
    (cell_root / "cell-receipt.json").write_bytes(b"{}")

    assert _validate_qualification_receipt(
        receipt,
        plan=plan,
        cell_root=cell_root,
        verifier_config=_qualification_verifier_config(),
        sync_retained=False,
    ) == ("RETAINED_RECEIPT_MISMATCH",)


_mark_posix_qualification_section_tests()
