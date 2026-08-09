"""Detached NO1-008A receipt-v3 signing contract.

This module is deliberately pure: it never discovers keys, snapshots, plans, or
trust roots.  Callers pass one role's raw key bytes and a closed receipt body.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# fmt: off
# Closed schema stays visibly compact and below the 500-line module cap.
DOMAIN = b"NO1-008A-CELL-RECEIPT-V3\0"
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX128 = re.compile(r"[0-9a-f]{128}\Z")
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 200_000
MAX_STRING_BYTES = 4 * 1024 * 1024
TMPFS_TARGET = Path("/").joinpath("tmp").as_posix()

BODY_KEYS = frozenset({
    "cell", "plan", "source", "environment", "counters", "resources",
    "executions", "index_partition", "snapshot", "process_audit", "oracle_approval", "run_nonce", "role_images",
})
COUNTER_KEYS = frozenset({
    "api_cost_usd", "input_tokens", "model_calls", "network_requests",
    "output_tokens", "provider_requests",
})
TOP_KEYS = frozenset({
    "schema_version", "body", "body_sha256", "executor_signature",
    "approver_signature", "receipt_hash",
})
SIGNATURE_KEYS = frozenset({"key_id", "algorithm", "signature"})
ELIGIBILITY_KEYS = frozenset({"repo_id", "source_rules_hash", "commit", "tracked_regular_paths", "tracked_entries", "tracked_files", "eligible_paths", "prefilter_exclusions", "tracked_inventory_hash", "eligible_paths_hash", "repo_fingerprint"})


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number rejected: {value}")


def strict_json_loads(payload: bytes) -> dict[str, Any]:
    """Parse bounded UTF-8 JSON while rejecting duplicates and non-JSON numbers."""
    if type(payload) is not bytes or not payload or len(payload) > MAX_JSON_BYTES:
        raise ValueError("receipt JSON byte size is invalid")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON member: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid receipt JSON") from error
    if type(value) is not dict:
        raise ValueError("receipt must be a JSON object")
    nodes = 0

    def walk(item: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError("receipt JSON complexity limit exceeded")
        if type(item) is str:
            if len(item.encode("utf-8")) > MAX_STRING_BYTES:
                raise ValueError("receipt JSON string limit exceeded")
        elif type(item) is list:
            for child in item:
                walk(child, depth + 1)
        elif type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError("receipt JSON member must be a string")
                walk(key, depth + 1)
                walk(child, depth + 1)
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("non-finite receipt number")
        elif item is not None and type(item) not in (bool, int):
            raise ValueError("unsupported receipt JSON value")

    walk(value, 0)
    return value


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("value is not canonical JSON") from error


def _exact(value: Any, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or frozenset(value) != keys:
        raise ValueError(f"{label} has unknown or missing fields")
    return value


def _text(value: Any, label: str, maximum: int = 4096) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise ValueError(f"{label} must be a bounded non-empty string")
    return value


def _hex(value: Any, label: str, pattern: re.Pattern[str] = _HEX64) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase hexadecimal")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an exact integer")
    return value


def _path(value: Any, label: str, *, absolute: bool = False) -> str:
    text = _text(value, label)
    if "," in text or "\\" in text or "//" in text or any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError(f"{label} is not canonical")
    parts = text.split("/")
    start = 1 if absolute else 0
    if absolute != text.startswith("/") or any(part in ("", ".", "..") for part in parts[start:]):
        raise ValueError(f"{label} is not canonical")
    return text


def _blob(value: Any, label: str) -> None:
    item = _exact(value, frozenset({"path", "size_bytes", "sha256"}), label)
    _path(item["path"], f"{label}.path")
    _integer(item["size_bytes"], f"{label}.size_bytes")
    _hex(item["sha256"], f"{label}.sha256")


def validate_body(body: Any) -> None:
    body = _exact(body, BODY_KEYS, "body")
    _hex(body["run_nonce"], "run_nonce")
    images = _exact(body["role_images"], frozenset({"producer", "executor", "approver", "verifier"}), "role_images")
    if any(re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None for value in images.values()) or len(set(images.values())) != 4:
        raise ValueError("role image digests must be exact and distinct")
    cell = _exact(body["cell"], frozenset({"repo_id", "arm_id", "attempt", "artifact_path"}), "cell")
    _text(cell["repo_id"], "cell.repo_id", 64)
    _text(cell["arm_id"], "cell.arm_id", 64)
    if cell["repo_id"] not in {"vscode", "excalidraw", "django", "tokio", "okhttp", "gin", "alamofire"} or cell["arm_id"] not in {"tsa-warm", "codegraph-warm"}:
        raise ValueError("cell identity must belong to the exact 14-cell manifest")
    if cell["attempt"] != 1 or type(cell["attempt"]) is not int:
        raise ValueError("cell attempt must be exact integer 1")
    _path(cell["artifact_path"], "cell.artifact_path")

    plan = _exact(body["plan"], frozenset({"plan_hash", "plan_set_hash", "tool_sha256", "config_sha256", "image_digest", "seccomp_sha256"}), "plan")
    for key in ("plan_hash", "plan_set_hash", "tool_sha256", "config_sha256", "seccomp_sha256"):
        _hex(plan[key], f"plan.{key}")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", _text(plan["image_digest"], "plan.image_digest")) is None:
        raise ValueError("plan image must use an exact lowercase sha256 digest")

    source = _exact(body["source"], frozenset({"commit", "eligibility", "repo_fingerprint", "mount_target", "read_only"}), "source")
    _text(source["commit"], "source.commit", 128)
    _hex(source["repo_fingerprint"], "source.repo_fingerprint")
    if source["read_only"] is not True or source["mount_target"] != "/source":
        raise ValueError("source mount must be /source read-only")
    eligibility = _exact(source["eligibility"], ELIGIBILITY_KEYS, "source.eligibility")
    _text(eligibility["repo_id"], "eligibility.repo_id", 64)
    _text(eligibility["commit"], "eligibility.commit", 128)
    for name in ("source_rules_hash", "tracked_inventory_hash", "eligible_paths_hash", "repo_fingerprint"):
        _hex(eligibility[name], f"eligibility.{name}")
    for name in ("tracked_regular_paths", "eligible_paths"):
        if type(eligibility[name]) is not list or eligibility[name] != sorted(set(eligibility[name])):
            raise ValueError(f"eligibility.{name} must be sorted and unique")
        for path in eligibility[name]:
            _path(path, f"eligibility.{name}")
    exclusions = eligibility["prefilter_exclusions"]
    if type(exclusions) is not list or any(type(item) is not list or len(item) != 2 or any(type(part) is not str or not part for part in item) for item in exclusions):
        raise ValueError("eligibility exclusions must be exact string pairs")

    environment = _exact(body["environment"], frozenset({"environment_digest", "image_digest", "docker_security_flags", "network_mode", "seccomp_sha256", "credentials_stripped"}), "environment")
    _hex(environment["environment_digest"], "environment.environment_digest")
    _hex(environment["seccomp_sha256"], "environment.seccomp_sha256")
    if environment["network_mode"] != "none" or environment["credentials_stripped"] is not True:
        raise ValueError("environment isolation is not exact")
    if type(environment["docker_security_flags"]) is not list or any(type(v) is not str for v in environment["docker_security_flags"]):
        raise ValueError("docker security flags must be exact strings")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", _text(environment["image_digest"], "environment.image_digest")) is None:
        raise ValueError("environment image must use an exact lowercase sha256 digest")

    counters = _exact(body["counters"], COUNTER_KEYS, "counters")
    if any(type(value) not in (int, float) or type(value) is bool or value != 0 for value in counters.values()):
        raise ValueError("all qualification counters must be exact zero")

    resources = _exact(body["resources"], frozenset({"plan_digest", "wall_ns", "cpu_usec", "io_bytes", "memory_peak_bytes", "pids_peak"}), "resources")
    _hex(resources["plan_digest"], "resources.plan_digest")
    for key, value in resources.items():
        if key != "plan_digest":
            _integer(value, f"resources.{key}")

    if type(body["executions"]) is not list or len(body["executions"]) != 5:
        raise ValueError("executions must contain exact delete/build/health/symbol/call order")
    execution_keys = frozenset({"id", "argv", "cwd", "environment_digest", "exit_code", "stdout_bytes", "stderr_bytes", "query_bytes", "final_index_observation"})
    execution_ids = [item.get("id") if type(item) is dict else None for item in body["executions"]]
    if execution_ids != ["delete", "build", "health", "symbol", "call"]:
        raise ValueError("executions must contain exact unique plan order")
    for number, execution in enumerate(body["executions"]):
        item = _exact(execution, execution_keys, f"executions[{number}]")
        _text(item["id"], "execution.id")
        _path(item["cwd"], "execution.cwd", absolute=True)
        if type(item["argv"]) is not list or not item["argv"] or any(type(arg) is not str or not arg or len(arg) > 4096 for arg in item["argv"]):
            raise ValueError("execution argv must be exact non-empty strings")
        _hex(item["environment_digest"], "execution.environment_digest")
        if type(item["exit_code"]) is not int:
            raise ValueError("execution exit code must be an exact integer")
        for name in ("stdout_bytes", "stderr_bytes", "query_bytes", "final_index_observation"):
            _blob(item[name], f"execution.{name}")

    partition = _exact(body["index_partition"], frozenset({"indexed_paths", "excluded_paths", "parse_error_paths", "indexed_paths_hash", "excluded_paths_hash", "parse_error_paths_hash"}), "index_partition")
    for name in ("indexed_paths", "excluded_paths", "parse_error_paths"):
        paths = partition[name]
        if type(paths) is not list or len(paths) != len(set(paths)):
            raise ValueError(f"{name} must be unique")
        for path in paths:
            _path(path, name)
    for name in ("indexed_paths_hash", "excluded_paths_hash", "parse_error_paths_hash"):
        _hex(partition[name], name)
    sets = [set(partition[name]) for name in ("indexed_paths", "excluded_paths", "parse_error_paths")]
    if any(sets[a] & sets[b] for a, b in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("index partition overlaps")

    snapshot = _exact(body["snapshot"], frozenset({"format", "data_image_sha256", "data_image_size", "hash_image_sha256", "hash_image_size", "root_hash", "salt", "data_block_size", "hash_block_size", "data_blocks", "tree_hash", "index_content_hash"}), "snapshot")
    if snapshot["format"] != "dm-verity-v1":
        raise ValueError("snapshot must use dm-verity-v1")
    for name in ("data_image_sha256", "hash_image_sha256", "root_hash", "tree_hash", "index_content_hash"):
        _hex(snapshot[name], f"snapshot.{name}")
    _hex(snapshot["salt"], "snapshot.salt")
    for name in ("data_image_size", "hash_image_size", "data_block_size", "hash_block_size", "data_blocks"):
        _integer(snapshot[name], f"snapshot.{name}", minimum=1)

    audit_keys = frozenset({"producer_container_id", "actual_image_id", "launch_token_sha256", "container_user", "readonly_rootfs", "cap_drop", "mounts", "resource_limits", "tmpfs", "image_digest", "cgroup_id", "network_mode", "security_opt", "restart_count", "terminal_pid", "launch_count", "cgroup_processes_after_stop", "pid1_exit", "run_nonce", "resource_observations", "audit_bytes"})
    audit = _exact(body["process_audit"], audit_keys, "process_audit")
    _hex(audit["run_nonce"], "process_audit.run_nonce")
    _hex(audit["launch_token_sha256"], "process_audit.launch_token_sha256")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", _text(audit["actual_image_id"], "process_audit.actual_image_id")) is None:
        raise ValueError("host audit actual image ID must be exact")
    if audit["container_user"] != "65532:65532" or audit["readonly_rootfs"] is not True or audit["cap_drop"] != ["ALL"]:
        raise ValueError("host audit container isolation facts invalid")
    if audit["resource_limits"] != {"pids_limit": 64, "memory": 4294967296, "nano_cpus": 1000000000} or audit["tmpfs"] != {TMPFS_TARGET: "rw,noexec,nosuid,nodev,size=64m"}:
        raise ValueError("host audit limits/tmpfs invalid")
    if type(audit["mounts"]) is not list or len(audit["mounts"]) != 4:
        raise ValueError("host audit mount facts invalid")
    for name in ("producer_container_id", "cgroup_id"):
        _text(audit[name], f"process_audit.{name}")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", _text(audit["image_digest"], "process_audit.image_digest")) is None:
        raise ValueError("host audit image digest must be exact")
    if audit["network_mode"] != "none" or audit["restart_count"] != 0 or audit["terminal_pid"] != 0 or audit["launch_count"] != 1 or audit["cgroup_processes_after_stop"] != [] or audit["pid1_exit"] != 0:
        raise ValueError("signed host audit is not terminal, isolated, and one-launch")
    if audit["resource_observations"] != {key: value for key, value in resources.items() if key != "plan_digest"}:
        raise ValueError("resources are not exact signed host observations")
    if type(audit["security_opt"]) is not list or any(type(item) is not str for item in audit["security_opt"]):
        raise ValueError("host audit security options invalid")
    _blob(audit["audit_bytes"], "process_audit.audit_bytes")

    approval = _exact(body["oracle_approval"], frozenset({"approved", "statement", "oracle_results_hash"}), "oracle_approval")
    if approval["approved"] is not True:
        raise ValueError("oracle approval must be exact true")
    _text(approval["statement"], "oracle_approval.statement", 4096)
    _hex(approval["oracle_results_hash"], "oracle_approval.oracle_results_hash")


def canonical_body_bytes(body: Mapping[str, Any]) -> bytes:
    validate_body(body)
    return canonical_json_bytes(body)


def body_sha256(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_body_bytes(body)).hexdigest()


def sign_body(body: Mapping[str, Any], private_key: bytes) -> str:
    if type(private_key) is not bytes or len(private_key) != 32:
        raise ValueError("Ed25519 private key must be exactly 32 raw bytes")
    signature = Ed25519PrivateKey.from_private_bytes(private_key).sign(DOMAIN + canonical_body_bytes(body))
    encoded = signature.hex()
    if type(encoded) is not str:
        raise ValueError("Ed25519 implementation returned an invalid signature")
    return encoded


def signature_record(key_id: str, signature: str) -> dict[str, str]:
    _text(key_id, "key_id", 128)
    _hex(signature, "signature", _HEX128)
    return {"key_id": key_id, "algorithm": "Ed25519", "signature": signature}



def create_executor_attestation(body: Mapping[str, Any], key_id: str, private_key: bytes) -> dict[str, Any]:
    """Create the executor-only handoff; it cannot claim approver authority."""
    canonical = canonical_body_bytes(body)
    return {"schema_version": 3, "body": body, "body_sha256": hashlib.sha256(canonical).hexdigest(), "executor_signature": signature_record(key_id, sign_body(body, private_key))}


def approve_executor_attestation(attestation: Mapping[str, Any], executor_key_id: str, executor_public_key: bytes, approver_key_id: str, approver_private_key: bytes) -> dict[str, Any]:
    """Verify the executor handoff, then sign precisely the same body bytes."""
    item = _exact(attestation, frozenset({"schema_version", "body", "body_sha256", "executor_signature"}), "executor attestation")
    if item["schema_version"] != 3 or type(item["schema_version"]) is not int:
        raise ValueError("executor attestation schema mismatch")
    body = item["body"]
    canonical = canonical_body_bytes(body)
    if item["body_sha256"] != hashlib.sha256(canonical).hexdigest():
        raise ValueError("executor attestation body hash mismatch")
    signature = _exact(item["executor_signature"], SIGNATURE_KEYS, "executor signature")
    if signature["key_id"] != executor_key_id or signature["algorithm"] != "Ed25519":
        raise ValueError("executor attestation identity mismatch")
    try:
        Ed25519PublicKey.from_public_bytes(executor_public_key).verify(bytes.fromhex(signature["signature"]), DOMAIN + canonical)
    except (InvalidSignature, ValueError) as error:
        raise ValueError("executor attestation signature mismatch") from error
    approver = signature_record(approver_key_id, sign_body(body, approver_private_key))
    return assemble_receipt(body, signature, approver)

def receipt_hash(receipt_without_hash: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(receipt_without_hash)).hexdigest()


def assemble_receipt(body: Mapping[str, Any], executor: Mapping[str, Any], approver: Mapping[str, Any]) -> dict[str, Any]:
    canonical = canonical_body_bytes(body)
    result: dict[str, Any] = {
        "schema_version": 3, "body": body,
        "body_sha256": hashlib.sha256(canonical).hexdigest(),
        "executor_signature": dict(executor), "approver_signature": dict(approver),
    }
    validate_receipt_shape({**result, "receipt_hash": "0" * 64})
    result["receipt_hash"] = receipt_hash(result)
    validate_published_schema(result)
    return result


@lru_cache(maxsize=1)
def _published_schema() -> tuple[Mapping[str, Any], Any]:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    directory = Path(__file__).parents[2] / "rfcs/schemas"
    names = (
        "no1-008a-cell-receipt-v3.schema.json",
        "no1-008a-cell-receipt-v3-body.schema.json",
        "no1-008a-cell-receipt-v3-common.schema.json",
        "no1-008a-cell-receipt-v3-fields-a.schema.json",
        "no1-008a-cell-receipt-v3-fields-b.schema.json",
    )
    documents = [strict_json_loads((directory / name).read_bytes()) for name in names]
    for document in documents:
        Draft202012Validator.check_schema(document)
    registry = Registry().with_resources(
        (document["$id"], Resource.from_contents(document)) for document in documents
    )
    return documents[0], registry


def validate_published_schema(receipt: Any) -> None:
    from jsonschema import Draft202012Validator
    schema, registry = _published_schema()
    errors = sorted(Draft202012Validator(schema, registry=registry).iter_errors(receipt), key=lambda error: list(error.path))
    if errors:
        raise ValueError(f"published receipt schema mismatch: {errors[0].message}")


def validate_receipt_shape(receipt: Any) -> None:
    item = _exact(receipt, TOP_KEYS, "receipt")
    if item["schema_version"] != 3 or type(item["schema_version"]) is not int:
        raise ValueError("receipt schema_version must be exact integer 3")
    validate_body(item["body"])
    _hex(item["body_sha256"], "body_sha256")
    _hex(item["receipt_hash"], "receipt_hash")
    for role in ("executor_signature", "approver_signature"):
        signature = _exact(item[role], SIGNATURE_KEYS, role)
        _text(signature["key_id"], f"{role}.key_id", 128)
        if signature["algorithm"] != "Ed25519":
            raise ValueError("signature algorithm must be Ed25519")
        _hex(signature["signature"], f"{role}.signature", _HEX128)
    if item["executor_signature"]["key_id"] == item["approver_signature"]["key_id"]:
        raise ValueError("signer key IDs must differ")


def verify_receipt(receipt: Mapping[str, Any], executor_key_id: str, executor_public_key: bytes, approver_key_id: str, approver_public_key: bytes) -> None:
    validate_receipt_shape(receipt)
    validate_published_schema(receipt)
    if type(executor_public_key) is not bytes or type(approver_public_key) is not bytes or len(executor_public_key) != 32 or len(approver_public_key) != 32:
        raise ValueError("public keys must be exactly 32 raw bytes")
    if executor_public_key == approver_public_key or executor_key_id == approver_key_id:
        raise ValueError("executor and approver identities must differ")
    if receipt["executor_signature"]["key_id"] != executor_key_id or receipt["approver_signature"]["key_id"] != approver_key_id:
        raise ValueError("receipt key identity mismatch")
    canonical = canonical_body_bytes(receipt["body"])
    if receipt["body_sha256"] != hashlib.sha256(canonical).hexdigest():
        raise ValueError("receipt body hash mismatch")
    without_hash = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    if receipt["receipt_hash"] != receipt_hash(without_hash):
        raise ValueError("receipt hash mismatch")
    signed = DOMAIN + canonical
    try:
        Ed25519PublicKey.from_public_bytes(executor_public_key).verify(bytes.fromhex(receipt["executor_signature"]["signature"]), signed)
        Ed25519PublicKey.from_public_bytes(approver_public_key).verify(bytes.fromhex(receipt["approver_signature"]["signature"]), signed)
    except (InvalidSignature, ValueError) as error:
        raise ValueError("detached receipt signature mismatch") from error
# fmt: on
