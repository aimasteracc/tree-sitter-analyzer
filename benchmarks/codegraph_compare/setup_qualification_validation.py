"""Filesystem and signature validation for NO1-008A receipts."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.integrity import _sha256
from benchmarks.codegraph_compare.setup_qualification_paths import (
    _hash_tree_at,
    _open_beneath,
    _open_root,
    _read_regular_at,
    _tree_size_at,
    canonical_relative_path,
)
from benchmarks.codegraph_compare.setup_qualification_plan import (
    ZERO_COUNTERS,
    CellPlanV1,
    HarnessArtifactV1,
    _bytes_hash,
    _is_finite_number,
    _sorted_paths,
)
from benchmarks.codegraph_compare.setup_qualification_schema import (
    _canonical_json_bytes,
    _strict_json_bytes,
    validate_receipt_schema_v2,
)
from benchmarks.codegraph_compare.setup_qualification_trust import (
    VerifierConfigV1,
    _verify_signature,
)


def _evidence_core_payload(
    receipt: Mapping[str, Any], *, plan: CellPlanV1, actual_index_hash: object
) -> dict[str, Any]:
    """Return the single canonical evidence core authenticated by both roles."""
    audit = receipt.get("os_audit")
    audit_mapping = audit if isinstance(audit, Mapping) else {}
    return {
        "schema_version": 1,
        "cell": {
            "repo_id": receipt.get("repo_id"),
            "arm_id": receipt.get("arm_id"),
            "attempt": receipt.get("attempt"),
            "artifact_path": receipt.get("artifact_path"),
        },
        "plan_hash": plan.digest,
        "source": {
            "eligibility": receipt.get("eligibility"),
            "repo_fingerprint": plan.eligibility.repo_fingerprint,
            "commit": plan.eligibility.commit,
        },
        "tool": receipt.get("tool"),
        "config": receipt.get("config"),
        "oracle_specs": [asdict(spec) for spec in plan.oracle_specs],
        "resources": {
            "plan_hash": receipt.get("resource_plan_hash"),
            "observation": receipt.get("resource_observation"),
        },
        "counters": receipt.get("counters"),
        "index": {
            "path": receipt.get("index_path"),
            "content_hash": actual_index_hash,
            "claimed_content_hash": receipt.get("index_content_hash"),
            "partition": receipt.get("index_partition"),
        },
        # Exact exit codes, argv and complete blob descriptors are signed, not
        # a lossy projection of them.
        "executions": receipt.get("raw_executions"),
        "audit": {
            "network_denied": audit_mapping.get("network_denied"),
            "credentials_stripped": audit_mapping.get("credentials_stripped"),
            "descendants_observed": audit_mapping.get("descendants_observed"),
            "process_audited": audit_mapping.get("process_audited"),
            "audit_bytes": audit_mapping.get("audit_bytes"),
        },
    }


def validate_cell_receipt(
    receipt: Mapping[str, Any],
    *,
    plan: CellPlanV1,
    cell_root: Path,
    verifier_config: VerifierConfigV1,
    trusted_root_fd: int | None = None,
    cell_relative: str | None = None,
) -> tuple[str, ...]:
    """Strictly validate one receipt against trusted plans and independent evidence."""
    failures: list[str] = []
    cell_fd: int | None = None
    try:
        if trusted_root_fd is None:
            cell_fd = _open_root(cell_root)
        else:
            if cell_relative is None:
                raise ValueError("Pinned-root validation requires a cell-relative path")
            cell_fd = _open_beneath(
                trusted_root_fd, canonical_relative_path(cell_relative), directory=True
            )
    except (OSError, RuntimeError, TypeError, ValueError):
        failures.append("CELL_ROOT_ISOLATION_MISMATCH")

    def read_cell(relative: str) -> bytes:
        if cell_fd is None:
            raise ValueError("Cell root is unavailable")
        return _read_regular_at(cell_fd, relative)

    try:
        validate_receipt_schema_v2(receipt)
    except (TypeError, ValueError):
        failures.append("RECEIPT_SCHEMA_MISMATCH")
    if receipt.get("schema_version") != 2 or isinstance(
        receipt.get("schema_version"), bool
    ):
        failures.append("RECEIPT_SCHEMA_MISMATCH")
    unsigned = dict(receipt)
    claimed_hash = unsigned.pop("receipt_hash", None)
    try:
        receipt_hash_valid = claimed_hash == _sha256(unsigned)
    except (TypeError, ValueError):
        receipt_hash_valid = False
    if not receipt_hash_valid:
        failures.append("RECEIPT_HASH_MISMATCH")
    if (receipt.get("repo_id"), receipt.get("arm_id"), receipt.get("attempt")) != (
        plan.repo_id,
        plan.arm_id,
        1,
    ):
        failures.append("CELL_IDENTITY_MISMATCH")
    if (
        receipt.get("plan_hash") != plan.digest
        or receipt.get("artifact_path") != plan.artifact_path
    ):
        failures.append("PLAN_BINDING_MISMATCH")
    try:
        eligibility_valid = _sha256(receipt.get("eligibility")) == _sha256(
            asdict(plan.eligibility)
        )
    except (TypeError, ValueError):
        eligibility_valid = False
    if not eligibility_valid:
        failures.append("SOURCE_ELIGIBILITY_MISMATCH")
    try:
        harness_bytes_valid = (
            HarnessArtifactV1.read(Path(plan.tool.path)) == plan.tool
            and HarnessArtifactV1.read(Path(plan.config.path)) == plan.config
        )
    except (OSError, ValueError):
        harness_bytes_valid = False
    if (
        receipt.get("tool") != asdict(plan.tool)
        or receipt.get("config") != asdict(plan.config)
        or not harness_bytes_valid
    ):
        failures.append("HARNESS_BYTES_MISMATCH")
    try:
        counters_valid = _canonical_json_bytes(receipt.get("counters")) == (
            _canonical_json_bytes(ZERO_COUNTERS)
        )
    except (TypeError, ValueError):
        counters_valid = False
    if not counters_valid:
        failures.append("FORBIDDEN_COUNTER_MISMATCH")

    observation = receipt.get("resource_observation")
    if (
        not isinstance(observation, Mapping)
        or receipt.get("resource_plan_hash") != plan.resources.digest
    ):
        failures.append("RESOURCE_EVIDENCE_MISSING")
    else:
        maxima = (
            ("wall_seconds", plan.resources.wall_timeout_seconds),
            ("cpu_seconds", plan.resources.max_cpu_seconds),
            ("index_bytes", plan.resources.max_index_bytes),
            ("disk_written_bytes", plan.resources.max_disk_write_bytes),
            ("peak_rss_bytes", plan.resources.max_rss_bytes),
            ("peak_processes", plan.resources.max_processes),
            ("peak_open_files", plan.resources.max_open_files),
            ("peak_concurrency", 1),
        )
        values = (
            ("free_disk_bytes_before", observation.get("free_disk_bytes_before")),
            *((key, observation.get(key)) for key, _ in maxima),
        )
        numeric = all(_is_finite_number(value) for _, value in values)
        if (
            not numeric
            or observation["free_disk_bytes_before"]
            < plan.resources.min_free_disk_bytes
            or any(
                observation[key] < 0 or observation[key] > ceiling
                for key, ceiling in maxima
            )
        ):
            failures.append("RESOURCE_LIMIT_VIOLATION")

    partition = receipt.get("index_partition")
    try:
        if not isinstance(partition, Mapping):
            raise ValueError
        indexed = _sorted_paths(partition.get("indexed_paths", ()), "indexed")
        excluded = _sorted_paths(partition.get("excluded_paths", ()), "excluded")
        errors = _sorted_paths(partition.get("parse_error_paths", ()), "parse-error")
        allowlist = _sorted_paths(
            partition.get("parse_error_allowlist", ()), "parse-error allowlist"
        )
        if allowlist != plan.parse_error_allowlist:
            raise ValueError
        eligible = set(plan.eligibility.eligible_paths)
        groups = (set(indexed), set(excluded), set(errors))
        if any(groups[a] & groups[b] for a, b in ((0, 1), (0, 2), (1, 2))):
            raise ValueError
        if set().union(*groups) != eligible or set(errors) != set(allowlist):
            raise ValueError
        if (
            partition.get("indexed_paths_hash") != _sha256(list(indexed))
            or partition.get("excluded_paths_hash") != _sha256(list(excluded))
            or partition.get("parse_error_paths_hash") != _sha256(list(errors))
        ):
            raise ValueError
    except (TypeError, ValueError):
        failures.append("INDEX_PARTITION_MISMATCH")

    index_relative = receipt.get("index_path")
    try:
        if not isinstance(index_relative, str) or cell_fd is None:
            raise ValueError
        canonical_relative_path(index_relative)
        actual_index_hash = _hash_tree_at(
            cell_fd, index_relative, max_bytes=plan.resources.max_index_bytes
        )
        actual_index_bytes = _tree_size_at(cell_fd, index_relative)
        if (
            actual_index_hash != receipt.get("index_content_hash")
            or not isinstance(observation, Mapping)
            or observation.get("index_bytes") != actual_index_bytes
        ):
            raise ValueError
    except (OSError, RuntimeError, TypeError, ValueError):
        failures.append("INDEX_BYTES_MISMATCH")
        actual_index_hash = None

    def valid_blob(raw: object) -> bytes | None:
        """Return the exact authenticated bytes from the single safe open."""
        if not isinstance(raw, Mapping):
            return None
        relative = raw.get("path")
        if not isinstance(relative, str):
            return None
        try:
            payload = read_cell(relative)
        except (OSError, RuntimeError, TypeError, ValueError):
            return None
        if raw.get("size_bytes") != len(payload) or raw.get("sha256") != _bytes_hash(
            payload
        ):
            return None
        return payload

    executions = receipt.get("raw_executions")
    expected_executions = plan.executions
    expected_ids = tuple(spec.execution_id for spec in expected_executions)
    raw_paths: list[str] = []
    execution_valid = (
        isinstance(executions, list)
        and tuple(item.get("id") for item in executions if isinstance(item, Mapping))
        == expected_ids
    )
    if isinstance(executions, list) and execution_valid:
        specs = {spec.oracle_id: spec for spec in plan.oracle_specs}
        frozen_argv = {
            spec.execution_id: list(spec.argv) for spec in expected_executions
        }
        for item in executions:
            blob_keys = ("stdout_bytes", "stderr_bytes", "query_bytes", "index_bytes")
            blobs = tuple(item.get(key) for key in blob_keys)
            raw_paths.extend(
                blob.get("path", "") for blob in blobs if isinstance(blob, Mapping)
            )
            authenticated = tuple(valid_blob(blob) for blob in blobs)
            if (
                item.get("exit_code") != 0
                or isinstance(item.get("exit_code"), bool)
                or item.get("argv") != frozen_argv.get(item.get("id"))
                or any(payload is None for payload in authenticated)
            ):
                execution_valid = False
                break
            if item["id"] not in specs and "oracle_spec_hash" in item:
                execution_valid = False
                break
            if item["id"] in specs:
                spec = specs[item["id"]]
                query_payload = authenticated[2]
                result_payload = authenticated[0]
                if query_payload is None or result_payload is None:
                    execution_valid = False
                    break
                try:
                    query = _strict_json_bytes(query_payload)
                    result = _strict_json_bytes(result_payload)
                    query_matches = _canonical_json_bytes(
                        query
                    ) == _canonical_json_bytes(dict(spec.query))
                    result_matches = _canonical_json_bytes(
                        result
                    ) == _canonical_json_bytes(spec.expected_result)
                except (TypeError, ValueError, json.JSONDecodeError):
                    execution_valid = False
                    break
                if (
                    item.get("oracle_spec_hash") != spec.digest
                    or not query_matches
                    or not result_matches
                ):
                    execution_valid = False
                    break
    if not execution_valid or len(raw_paths) != len(set(raw_paths)):
        failures.append("RAW_EXECUTION_EVIDENCE_MISSING")

    audit = receipt.get("os_audit")
    required_audit = {
        "network_denied": True,
        "credentials_stripped": True,
        "descendants_observed": True,
        "process_audited": True,
    }
    audit_blob = (
        valid_blob(audit.get("audit_bytes")) if isinstance(audit, Mapping) else None
    )
    try:
        core_payload = _evidence_core_payload(
            receipt, plan=plan, actual_index_hash=actual_index_hash
        )
        core_digest = _bytes_hash(_canonical_json_bytes(core_payload))
    except (TypeError, ValueError):
        core_digest = None
        failures.append("EVIDENCE_CORE_CANONICALIZATION_FAILED")
    executor_payload = {
        "schema_version": 1,
        "plan_hash": plan.digest,
        "evidence_core_digest": core_digest,
    }
    provenance = receipt.get("index_provenance")
    if (
        core_digest is None
        or not isinstance(provenance, Mapping)
        or provenance.get("payload") != executor_payload
        or not _verify_signature(
            key_id=provenance.get("key_id"),
            signature=provenance.get("signature"),
            payload=executor_payload,
            expected_key_id=verifier_config.executor_key_id,
            public_key=verifier_config.executor_public_key,
        )
    ):
        failures.append("INDEX_PROVENANCE_MISSING")
    if (
        core_digest is None
        or not isinstance(audit, Mapping)
        or any(audit.get(k) != v for k, v in required_audit.items())
        or audit_blob is None
        or audit.get("payload") != executor_payload
        or not _verify_signature(
            key_id=audit.get("key_id"),
            signature=audit.get("signature"),
            payload=executor_payload,
            expected_key_id=verifier_config.executor_key_id,
            public_key=verifier_config.executor_public_key,
        )
    ):
        failures.append("OS_AUDIT_MISSING")

    approval = receipt.get("human_oracle_approval")
    approval_blob = (
        valid_blob(approval.get("approval_bytes"))
        if isinstance(approval, Mapping)
        else None
    )
    approval_bytes = (
        approval.get("approval_bytes") if isinstance(approval, Mapping) else None
    )
    approval_payload = {
        "schema_version": 1,
        "plan_hash": plan.digest,
        "evidence_core_digest": core_digest,
        "approved": True,
        "approval_blob_hash": approval_bytes.get("sha256")
        if isinstance(approval_bytes, Mapping)
        else None,
    }
    if (
        core_digest is None
        or not isinstance(approval, Mapping)
        or approval.get("approved") is not True
        or approval_blob is None
        or approval.get("payload") != approval_payload
        or approval.get("key_id") == verifier_config.executor_key_id
        or not _verify_signature(
            key_id=approval.get("key_id"),
            signature=approval.get("signature"),
            payload=approval_payload,
            expected_key_id=verifier_config.approver_key_id,
            public_key=verifier_config.approver_public_key,
        )
    ):
        failures.append("HUMAN_ORACLE_APPROVAL_MISSING")
    if cell_fd is not None:
        os.close(cell_fd)
    return tuple(dict.fromkeys(failures))
