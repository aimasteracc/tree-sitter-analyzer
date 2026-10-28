"""Fail-closed validation for the NO1-001A Gin qualification bundle."""

from __future__ import annotations

import json
import stat
from dataclasses import fields
from pathlib import Path, PurePosixPath
from typing import Any, cast

from benchmarks.codegraph_compare.gin_smoke import (
    EXPECTED_ARMS,
    FILES,
    FORBIDDEN_NAMES,
    MANIFEST_KEYS,
    OBJECTIVE_ID,
    SCHEMA_VERSION,
    Cell,
    QualificationError,
    _digest_bytes,
    _is_git_sha,
    _is_sha256,
    _policy,
)
from benchmarks.codegraph_compare.integrity import _sha256

#: Manifest fields that must equal one fixed value.
_MANIFEST_CONSTANTS: tuple[tuple[str, Any], ...] = (
    ("schema_version", SCHEMA_VERSION),
    ("objective_id", OBJECTIVE_ID),
    ("mode", "fixture"),
    ("expected_arms", list(EXPECTED_ARMS)),
    ("network", "disabled"),
    ("allowed_native_tools", ["read", "search"]),
    ("retry_policy", {"kind": "none", "selective_reruns": False}),
)
_MANIFEST_SHA256_FIELDS = (
    "question_sha256",
    "config_fingerprint",
    "repository_fingerprint",
)
_MANIFEST_NONEMPTY_STR_FIELDS = ("model", "repository_path")
_CELL_BOOLEAN_KEYS = frozenset({"backend_executed", "index_created", "model_executed"})
_CELL_SHA256_FIELDS = (
    "input_fingerprint",
    "config_fingerprint",
    "tool_policy_fingerprint",
)
_NAMESPACE_KEYS = (
    "checkout_namespace",
    "mcp_namespace",
    "index_namespace",
    "artifact_namespace",
)
_EXPECTED_QUALIFICATION = {
    "schema_version": 1,
    "objective_id": OBJECTIVE_ID,
    "evidence_level": "E0",
    "publishable": False,
    "qualification_only": True,
    "backend_executed": False,
    "index_created": False,
    "model_executed": False,
    "dominance_allowed": False,
    "winner": None,
}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QualificationError(f"invalid JSON: {path.name}") from exc


def _read_object(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if not isinstance(payload, dict) or any(
        not isinstance(key, str) for key in payload
    ):
        raise QualificationError(f"JSON object required: {path.name}")
    return cast(dict[str, Any], payload)


def _reject_forbidden_keys(payload: Any) -> None:
    if isinstance(payload, dict):
        if any(str(key).casefold() in FORBIDDEN_NAMES for key in payload):
            raise QualificationError("oracle material is forbidden")
        children = list(payload.values())
    elif isinstance(payload, (list, tuple)):
        children = list(payload)
    else:
        return
    for value in children:
        _reject_forbidden_keys(value)


def _regular_files(root: Path) -> tuple[str, ...]:
    names: list[str] = []
    for path in root.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or (not stat.S_ISREG(mode) and not stat.S_ISDIR(mode)):
            raise QualificationError(f"special filesystem node: {path}")
        if path.is_file():
            names.append(path.relative_to(root).as_posix())
    return tuple(sorted(names))


def _validate_names(names: tuple[str, ...]) -> None:
    expected = tuple(sorted((*FILES, "checksums.json")))
    if names != expected:
        raise QualificationError("missing, duplicate, or unexpected bundle files")
    for name in names:
        parts = {part.casefold() for part in PurePosixPath(name).parts}
        if parts & FORBIDDEN_NAMES:
            raise QualificationError("oracle material is forbidden")


def validate_bundle(
    root: Path, *, expected_git_sha: str, expected_bundle_digest: str
) -> dict[str, Any]:
    """Validate a bundle against external trusted Git and digest anchors."""
    if (
        not root.is_dir()
        or not expected_git_sha
        or not _is_sha256(expected_bundle_digest)
    ):
        raise QualificationError("bundle directory and external anchors are required")
    names = _regular_files(root)
    _validate_names(names)
    manifest = _read_object(root / "manifest.json")
    qualification = _read_object(root / "qualification.json")
    checksum_doc = _read_object(root / "checksums.json")
    if _digest_bytes((root / "checksums.json").read_bytes()) != expected_bundle_digest:
        raise QualificationError("external bundle digest mismatch")
    _reject_forbidden_keys((manifest, qualification, checksum_doc))
    _validate_manifest(manifest, expected_git_sha)
    _validate_checksums(root, checksum_doc)

    cells = [_read_object(root / "cells" / f"{arm}.json") for arm in EXPECTED_ARMS]
    policies = [
        _read_object(root / "policies" / f"{arm}.json") for arm in EXPECTED_ARMS
    ]
    _reject_forbidden_keys((cells, policies))
    for arm, cell, policy in zip(EXPECTED_ARMS, cells, policies, strict=True):
        _validate_cell(root, arm, cell, policy, manifest)
    namespaces = [cell[key] for cell in cells for key in _NAMESPACE_KEYS]
    if len(namespaces) != len(set(namespaces)):
        raise QualificationError("namespace collision")
    if qualification != _EXPECTED_QUALIFICATION:
        raise QualificationError("qualification claim exceeds E0")
    return qualification


def _validate_manifest(manifest: dict[str, Any], expected_git_sha: str) -> None:
    """Check the Git anchor, the manifest contract and its config fingerprint."""
    if manifest.get("benchmark_git_sha") != expected_git_sha or not _is_git_sha(
        expected_git_sha
    ):
        raise QualificationError("wrong benchmark Git SHA")
    if not _manifest_contract_holds(manifest):
        raise QualificationError("invalid manifest contract")
    shared = {
        "question_sha256": manifest.get("question_sha256"),
        "model": manifest.get("model"),
        "timeout_seconds": manifest.get("timeout_seconds"),
        "network": manifest.get("network"),
        "allowed_native_tools": manifest.get("allowed_native_tools"),
    }
    if manifest.get("config_fingerprint") != _sha256(shared):
        raise QualificationError("config fingerprint mismatch")


def _manifest_contract_holds(manifest: dict[str, Any]) -> bool:
    """Return whether the manifest has exactly the fixture-mode contract."""
    if set(manifest) != MANIFEST_KEYS:
        return False
    timeout = manifest.get("timeout_seconds")
    return (
        all(manifest.get(key) == value for key, value in _MANIFEST_CONSTANTS)
        and all(_is_sha256(manifest.get(key)) for key in _MANIFEST_SHA256_FIELDS)
        and all(
            isinstance(manifest.get(key), str) and bool(manifest[key])
            for key in _MANIFEST_NONEMPTY_STR_FIELDS
        )
        and type(timeout) is int
        and timeout > 0
        and _is_git_sha(manifest.get("repository_commit"))
        and manifest.get("oracle_material_in_bundle") is False
    )


def _validate_checksums(root: Path, checksum_doc: dict[str, Any]) -> None:
    """Check the checksum inventory shape and every listed file digest."""
    expected_checksums = checksum_doc.get("sha256")
    if (
        set(checksum_doc) != {"sha256"}
        or not isinstance(expected_checksums, dict)
        or set(expected_checksums) != set(FILES)
        or any(not _is_sha256(value) for value in expected_checksums.values())
    ):
        raise QualificationError("invalid checksum inventory")
    actual = {name: _digest_bytes((root / name).read_bytes()) for name in FILES}
    if actual != expected_checksums:
        raise QualificationError("checksum mismatch")


def _cell_shape_holds(arm: str, cell: dict[str, Any], policy: Any) -> bool:
    """Return whether one cell has its arm's exact shape and namespaces."""
    cell_keys = {field.name for field in fields(Cell)}
    if set(cell) != cell_keys or any(
        not isinstance(cell[key], str) for key in cell_keys - _CELL_BOOLEAN_KEYS
    ):
        return False
    slug = arm.replace("-", "_")
    expected_values = {
        "arm": arm,
        "checkout_namespace": f"checkout/{slug}",
        "mcp_namespace": f"mcp/{slug}",
        "index_namespace": f"index/{slug}",
        "artifact_namespace": f"artifact/{slug}",
    }
    return (
        all(cell.get(key) == value for key, value in expected_values.items())
        and all(_is_sha256(cell.get(key)) for key in _CELL_SHA256_FIELDS)
        and policy == _policy(arm)
    )


def _validate_cell(
    root: Path,
    arm: str,
    cell: dict[str, Any],
    policy: Any,
    manifest: dict[str, Any],
) -> None:
    """Validate one arm's cell, its provenance bindings and its transcript."""
    if not _cell_shape_holds(arm, cell, policy):
        raise QualificationError("mixed or invalid cell")
    if cell.get("repository_path") != manifest.get("repository_path"):
        raise QualificationError("wrong repository")
    if cell.get("repository_commit") != manifest.get("repository_commit") or cell.get(
        "repository_fingerprint"
    ) != manifest.get("repository_fingerprint"):
        raise QualificationError("wrong repository provenance")
    expected_input = _sha256(
        {
            "question_sha256": manifest.get("question_sha256"),
            "repository_commit": manifest.get("repository_commit"),
            "repository_fingerprint": manifest.get("repository_fingerprint"),
        }
    )
    if cell.get("input_fingerprint") != expected_input:
        raise QualificationError("input fingerprint mismatch")
    if cell.get("config_fingerprint") != manifest.get("config_fingerprint"):
        raise QualificationError("config fingerprint mismatch")
    if cell.get("tool_policy_fingerprint") != _sha256(policy):
        raise QualificationError("tool policy fingerprint mismatch")
    if any(cell.get(flag) is not False for flag in _CELL_BOOLEAN_KEYS):
        raise QualificationError("qualification executed forbidden work")
    transcript = _read_object(root / "transcripts" / f"{arm}.jsonl")
    _reject_forbidden_keys(transcript)
    if transcript != {
        "arm": arm,
        "event": "qualification_only",
        "backend_executed": False,
        "index_created": False,
        "model_executed": False,
    }:
        raise QualificationError("invalid qualification transcript")
