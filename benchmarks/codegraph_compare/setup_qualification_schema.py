"""Closed recursive JSON schema for NO1-008A cell receipts."""

from __future__ import annotations

import json
import math
from pathlib import PurePosixPath
from typing import Any

from benchmarks.codegraph_compare.setup_qualification_paths import (
    canonical_relative_path,
)
from benchmarks.codegraph_compare.setup_qualification_plan import (
    INDEXED_ARMS,
    REPOSITORIES,
    ZERO_COUNTERS,
)

_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "repo_id",
        "arm_id",
        "attempt",
        "plan_hash",
        "artifact_path",
        "eligibility",
        "tool",
        "config",
        "counters",
        "resource_plan_hash",
        "resource_observation",
        "index_path",
        "index_content_hash",
        "index_partition",
        "raw_executions",
        "index_provenance",
        "os_audit",
        "human_oracle_approval",
        "receipt_hash",
    }
)
_BLOB_KEYS = frozenset({"path", "size_bytes", "sha256"})
_EXECUTION_KEYS = frozenset(
    {
        "id",
        "argv",
        "exit_code",
        "stdout_bytes",
        "stderr_bytes",
        "query_bytes",
        "index_bytes",
    }
)
_SIGNATURE_KEYS = frozenset({"payload", "key_id", "signature"})
_EXECUTOR_PAYLOAD_KEYS = frozenset(
    {"schema_version", "plan_hash", "evidence_core_digest"}
)
_HASH_FIELDS = (
    "source_rules_hash",
    "tracked_inventory_hash",
    "eligible_paths_hash",
    "repo_fingerprint",
)
_EXCLUSION_REASONS = frozenset(
    {"extension", "excluded-component", "minified", "generated", "gitlink", "symlink"}
)


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON member: {key}")
        result[key] = value
    return result


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"Non-finite JSON number is forbidden: {value}")
    return parsed


_MAX_STRICT_JSON_BYTES = 4 * 1024 * 1024
_MAX_STRICT_JSON_DEPTH = 128


def _validate_json_envelope(payload: bytes) -> None:
    if type(payload) is not bytes:
        raise ValueError("Strict JSON input must be bytes")
    if len(payload) > _MAX_STRICT_JSON_BYTES:
        raise ValueError("Strict JSON exceeds the trusted size limit")
    depth = 0
    in_string = False
    escaped = False
    for byte in payload:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:  # backslash
                escaped = True
            elif byte == 0x22:  # quote
                in_string = False
        elif byte == 0x22:
            in_string = True
        elif byte in (0x5B, 0x7B):  # [ {
            depth += 1
            if depth > _MAX_STRICT_JSON_DEPTH:
                raise ValueError("Strict JSON exceeds the trusted nesting limit")
        elif byte in (0x5D, 0x7D):  # ] }
            depth -= 1
            if depth < 0:
                break


def strict_json_loads(payload: bytes) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON number is forbidden: {value}")

    _validate_json_envelope(payload)
    try:
        return json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_members,
            parse_constant=reject_constant,
            parse_float=_parse_finite_float,
        )
    except RecursionError as exc:
        raise ValueError("Strict JSON nesting is a validation violation") from exc


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _strict_json_bytes(payload: bytes) -> Any:
    return strict_json_loads(payload)


def _require_exact_keys(
    value: object, expected: frozenset[str], name: str
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise ValueError(f"{name} must contain exactly the schema-v2 keys")
    return value


def _require_string(value: object, name: str, *, nonempty: bool = True) -> str:
    if type(value) is not str or (nonempty and not value):
        raise ValueError(f"{name} must be a JSON string")
    return value


def _require_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a JSON boolean")
    return value


def _require_int(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be a JSON integer >= {minimum}")
    return value


def _require_number(value: object, name: str, *, minimum: float = 0) -> int | float:
    number: int | float
    if type(value) is int:
        number = value
    elif type(value) is float and math.isfinite(value):
        number = value
    else:
        raise ValueError(f"{name} must be a finite JSON number >= {minimum}")
    if number < minimum:
        raise ValueError(f"{name} must be a finite JSON number >= {minimum}")
    return number


def _require_hash(value: object, name: str, *, length: int = 64) -> str:
    text = _require_string(value, name)
    if len(text) != length or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{name} must be a lowercase hexadecimal digest")
    return text


def _require_path(value: object, name: str, *, absolute: bool = False) -> str:
    text = _require_string(value, name)
    if absolute:
        path = PurePosixPath(text)
        if not path.is_absolute() or str(path) != text or ".." in path.parts:
            raise ValueError(f"{name} must be a canonical absolute POSIX path")
    else:
        canonical_relative_path(text)
    return text


def _require_string_array(
    value: object, name: str, *, paths: bool = False
) -> list[str]:
    if type(value) is not list:
        raise ValueError(f"{name} must be a JSON array")
    for number, item in enumerate(value):
        if paths:
            _require_path(item, f"{name}[{number}]")
        else:
            _require_string(item, f"{name}[{number}]")
    return value


def _validate_blob(value: object, name: str, *, absolute: bool = False) -> None:
    blob = _require_exact_keys(value, _BLOB_KEYS, name)
    _require_path(blob["path"], f"{name}.path", absolute=absolute)
    _require_int(blob["size_bytes"], f"{name}.size_bytes")
    _require_hash(blob["sha256"], f"{name}.sha256")


def _validate_executor_payload(value: object, name: str) -> None:
    payload = _require_exact_keys(value, _EXECUTOR_PAYLOAD_KEYS, name)
    if (
        _require_int(payload["schema_version"], f"{name}.schema_version", minimum=1)
        != 1
    ):
        raise ValueError(f"{name}.schema_version must equal 1")
    _require_hash(payload["plan_hash"], f"{name}.plan_hash")
    _require_hash(payload["evidence_core_digest"], f"{name}.evidence_core_digest")


def validate_receipt_schema_v2(receipt: object) -> None:
    """Validate exact container/scalar types and constraints at every depth."""
    root = _require_exact_keys(receipt, _RECEIPT_KEYS, "receipt")
    if _require_int(root["schema_version"], "schema_version", minimum=1) != 2:
        raise ValueError("schema_version must equal 2")
    repo = _require_string(root["repo_id"], "repo_id")
    arm = _require_string(root["arm_id"], "arm_id")
    if repo not in REPOSITORIES or arm not in INDEXED_ARMS:
        raise ValueError("receipt cell identity is outside the canonical enumeration")
    if _require_int(root["attempt"], "attempt", minimum=1) != 1:
        raise ValueError("attempt must equal integer 1")
    for name in (
        "plan_hash",
        "resource_plan_hash",
        "index_content_hash",
        "receipt_hash",
    ):
        _require_hash(root[name], name)
    _require_path(root["artifact_path"], "artifact_path")
    _require_path(root["index_path"], "index_path")

    eligibility = _require_exact_keys(
        root["eligibility"],
        frozenset(
            {
                "repo_id",
                "source_rules_hash",
                "commit",
                "tracked_regular_paths",
                "eligible_paths",
                "prefilter_exclusions",
                "tracked_inventory_hash",
                "eligible_paths_hash",
                "repo_fingerprint",
            }
        ),
        "eligibility",
    )
    if (
        _require_string(eligibility["repo_id"], "eligibility.repo_id")
        not in REPOSITORIES
    ):
        raise ValueError("eligibility.repo_id is outside the canonical enumeration")
    for name in _HASH_FIELDS:
        _require_hash(eligibility[name], f"eligibility.{name}")
    _require_hash(eligibility["commit"], "eligibility.commit", length=40)
    for name in ("tracked_regular_paths", "eligible_paths"):
        _require_string_array(eligibility[name], f"eligibility.{name}", paths=True)
    exclusions = eligibility["prefilter_exclusions"]
    if type(exclusions) is not list:
        raise ValueError("eligibility.prefilter_exclusions must be a JSON array")
    for number, item in enumerate(exclusions):
        if type(item) is not list or len(item) != 2:
            raise ValueError(
                f"eligibility.prefilter_exclusions[{number}] must be a pair"
            )
        _require_path(item[0], f"eligibility.prefilter_exclusions[{number}][0]")
        if (
            _require_string(item[1], f"eligibility.prefilter_exclusions[{number}][1]")
            not in _EXCLUSION_REASONS
        ):
            raise ValueError("prefilter exclusion reason is outside the enumeration")

    for name in ("tool", "config"):
        _validate_blob(root[name], name, absolute=True)
    counters = _require_exact_keys(
        root["counters"], frozenset(ZERO_COUNTERS), "counters"
    )
    for name, value in counters.items():
        if name == "api_cost_usd":
            _require_number(value, f"counters.{name}")
        else:
            _require_int(value, f"counters.{name}")

    observation = _require_exact_keys(
        root["resource_observation"],
        frozenset(
            {
                "wall_seconds",
                "cpu_seconds",
                "index_bytes",
                "disk_written_bytes",
                "free_disk_bytes_before",
                "peak_rss_bytes",
                "peak_processes",
                "peak_open_files",
                "peak_concurrency",
            }
        ),
        "resource_observation",
    )
    for name in ("wall_seconds", "cpu_seconds"):
        _require_number(observation[name], f"resource_observation.{name}")
    for name in set(observation) - {"wall_seconds", "cpu_seconds"}:
        _require_int(observation[name], f"resource_observation.{name}")

    partition = _require_exact_keys(
        root["index_partition"],
        frozenset(
            {
                "indexed_paths",
                "excluded_paths",
                "parse_error_paths",
                "parse_error_allowlist",
                "indexed_paths_hash",
                "excluded_paths_hash",
                "parse_error_paths_hash",
            }
        ),
        "index_partition",
    )
    for name in (
        "indexed_paths",
        "excluded_paths",
        "parse_error_paths",
        "parse_error_allowlist",
    ):
        _require_string_array(partition[name], f"index_partition.{name}", paths=True)
    for name in ("indexed_paths_hash", "excluded_paths_hash", "parse_error_paths_hash"):
        _require_hash(partition[name], f"index_partition.{name}")

    executions = root["raw_executions"]
    if type(executions) is not list:
        raise ValueError("raw_executions must be a JSON array")
    for number, execution_value in enumerate(executions):
        name = f"raw_executions[{number}]"
        if type(execution_value) is not dict:
            raise ValueError(f"{name} must be a JSON object")
        identifier = _require_string(execution_value.get("id"), f"{name}.id")
        expected = (
            _EXECUTION_KEYS
            if identifier in {"delete", "build", "health"}
            else _EXECUTION_KEYS | {"oracle_spec_hash"}
        )
        execution = _require_exact_keys(execution_value, expected, name)
        argv = _require_string_array(execution["argv"], f"{name}.argv")
        if not argv:
            raise ValueError(f"{name}.argv must not be empty")
        _require_int(execution["exit_code"], f"{name}.exit_code")
        if "oracle_spec_hash" in execution:
            _require_hash(execution["oracle_spec_hash"], f"{name}.oracle_spec_hash")
        for blob_name in ("stdout_bytes", "stderr_bytes", "query_bytes", "index_bytes"):
            _validate_blob(execution[blob_name], f"{name}.{blob_name}")

    provenance = _require_exact_keys(
        root["index_provenance"], _SIGNATURE_KEYS, "index_provenance"
    )
    _validate_executor_payload(provenance["payload"], "index_provenance.payload")
    _require_string(provenance["key_id"], "index_provenance.key_id")
    _require_hash(provenance["signature"], "index_provenance.signature", length=128)

    audit = _require_exact_keys(
        root["os_audit"],
        _SIGNATURE_KEYS
        | {
            "network_denied",
            "credentials_stripped",
            "descendants_observed",
            "process_audited",
            "audit_bytes",
        },
        "os_audit",
    )
    _validate_executor_payload(audit["payload"], "os_audit.payload")
    _require_string(audit["key_id"], "os_audit.key_id")
    _require_hash(audit["signature"], "os_audit.signature", length=128)
    for name in (
        "network_denied",
        "credentials_stripped",
        "descendants_observed",
        "process_audited",
    ):
        _require_bool(audit[name], f"os_audit.{name}")
    _validate_blob(audit["audit_bytes"], "os_audit.audit_bytes")

    approval = _require_exact_keys(
        root["human_oracle_approval"],
        _SIGNATURE_KEYS
        | {
            "approved",
            "approval_bytes",
        },
        "human_oracle_approval",
    )
    approval_payload = _require_exact_keys(
        approval["payload"],
        _EXECUTOR_PAYLOAD_KEYS
        | {
            "approved",
            "approval_blob_hash",
        },
        "human_oracle_approval.payload",
    )
    _validate_executor_payload(
        {key: approval_payload[key] for key in _EXECUTOR_PAYLOAD_KEYS},
        "human_oracle_approval.payload",
    )
    _require_bool(
        approval_payload["approved"], "human_oracle_approval.payload.approved"
    )
    _require_hash(
        approval_payload["approval_blob_hash"],
        "human_oracle_approval.payload.approval_blob_hash",
    )
    _require_string(approval["key_id"], "human_oracle_approval.key_id")
    _require_hash(approval["signature"], "human_oracle_approval.signature", length=128)
    _require_bool(approval["approved"], "human_oracle_approval.approved")
    _validate_blob(approval["approval_bytes"], "human_oracle_approval.approval_bytes")
