"""Filesystem and signature validation for NO1-008A receipts."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.integrity import _sha256
from benchmarks.codegraph_compare.setup_qualification_paths import (
    _hash_regular_descriptor,
    _open_beneath,
    _snapshot_tree_at,
    _stable_directory_identity,
    _stable_file_identity,
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
    _MAX_STRICT_JSON_BYTES,
    _canonical_json_bytes,
    _strict_json_bytes,
    validate_direct_json_bounds,
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
            "source_checkout_path": plan.source_checkout_path,
        },
        "tool": receipt.get("tool"),
        "config": receipt.get("config"),
        "oracle_specs": [
            {
                "oracle_id": spec.oracle_id,
                "kind": spec.kind,
                "query": spec.query,
                "expected_result": json.loads(spec.expected_result),
            }
            for spec in plan.oracle_specs
        ],
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
        "snapshot_audit": receipt.get("snapshot_audit", {}).get("payload")
        if isinstance(receipt.get("snapshot_audit"), Mapping)
        else None,
        "audit": {
            "network_denied": audit_mapping.get("network_denied"),
            "credentials_stripped": audit_mapping.get("credentials_stripped"),
            "descendants_observed": audit_mapping.get("descendants_observed"),
            "process_audited": audit_mapping.get("process_audited"),
            "audit_bytes": audit_mapping.get("audit_bytes"),
        },
    }


def _read_retained_receipt(
    *, cell_fd: int, plan: CellPlanV1, supplied: Mapping[str, Any]
) -> dict[str, Any]:
    """Stably read the plan-bound receipt from the pinned cell snapshot."""
    cell_namespace = f"cells/{plan.repo_id}/{plan.arm_id}/"
    if not plan.artifact_path.startswith(cell_namespace):
        raise ValueError("Receipt artifact is outside its canonical cell namespace")
    relative = canonical_relative_path(plan.artifact_path[len(cell_namespace) :])
    descriptor: int | None = None
    try:
        descriptor = _open_beneath(cell_fd, relative)
        metadata = os.fstat(descriptor)
        identity = _stable_file_identity(metadata)
        size = metadata.st_size
        first_hash = _hash_regular_descriptor(
            descriptor, expected_size=size, max_bytes=_MAX_STRICT_JSON_BYTES
        )
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                raise ValueError("Retained receipt ended before its trusted size")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError("Retained receipt grew during its trusted read")
        payload = b"".join(chunks)
        os.lseek(descriptor, 0, os.SEEK_SET)
        second_hash = _hash_regular_descriptor(
            descriptor, expected_size=size, max_bytes=_MAX_STRICT_JSON_BYTES
        )
        if (
            first_hash != second_hash
            or hashlib.sha256(payload).hexdigest() != first_hash
            or _stable_file_identity(os.fstat(descriptor)) != identity
        ):
            raise ValueError("Retained receipt changed during validation")
        retained = _strict_json_bytes(payload)
        if type(retained) is not dict or type(supplied) is not dict or not retained:
            raise ValueError("Retained receipt must be a non-empty exact JSON object")
        if _canonical_json_bytes(retained) != _canonical_json_bytes(
            supplied
        ) or _sha256(retained) != _sha256(supplied):
            raise ValueError("Retained receipt differs from the supplied mapping")
        return retained
    finally:
        if descriptor is not None:
            os.close(descriptor)


def validate_cell_receipt(
    receipt: Mapping[str, Any],
    *,
    plan: CellPlanV1,
    cell_root: Path,
    verifier_config: VerifierConfigV1,
    trusted_root_fd: int | None = None,
    trusted_root_identity: tuple[int, ...] | None = None,
    cell_relative: str | None = None,
) -> tuple[str, ...]:
    """Strictly validate one receipt against trusted plans and independent evidence."""
    failures: list[str] = []
    try:
        validate_direct_json_bounds(receipt)
    except (RecursionError, TypeError, ValueError):
        return ("RECEIPT_SCHEMA_MISMATCH",)
    cell_fd: int | None = None
    try:
        if (
            trusted_root_fd is None
            or trusted_root_identity is None
            or cell_relative is None
            or _stable_directory_identity(os.fstat(trusted_root_fd))
            != trusted_root_identity
        ):
            raise ValueError(
                "Untrusted validation requires a pinned experiment-root identity"
            )
        cell_fd = _open_beneath(
            trusted_root_fd, canonical_relative_path(cell_relative), directory=True
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        failures.append("CELL_ROOT_ISOLATION_MISMATCH")
    try:
        retained_receipt = receipt
        if cell_fd is not None:
            try:
                retained_receipt = _read_retained_receipt(
                    cell_fd=cell_fd, plan=plan, supplied=receipt
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                failures.append("RETAINED_RECEIPT_MISMATCH")
                return tuple(dict.fromkeys(failures))
        return _validate_open_cell_receipt(
            retained_receipt,
            plan=plan,
            verifier_config=verifier_config,
            failures=failures,
            cell_fd=cell_fd,
            cell_root_identity=(
                _stable_directory_identity(os.fstat(cell_fd))
                if cell_fd is not None
                else None
            ),
        )
    finally:
        if cell_fd is not None:
            os.close(cell_fd)


def _validate_open_cell_receipt(
    receipt: Mapping[str, Any],
    *,
    plan: CellPlanV1,
    verifier_config: VerifierConfigV1,
    failures: list[str],
    cell_fd: int | None,
    cell_root_identity: tuple[int, ...] | None,
) -> tuple[str, ...]:
    direct_json_bounded = True
    try:
        validate_direct_json_bounds(receipt)
    except (RecursionError, TypeError, ValueError):
        direct_json_bounded = False
        failures.append("RECEIPT_SCHEMA_MISMATCH")
    try:
        validate_receipt_schema_v2(receipt)
    except (RecursionError, TypeError, ValueError):
        failures.append("RECEIPT_SCHEMA_MISMATCH")
    if receipt.get("schema_version") != 2 or isinstance(
        receipt.get("schema_version"), bool
    ):
        failures.append("RECEIPT_SCHEMA_MISMATCH")
    unsigned = dict(receipt)
    claimed_hash = unsigned.pop("receipt_hash", None)
    try:
        receipt_hash_valid = direct_json_bounded and claimed_hash == _sha256(unsigned)
    except (RecursionError, TypeError, ValueError):
        receipt_hash_valid = False
    if not receipt_hash_valid:
        failures.append("RECEIPT_HASH_MISMATCH")
    if not direct_json_bounded:
        return tuple(dict.fromkeys(failures))
    if (receipt.get("repo_id"), receipt.get("arm_id"), receipt.get("attempt")) != (
        plan.repo_id,
        plan.arm_id,
        1,
    ):
        failures.append("CELL_IDENTITY_MISMATCH")
    if (
        receipt.get("plan_hash") != plan.digest
        or receipt.get("artifact_path") != plan.artifact_path
        or receipt.get("index_path") != plan.index_path
    ):
        failures.append("PLAN_BINDING_MISMATCH")
    snapshot_audit = receipt.get("snapshot_audit")
    snapshot_payload = (
        snapshot_audit.get("payload") if isinstance(snapshot_audit, Mapping) else None
    )
    expected_snapshot_facts = {
        "schema_version": 1,
        "plan_hash": plan.digest,
        "snapshot_id": snapshot_payload.get("snapshot_id")
        if isinstance(snapshot_payload, Mapping)
        else None,
        "root_identity": list(cell_root_identity)
        if cell_root_identity is not None
        else None,
        "mount": {"read_only": True},
        "producer_descendants": 0,
        "writes_blocked": True,
    }
    snapshot_trusted = (
        isinstance(snapshot_audit, Mapping)
        and isinstance(snapshot_payload, Mapping)
        and isinstance(snapshot_payload.get("snapshot_id"), str)
        and bool(snapshot_payload.get("snapshot_id"))
        and snapshot_payload == expected_snapshot_facts
        and _verify_signature(
            key_id=snapshot_audit.get("key_id"),
            signature=snapshot_audit.get("signature"),
            payload=snapshot_payload,
            expected_key_id=verifier_config.executor_key_id,
            public_key=verifier_config.executor_public_key,
        )
    )
    if not snapshot_trusted:
        failures.append("SNAPSHOT_AUDIT_MISSING")

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
            HarnessArtifactV1.read(
                Path(plan.tool.path), expected_size=plan.tool.size_bytes
            )
            == plan.tool
            and HarnessArtifactV1.read(
                Path(plan.config.path), expected_size=plan.config.size_bytes
            )
            == plan.config
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
        if (
            allowlist != plan.parse_error_allowlist
            or excluded != plan.explicit_excluded_allowlist
        ):
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

    index_path = receipt.get("index_path")
    try:
        if index_path != plan.index_path or cell_fd is None or not snapshot_trusted:
            raise ValueError
        canonical_relative_path(index_path)
        cell_namespace = f"cells/{plan.repo_id}/{plan.arm_id}/"
        if not index_path.startswith(cell_namespace):
            raise ValueError
        index_relative = index_path[len(cell_namespace) :]
        canonical_relative_path(index_relative)
        (
            actual_index_hash,
            actual_index_bytes,
            _actual_index_directories,
            _actual_index_files,
        ) = _snapshot_tree_at(
            cell_fd, index_relative, max_bytes=plan.resources.max_index_bytes
        )
        if (
            actual_index_hash != receipt.get("index_content_hash")
            or not isinstance(observation, Mapping)
            or observation.get("index_bytes") != actual_index_bytes
        ):
            raise ValueError
    except (OSError, RuntimeError, TypeError, ValueError):
        failures.append("INDEX_BYTES_MISMATCH")
        actual_index_hash = None

    blob_bytes_consumed = 0
    per_blob_ceiling = min(
        plan.resources.max_index_bytes, plan.resources.max_disk_write_bytes
    )
    cumulative_blob_ceiling = plan.resources.max_disk_write_bytes
    json_materialization_ceiling = min(per_blob_ceiling, 1024 * 1024)

    def valid_blob(
        raw: object, *, materialize_json: bool = False
    ) -> tuple[bool, bytes | None]:
        """Authenticate one blob from the signed read-only cell snapshot twice."""
        nonlocal blob_bytes_consumed
        if type(raw) is not dict or cell_fd is None or not snapshot_trusted:
            return False, None
        relative = raw.get("path")
        claimed_size = raw.get("size_bytes")
        if (
            not isinstance(relative, str)
            or not relative.startswith("raw/")
            or type(claimed_size) is not int
        ):
            return False, None
        descriptor: int | None = None
        try:
            descriptor = _open_beneath(cell_fd, relative)
            metadata = os.fstat(descriptor)
            identity = _stable_file_identity(metadata)
            allocated = getattr(metadata, "st_blocks", 0) * 512
            if (
                metadata.st_size != claimed_size
                or metadata.st_size > per_blob_ceiling
                or blob_bytes_consumed + metadata.st_size > cumulative_blob_ceiling
                or (metadata.st_size > 0 and allocated < metadata.st_size)
                or (
                    materialize_json and metadata.st_size > json_materialization_ceiling
                )
            ):
                return False, None
            first_hash = _hash_regular_descriptor(
                descriptor,
                expected_size=claimed_size,
                max_bytes=per_blob_ceiling,
            )
            os.lseek(descriptor, 0, os.SEEK_SET)
            second_hash = _hash_regular_descriptor(
                descriptor,
                expected_size=claimed_size,
                max_bytes=per_blob_ceiling,
            )
            if (
                first_hash != second_hash
                or first_hash != raw.get("sha256")
                or _stable_file_identity(os.fstat(descriptor)) != identity
            ):
                return False, None
            payload: bytes | None = None
            if materialize_json:
                os.lseek(descriptor, 0, os.SEEK_SET)
                payload = os.read(descriptor, claimed_size + 1)
                if (
                    len(payload) != claimed_size
                    or hashlib.sha256(payload).hexdigest() != first_hash
                    or os.read(descriptor, 1)
                    or _stable_file_identity(os.fstat(descriptor)) != identity
                ):
                    return False, None
            blob_bytes_consumed += claimed_size
            return True, payload
        except (OSError, RuntimeError, TypeError, ValueError):
            return False, None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    executions = receipt.get("raw_executions")
    expected_executions = plan.executions
    expected_ids = tuple(spec.execution_id for spec in expected_executions)
    raw_paths: list[str] = []
    execution_valid = (
        type(executions) is list
        and all(type(item) is dict for item in executions)
        and tuple(item.get("id") for item in executions) == expected_ids
    )
    if isinstance(executions, list) and execution_valid:
        specs = {spec.oracle_id: spec for spec in plan.oracle_specs}
        frozen_argv = {
            spec.execution_id: list(spec.argv) for spec in expected_executions
        }
        frozen_cwd = {spec.execution_id: spec.cwd for spec in expected_executions}
        for item in executions:
            blob_keys = ("stdout_bytes", "stderr_bytes", "query_bytes", "index_bytes")
            blobs = tuple(item.get(key) for key in blob_keys)
            raw_paths.extend(
                blob.get("path", "") for blob in blobs if isinstance(blob, Mapping)
            )
            is_oracle = item["id"] in specs
            authenticated = tuple(
                valid_blob(
                    blob,
                    materialize_json=is_oracle
                    and key in {"stdout_bytes", "query_bytes"},
                )
                for key, blob in zip(blob_keys, blobs, strict=True)
            )
            if (
                item.get("exit_code") != 0
                or isinstance(item.get("exit_code"), bool)
                or item.get("argv") != frozen_argv.get(item.get("id"))
                or item.get("cwd") != frozen_cwd.get(item.get("id"))
                or item.get("environment_digest")
                != next(
                    spec.environment_digest
                    for spec in expected_executions
                    if spec.execution_id == item.get("id")
                )
                or any(not valid for valid, _ in authenticated)
            ):
                execution_valid = False
                break
            if item["id"] not in specs and "oracle_spec_hash" in item:
                execution_valid = False
                break
            if item["id"] in specs:
                spec = specs[item["id"]]
                query_payload = authenticated[2][1]
                result_payload = authenticated[0][1]
                if query_payload is None or result_payload is None:
                    execution_valid = False
                    break
                try:
                    query = _strict_json_bytes(query_payload)
                    result = _strict_json_bytes(result_payload)
                    query_matches = _canonical_json_bytes(
                        query
                    ) == _canonical_json_bytes(dict(spec.query))
                    result_matches = (
                        _canonical_json_bytes(result) == spec.expected_result
                    )
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
    audit_blob_valid = (
        valid_blob(audit.get("audit_bytes"))[0] if isinstance(audit, Mapping) else False
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
        or not audit_blob_valid
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
    approval_blob_valid = (
        valid_blob(approval.get("approval_bytes"))[0]
        if isinstance(approval, Mapping)
        else False
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
        or not approval_blob_valid
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
    return tuple(dict.fromkeys(failures))
