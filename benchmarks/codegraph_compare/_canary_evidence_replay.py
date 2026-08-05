"""Semantic replay helpers for NO1-002C evidence artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

_TOOLS = {"tsa-warm": "nav", "codegraph-warm": "codegraph_search"}
_ORACLE = {
    "expected_path": "gin.go",
    "expected_symbol": "Engine.ServeHTTP",
    "expected_kind": "method",
}
_WORKSPACE_KEYS = {
    "schema_version",
    "manifest_hash",
    "session_id",
    "run_id",
    "cell_id",
    "arm",
    "audit_sha256",
    "audit",
}
_AUDIT_KEYS = {
    "checkout_root",
    "head_commit",
    "tracked_paths",
    "repository_fingerprint",
    "source_before",
    "source_after",
    "runtime_namespace",
    "runtime_before",
    "runtime_after",
}


def read_if_file(path: Path | None) -> bytes | None:
    try:
        return path.read_bytes() if path is not None and path.is_file() else None
    except OSError:
        return None


def workspace_envelope(
    manifest_hash: str,
    session_id: str,
    run_id: str,
    cell: Any,
    audit_hash: str,
    audit: Any,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_hash": manifest_hash,
        "session_id": session_id,
        "run_id": run_id,
        "cell_id": cell.cell_id,
        "arm": cell.arm,
        "audit_sha256": audit_hash,
        "audit": audit,
    }


def _json_object(payload: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if type(value) is dict else None


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _valid_inventory(value: Any) -> bool:
    return type(value) is list and all(
        type(item) is list
        and len(item) == 2
        and type(item[0]) is str
        and bool(item[0])
        and type(item[1]) is str
        and len(item[1]) == 64
        for item in value
    )


def _workspace_audit_valid(audit: Any, arm: str) -> bool:
    if type(audit) is not dict or set(audit) != _AUDIT_KEYS:
        return False
    namespace = ".ast-cache" if arm == "tsa-warm" else ".codegraph"
    return (
        type(audit["checkout_root"]) is str
        and Path(audit["checkout_root"]).is_absolute()
        and type(audit["head_commit"]) is str
        and bool(audit["head_commit"])
        and type(audit["tracked_paths"]) is list
        and all(type(path) is str and path for path in audit["tracked_paths"])
        and type(audit["repository_fingerprint"]) is str
        and len(audit["repository_fingerprint"]) == 64
        and _valid_inventory(audit["source_before"])
        and audit["source_after"] == audit["source_before"]
        and audit["runtime_namespace"] == namespace
        and _valid_inventory(audit["runtime_before"])
        and _valid_inventory(audit["runtime_after"])
    )


def replay_artifact_semantics(
    attempt: Any, payloads: dict[str, tuple[Path, bytes]]
) -> bool:
    """Replay receipt/source-order semantics and exact workspace bindings."""

    receipt = _json_object(payloads["receipt"][1])
    if receipt != {"call_id": attempt.receipt_call_id}:
        return False
    transcript_path = payloads["transcript"][0]
    try:
        audit = audit_canary_transcript(
            transcript_path,
            attempt.arm,
            expected_tool=_TOOLS[attempt.arm],
            **_ORACLE,
        )
    except (KeyError, OSError, TypeError, ValueError):
        return False
    if (
        audit.violations
        or audit.receipt is None
        or audit.receipt.call_id != attempt.receipt_call_id
    ):
        return False
    workspace = _json_object(payloads["workspace_audit"][1])
    expected_workspace = {
        "schema_version": 1,
        "manifest_hash": attempt.manifest_hash,
        "session_id": attempt.session_id,
        "run_id": attempt.run_id,
        "cell_id": attempt.cell_id,
        "arm": attempt.arm,
        "audit_sha256": attempt.workspace_audit_sha256,
        "audit": workspace.get("audit") if workspace is not None else None,
    }
    if workspace is None or set(workspace) != _WORKSPACE_KEYS:
        return False
    if workspace != expected_workspace:
        return False
    if not _workspace_audit_valid(workspace["audit"], attempt.arm):
        return False
    if _sha256_json(workspace["audit"]) != attempt.workspace_audit_sha256:
        return False
    return payloads["runtime"][1] == attempt.runtime_hash.encode("ascii")


def artifacts_are_bound(
    attempt: Any, artifacts: tuple[Any, ...], expected_hashes: dict[str, str]
) -> bool:
    """Read every artifact and verify its digest, binding, and semantics."""

    payloads: dict[str, tuple[Path, bytes]] = {}
    for item in artifacts:
        try:
            path = Path(item.evidence_path)
            payload = path.read_bytes()
        except (OSError, TypeError, ValueError):
            return False
        expected = (
            hashlib.sha256(
                json.dumps(
                    {"call_id": attempt.receipt_call_id},
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            if item.kind == "receipt"
            else expected_hashes[item.kind]
        )
        if item.kind == "runtime":
            content_bound = payload == attempt.runtime_hash.encode("ascii")
        elif item.kind == "workspace_audit":
            content_bound = True
        else:
            content_bound = item.sha256 == expected
        receipt_bound = (
            item.receipt_call_id == attempt.receipt_call_id
            if item.kind == "receipt"
            else item.receipt_call_id is None
        )
        if not (
            path.is_absolute()
            and hashlib.sha256(payload).hexdigest() == item.sha256
            and type(item.schema_version) is int
            and item.schema_version == 1
            and item.manifest_hash == attempt.manifest_hash
            and item.session_id == attempt.session_id
            and content_bound
            and receipt_bound
        ):
            return False
        payloads[item.kind] = (path, payload)
    return replay_artifact_semantics(attempt, payloads)
