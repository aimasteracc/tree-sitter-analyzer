"""Deterministic, model-free qualification bundle for NO1-001A.

This adapter deliberately produces E0 infrastructure evidence only.  It
reuses the benchmark's canonical hashing vocabulary while keeping model,
backend, and index execution outside the qualification boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path, PurePosixPath
from typing import Any, cast

from benchmarks.codegraph_compare.integrity import _sha256

OBJECTIVE_ID = "NO1-001A"
SCHEMA_VERSION = 1
EXPECTED_ARMS = ("native", "tree-sitter-analyzer", "codegraph")
FORBIDDEN_NAMES = frozenset({"oracle", "oracles", "expected_answer", "answers"})
FILES = (
    "manifest.json",
    "qualification.json",
    "cells/native.json",
    "cells/tree-sitter-analyzer.json",
    "cells/codegraph.json",
    "policies/native.json",
    "policies/tree-sitter-analyzer.json",
    "policies/codegraph.json",
    "transcripts/native.jsonl",
    "transcripts/tree-sitter-analyzer.jsonl",
    "transcripts/codegraph.jsonl",
)


class QualificationError(ValueError):
    """A bundle is not valid qualification evidence."""


@dataclass(frozen=True)
class Cell:
    arm: str
    repository_path: str
    checkout_namespace: str
    mcp_namespace: str
    index_namespace: str
    artifact_namespace: str
    config_fingerprint: str
    input_fingerprint: str
    tool_policy_fingerprint: str
    backend_executed: bool = False
    index_created: bool = False
    model_executed: bool = False


def _canonical(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(payload) + b"\n")


def _policy(arm: str) -> dict[str, Any]:
    allowed = {
        "native": ["read", "search"],
        "tree-sitter-analyzer": ["read", "search", "tree-sitter-analyzer"],
        "codegraph": ["read", "search", "codegraph"],
    }[arm]
    forbidden = sorted({"tree-sitter-analyzer", "codegraph"} - set(allowed))
    return {
        "arm": arm,
        "allowed_native_tools": ["read", "search"],
        "allowed_tools": allowed,
        "forbidden_tools": forbidden,
        "network": "disabled",
        "oracle_access": False,
        "retry_policy": "none",
    }


def _cell(
    arm: str,
    *,
    repository_path: str,
    input_fingerprint: str,
    config_fingerprint: str,
) -> Cell:
    policy_hash = _sha256(_policy(arm))
    slug = arm.replace("-", "_")
    return Cell(
        arm=arm,
        repository_path=repository_path,
        checkout_namespace=f"checkout/{slug}",
        mcp_namespace=f"mcp/{slug}",
        index_namespace=f"index/{slug}",
        artifact_namespace=f"artifact/{slug}",
        config_fingerprint=config_fingerprint,
        input_fingerprint=input_fingerprint,
        tool_policy_fingerprint=policy_hash,
    )


def create_bundle(
    destination: Path,
    *,
    benchmark_git_sha: str,
    repository_path: str,
    question: str,
    model: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Create an immutable fixture bundle without executing a backend or model."""
    if destination.exists():
        raise QualificationError("destination already exists")
    if not benchmark_git_sha or not repository_path or not question or not model:
        raise QualificationError("identity fields must be non-empty")
    if timeout_seconds <= 0:
        raise QualificationError("timeout_seconds must be positive")

    destination.mkdir(parents=True)
    input_fingerprint = _digest_bytes(question.encode())
    shared = {
        "question_sha256": input_fingerprint,
        "model": model,
        "timeout_seconds": timeout_seconds,
        "network": "disabled",
        "allowed_native_tools": ["read", "search"],
    }
    config_fingerprint = _sha256(shared)
    cells = tuple(
        _cell(
            arm,
            repository_path=repository_path,
            input_fingerprint=input_fingerprint,
            config_fingerprint=config_fingerprint,
        )
        for arm in EXPECTED_ARMS
    )
    namespaces = [
        value
        for cell in cells
        for value in (
            cell.checkout_namespace,
            cell.mcp_namespace,
            cell.index_namespace,
            cell.artifact_namespace,
        )
    ]
    if len(namespaces) != len(set(namespaces)):
        raise QualificationError("namespace collision")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "objective_id": OBJECTIVE_ID,
        "mode": "fixture",
        "benchmark_git_sha": benchmark_git_sha,
        "repository_path": repository_path,
        "question_sha256": input_fingerprint,
        "config_fingerprint": config_fingerprint,
        "expected_arms": list(EXPECTED_ARMS),
        "retry_policy": {"kind": "none", "selective_reruns": False},
        "oracle_material_in_bundle": False,
        **shared,
    }
    _write(destination / "manifest.json", manifest)
    for cell in cells:
        _write(destination / "cells" / f"{cell.arm}.json", asdict(cell))
        _write(destination / "policies" / f"{cell.arm}.json", _policy(cell.arm))
        _write(
            destination / "transcripts" / f"{cell.arm}.jsonl",
            {
                "arm": cell.arm,
                "event": "qualification_only",
                "backend_executed": False,
                "index_created": False,
                "model_executed": False,
            },
        )
    qualification = {
        "schema_version": SCHEMA_VERSION,
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
    _write(destination / "qualification.json", qualification)
    checksums = {
        name: _digest_bytes((destination / name).read_bytes()) for name in FILES
    }
    _write(destination / "checksums.json", {"sha256": checksums})
    bundle_digest = _digest_bytes((destination / "checksums.json").read_bytes())
    validate_bundle(
        destination,
        expected_git_sha=benchmark_git_sha,
        expected_bundle_digest=bundle_digest,
    )
    if not isinstance(qualification, dict):
        raise QualificationError("qualification must be an object")
    return {**cast(dict[str, Any], qualification), "bundle_digest": bundle_digest}


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
    """Validate a bundle against an external, trusted Git SHA anchor."""
    if not root.is_dir() or not expected_git_sha or not expected_bundle_digest:
        raise QualificationError("bundle directory and external anchors are required")
    names = _regular_files(root)
    _validate_names(names)
    manifest = _read_object(root / "manifest.json")
    qualification = _read_object(root / "qualification.json")
    checksum_doc = _read_object(root / "checksums.json")
    if _digest_bytes((root / "checksums.json").read_bytes()) != expected_bundle_digest:
        raise QualificationError("external bundle digest mismatch")
    _reject_forbidden_keys((manifest, qualification, checksum_doc))
    if manifest.get("benchmark_git_sha") != expected_git_sha:
        raise QualificationError("wrong benchmark Git SHA")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("objective_id") != OBJECTIVE_ID
        or manifest.get("mode") != "fixture"
        or tuple(manifest.get("expected_arms", ())) != EXPECTED_ARMS
        or manifest.get("network") != "disabled"
        or manifest.get("allowed_native_tools") != ["read", "search"]
        or type(manifest.get("timeout_seconds")) is not int
        or manifest["timeout_seconds"] <= 0
        or not isinstance(manifest.get("model"), str)
        or not manifest["model"]
        or not isinstance(manifest.get("repository_path"), str)
        or not manifest["repository_path"]
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
    if not isinstance(expected_checksums, dict) or set(expected_checksums) != set(FILES):
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
        if (
            set(cell) != cell_keys
            or any(not isinstance(cell[key], str) for key in cell_keys - {
                "backend_executed",
                "index_created",
                "model_executed",
            })
            or cell.get("arm") != arm
            or policy != _policy(arm)
        ):
            raise QualificationError("mixed or invalid cell")
        if cell.get("repository_path") != manifest.get("repository_path"):
            raise QualificationError("wrong repository")
        if cell.get("input_fingerprint") != manifest.get("question_sha256"):
            raise QualificationError("input fingerprint mismatch")
        if cell.get("config_fingerprint") != manifest.get("config_fingerprint"):
            raise QualificationError("config fingerprint mismatch")
        if cell.get("tool_policy_fingerprint") != _sha256(policy):
            raise QualificationError("tool policy fingerprint mismatch")
        if any(
            cell.get(flag) is not False
            for flag in ("backend_executed", "index_created", "model_executed")
        ):
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


def replay_bundle(
    source: Path,
    destination: Path,
    *,
    expected_git_sha: str,
    expected_bundle_digest: str,
) -> None:
    """Replay the deterministic bundle atomically and verify byte identity."""
    validate_bundle(
        source,
        expected_git_sha=expected_git_sha,
        expected_bundle_digest=expected_bundle_digest,
    )
    if destination.exists():
        raise QualificationError("replay destination already exists")
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as temp_name:
        temp = Path(temp_name)
        for name in (*FILES, "checksums.json"):
            target = temp / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source / name).read_bytes())
        validate_bundle(
            temp,
            expected_git_sha=expected_git_sha,
            expected_bundle_digest=expected_bundle_digest,
        )
        os.replace(temp, destination)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("destination", type=Path)
    create.add_argument("--benchmark-git-sha", required=True)
    create.add_argument("--repository-path", required=True)
    create.add_argument("--question", required=True)
    create.add_argument("--model", required=True)
    create.add_argument("--timeout-seconds", type=int, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("bundle", type=Path)
    validate.add_argument("--expected-git-sha", required=True)
    validate.add_argument("--expected-bundle-digest", required=True)
    replay = sub.add_parser("replay")
    replay.add_argument("source", type=Path)
    replay.add_argument("destination", type=Path)
    replay.add_argument("--expected-git-sha", required=True)
    replay.add_argument("--expected-bundle-digest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            result = create_bundle(
                args.destination,
                benchmark_git_sha=args.benchmark_git_sha,
                repository_path=args.repository_path,
                question=args.question,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.command == "validate":
            result = validate_bundle(
                args.bundle,
                expected_git_sha=args.expected_git_sha,
                expected_bundle_digest=args.expected_bundle_digest,
            )
        else:
            replay_bundle(
                args.source,
                args.destination,
                expected_git_sha=args.expected_git_sha,
                expected_bundle_digest=args.expected_bundle_digest,
            )
            result = {"replayed": True, "destination": str(args.destination)}
    except QualificationError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 2
    print(json.dumps({"valid": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
