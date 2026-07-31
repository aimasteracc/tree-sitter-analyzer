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
        for key, value in payload.items():
            if str(key).casefold() in FORBIDDEN_NAMES:
                raise QualificationError("oracle material is forbidden")
            _reject_forbidden_keys(value)
    elif isinstance(payload, (list, tuple)):
        for value in payload:
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
    if (
        manifest.get("benchmark_git_sha") != expected_git_sha
        or not _is_git_sha(expected_git_sha)
    ):
        raise QualificationError("wrong benchmark Git SHA")
    if (
        set(manifest) != MANIFEST_KEYS
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("objective_id") != OBJECTIVE_ID
        or manifest.get("mode") != "fixture"
        or manifest.get("expected_arms") != list(EXPECTED_ARMS)
        or manifest.get("network") != "disabled"
        or manifest.get("allowed_native_tools") != ["read", "search"]
        or not _is_sha256(manifest.get("question_sha256"))
        or not _is_sha256(manifest.get("config_fingerprint"))
        or type(manifest.get("timeout_seconds")) is not int
        or manifest["timeout_seconds"] <= 0
        or not isinstance(manifest.get("model"), str)
        or not manifest["model"]
        or not isinstance(manifest.get("repository_path"), str)
        or not manifest["repository_path"]
        or not _is_git_sha(manifest.get("repository_commit"))
        or not _is_sha256(manifest.get("repository_fingerprint"))
        or manifest.get("oracle_material_in_bundle") is not False
        or manifest.get("retry_policy")
        != {"kind": "none", "selective_reruns": False}
    ):
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

    cells = [
        _read_object(root / "cells" / f"{arm}.json") for arm in EXPECTED_ARMS
    ]
    policies = [
        _read_object(root / "policies" / f"{arm}.json") for arm in EXPECTED_ARMS
    ]
    _reject_forbidden_keys((cells, policies))
    cell_keys = {field.name for field in fields(Cell)}
    for arm, cell, policy in zip(EXPECTED_ARMS, cells, policies, strict=True):
        slug = arm.replace("-", "_")
        boolean_keys = {"backend_executed", "index_created", "model_executed"}
        if (
            set(cell) != cell_keys
            or any(
                not isinstance(cell[key], str) for key in cell_keys - boolean_keys
            )
            or cell.get("arm") != arm
            or cell.get("checkout_namespace") != f"checkout/{slug}"
            or cell.get("mcp_namespace") != f"mcp/{slug}"
            or cell.get("index_namespace") != f"index/{slug}"
            or cell.get("artifact_namespace") != f"artifact/{slug}"
            or not _is_sha256(cell.get("input_fingerprint"))
            or not _is_sha256(cell.get("config_fingerprint"))
            or not _is_sha256(cell.get("tool_policy_fingerprint"))
            or policy != _policy(arm)
        ):
            raise QualificationError("mixed or invalid cell")
        if cell.get("repository_path") != manifest.get("repository_path"):
            raise QualificationError("wrong repository")
        if (
            cell.get("repository_commit") != manifest.get("repository_commit")
            or cell.get("repository_fingerprint")
            != manifest.get("repository_fingerprint")
        ):
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
        if any(cell.get(flag) is not False for flag in boolean_keys):
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
    namespaces = [
        cell[key]
        for cell in cells
        for key in (
            "checkout_namespace",
            "mcp_namespace",
            "index_namespace",
            "artifact_namespace",
        )
    ]
    if len(namespaces) != len(set(namespaces)):
        raise QualificationError("namespace collision")
    expected_qualification = {
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
    if qualification != expected_qualification:
        raise QualificationError("qualification claim exceeds E0")
    return qualification
