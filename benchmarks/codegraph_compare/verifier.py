"""Fresh recomputing verifier for detached NO1-008A receipt v3."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
    verify_receipt,
)
from benchmarks.codegraph_compare.setup_qualification_paths import (
    _hash_tree,
    _open_beneath,
    _open_root,
    canonical_relative_path,
)
from benchmarks.codegraph_compare.setup_qualification_plan import (
    ZERO_COUNTERS,
)

CLAIMS = {
    "evaluation_stage": "E0",
    "publishable": False,
    "winner": None,
    "dominance_allowed": False,
    "unlock_allowed": False,
}
PUBLIC_CONFIG_KEYS = frozenset({"schema_version", "executor", "approver"})
PUBLIC_ROLE_KEYS = frozenset({"key_id", "public_key_hex"})
MANIFEST_KEYS = frozenset(
    {"schema_version", "verifier_nonce", "verifier_image_digest", "cells"}
)
CELL_KEYS = frozenset(
    {
        "repo_id",
        "arm_id",
        "attempt",
        "plan",
        "inventory",
        "receipt",
        "data_image",
        "hash_image",
        "process_audit",
    }
)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]]
Extractor = Callable[[Path, Path], None]


def _exact(value: Any, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or frozenset(value) != keys:
        raise ValueError(f"{label} has unknown or missing fields")
    return value


def parse_public_config(payload: bytes) -> dict[str, Any]:
    config = _exact(strict_json_loads(payload), PUBLIC_CONFIG_KEYS, "public config")
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ValueError("public config schema must be exact integer 1")
    keys: list[bytes] = []
    ids: list[str] = []
    for role in ("executor", "approver"):
        item = _exact(config[role], PUBLIC_ROLE_KEYS, role)
        if (
            type(item["key_id"]) is not str
            or not item["key_id"]
            or len(item["key_id"].encode()) > 128
        ):
            raise ValueError("public key ID must be bounded and non-empty")
        encoded = item["public_key_hex"]
        if type(encoded) is not str or _HEX64.fullmatch(encoded) is None:
            raise ValueError("public key must contain 32 lowercase hexadecimal bytes")
        keys.append(bytes.fromhex(encoded))
        ids.append(item["key_id"])
    if ids[0] == ids[1] or keys[0] == keys[1]:
        raise ValueError("public signer identities must differ")
    return dict(config)


def _safe_path(raw: Any, label: str) -> Path:
    if (
        type(raw) is not str
        or not raw
        or "," in raw
        or any(ord(c) < 32 or ord(c) == 127 for c in raw)
    ):
        raise ValueError(f"{label} contains a comma or control character")
    path = Path(raw)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError(f"{label} must be canonical, absolute, and existing")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        if stat.S_ISLNK(os.lstat(current).st_mode):
            raise ValueError(f"{label} parent components must not be symbolic links")
    return path


def _sha_file(path: Path) -> tuple[int, str]:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    )
    digest = hashlib.sha256()
    size = 0
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("evidence image is not regular")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return size, digest.hexdigest()


def _read_core(root: Path, relative: str, expected_size: int) -> bytes:
    relative = canonical_relative_path(relative)
    if (
        expected_size > 512 * 1024 * 1024
        or type(expected_size) is not int
        or expected_size < 0
    ):
        raise ValueError("core blob size is invalid")
    root_fd = _open_root(root)
    try:
        descriptor = _open_beneath(root_fd, relative)
        try:
            metadata = os.fstat(descriptor)
            if metadata.st_size != expected_size:
                raise ValueError("core blob size mismatch")
            chunks = bytearray()
            while len(chunks) < expected_size:
                chunk = os.read(
                    descriptor, min(1024 * 1024, expected_size - len(chunks))
                )
                if not chunk:
                    break
                chunks.extend(chunk)
            if len(chunks) != expected_size or os.read(descriptor, 1):
                raise ValueError("core blob changed")
            return bytes(chunks)
        finally:
            os.close(descriptor)
    finally:
        os.close(root_fd)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _plan_value(plan: Mapping[str, Any], name: str, fallback: Any = None) -> Any:
    return plan[name] if name in plan else fallback


def _plan_executions(plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    executions = plan.get("executions")
    if type(executions) is not list or len(executions) != 5:
        raise ValueError("trusted plan executions must be exact count five")
    return [_mapping(item, "plan execution") for item in executions]


def _run_verity(command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(command),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=120,
    )


def _extract_ext4(data_image: Path, destination: Path) -> None:
    # debugfs opens the image read-only by default; destination is a fresh 0700 directory.
    result = subprocess.run(
        ["debugfs", "-R", f"rdump / {destination}", str(data_image)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise ValueError("read-only ext4 extraction failed")


def _hash_list(paths: list[str]) -> str:
    return hashlib.sha256(canonical_json_bytes(paths)).hexdigest()


def _verify_verity(
    body: Mapping[str, Any], evidence: Mapping[str, Any], runner: Runner
) -> None:
    snapshot = body["snapshot"]
    data = _safe_path(evidence["data_image"], "data image")
    hashes = _safe_path(evidence["hash_image"], "hash image")
    data_size, data_sha = _sha_file(data)
    hash_size, hash_sha = _sha_file(hashes)
    if (data_size, data_sha, hash_size, hash_sha) != (
        snapshot["data_image_size"],
        snapshot["data_image_sha256"],
        snapshot["hash_image_size"],
        snapshot["hash_image_sha256"],
    ):
        raise ValueError("image digest or size mismatch")
    result = runner(
        [
            "veritysetup",
            "verify",
            str(data),
            str(hashes),
            snapshot["root_hash"],
            "--hash",
            "sha256",
            "--salt",
            snapshot["salt"],
            "--data-block-size",
            str(snapshot["data_block_size"]),
            "--hash-block-size",
            str(snapshot["hash_block_size"]),
        ]
    )
    if result.returncode != 0:
        raise ValueError("veritysetup verification failed")


def _verify_external_audit(
    body: Mapping[str, Any], evidence: Mapping[str, Any]
) -> Mapping[str, Any]:
    audit_path = _safe_path(evidence["process_audit"], "terminal process audit")
    payload = audit_path.read_bytes()
    blob = body["process_audit"]["audit_bytes"]
    if (
        blob["path"] != "terminal/process-audit.json"
        or len(payload) != blob["size_bytes"]
        or hashlib.sha256(payload).hexdigest() != blob["sha256"]
    ):
        raise ValueError("terminal process audit bytes mismatch")
    audit = strict_json_loads(payload)
    expected = {
        key: value
        for key, value in body["process_audit"].items()
        if key != "audit_bytes"
    }
    if audit != expected:
        raise ValueError("terminal process audit facts mismatch")
    if audit["descendants_after_stop"] != 0 or audit["one_start"] is not True:
        raise ValueError("producer did not terminate exactly once")
    return audit


def _verify_recomputed(
    body: Mapping[str, Any],
    plan: Mapping[str, Any],
    inventory: Mapping[str, Any],
    core: Path,
) -> None:
    cell = body["cell"]
    if (cell["repo_id"], cell["arm_id"], cell["attempt"]) != (
        plan.get("repo_id"),
        plan.get("arm_id"),
        plan.get("attempt"),
    ):
        raise ValueError("plan identity mismatch")
    eligibility = inventory.get("eligibility", inventory)
    if (
        body["source"]["eligibility"] != eligibility
        or body["source"]["commit"] != eligibility.get("commit")
        or body["source"]["repo_fingerprint"] != eligibility.get("repo_fingerprint")
    ):
        raise ValueError("inventory mismatch")
    expected_plan = {
        key: plan[key]
        for key in (
            "plan_hash",
            "plan_set_hash",
            "tool_sha256",
            "config_sha256",
            "image_digest",
            "seccomp_sha256",
        )
    }
    if body["plan"] != expected_plan:
        raise ValueError("trusted plan hashes mismatch")
    environment = body["environment"]
    if (
        environment["image_digest"] != plan["image_digest"]
        or environment["seccomp_sha256"] != plan["seccomp_sha256"]
        or environment["network_mode"] != "none"
    ):
        raise ValueError("trusted environment mismatch")
    expected_exec = _plan_executions(plan)
    observed = body["executions"]
    expected_tuples = [
        (
            item.get("id", item.get("execution_id")),
            item["argv"],
            item["cwd"],
            item["environment_digest"],
        )
        for item in expected_exec
    ]
    observed_tuples = [
        (item["id"], item["argv"], item["cwd"], item["environment_digest"])
        for item in observed
    ]
    if observed_tuples != expected_tuples or any(
        item["exit_code"] != 0 for item in observed
    ):
        raise ValueError("execution count, order, command, or result mismatch")
    producer_result = strict_json_loads(
        _read_core(
            core, "producer-result.json", (core / "producer-result.json").stat().st_size
        )
    )
    result_executions = [
        {
            key: item[key]
            for key in (
                "id",
                "argv",
                "cwd",
                "environment_digest",
                "exit_code",
                "stdout_bytes",
                "stderr_bytes",
                "query_bytes",
                "index_bytes",
            )
        }
        for item in producer_result.get("executions", [])
        if type(item) is dict
    ]
    if result_executions != observed or producer_result.get("counters") != dict(
        ZERO_COUNTERS
    ):
        raise ValueError("producer result mismatch")
    for item, spec in zip(observed, expected_exec, strict=True):
        for field in ("stdout_bytes", "stderr_bytes", "query_bytes", "index_bytes"):
            blob = item[field]
            payload = _read_core(core, blob["path"], blob["size_bytes"])
            if hashlib.sha256(payload).hexdigest() != blob["sha256"]:
                raise ValueError("raw bytes mismatch")
        query = spec.get("query")
        if query is not None and _read_core(
            core, item["query_bytes"]["path"], item["query_bytes"]["size_bytes"]
        ) != canonical_json_bytes(query):
            raise ValueError("oracle query bytes mismatch")
        if item["id"] not in {"delete", "build", "health"}:
            expected_result = spec.get("expected_result")
            stdout = _read_core(
                core, item["stdout_bytes"]["path"], item["stdout_bytes"]["size_bytes"]
            )
            if expected_result is None or stdout.rstrip(b"\n") != canonical_json_bytes(
                expected_result
            ):
                raise ValueError("oracle result bytes mismatch")
    partition = body["index_partition"]
    names = ("indexed_paths", "excluded_paths", "parse_error_paths")
    for name in names:
        if partition[f"{name}_hash"] != _hash_list(partition[name]):
            raise ValueError("partition hash mismatch")
    union = set().union(*(set(partition[name]) for name in names))
    if union != set(eligibility["eligible_paths"]):
        raise ValueError("partition gap or extra path")
    if _hash_tree(core) != body["snapshot"]["tree_hash"]:
        raise ValueError("sealed core tree mismatch")
    index = core / "index"
    if (
        not index.is_dir()
        or _hash_tree(index) != body["snapshot"]["index_content_hash"]
    ):
        raise ValueError("index content mismatch")
    if body["counters"] != dict(ZERO_COUNTERS):
        raise ValueError("zero counters mismatch")
    resources = plan.get("resources", {})
    digest = (
        resources.get(
            "digest", resources.get("plan_digest", plan.get("resource_plan_digest"))
        )
        if type(resources) is dict
        else None
    )
    if digest is not None and body["resources"]["plan_digest"] != digest:
        raise ValueError("resource plan mismatch")
    oracle_hashes = [item["stdout_bytes"]["sha256"] for item in observed[3:]]
    if (
        body["oracle_approval"]["oracle_results_hash"]
        != hashlib.sha256(canonical_json_bytes(oracle_hashes)).hexdigest()
    ):
        raise ValueError("oracle results hash mismatch")


def verify_cell(
    receipt: Mapping[str, Any],
    *,
    public_config: Mapping[str, Any],
    plan: Mapping[str, Any],
    inventory: Mapping[str, Any],
    evidence: Mapping[str, Any],
    runner: Runner = _run_verity,
    extractor: Extractor = _extract_ext4,
    verifier_nonce: str,
    verifier_image_digest: str,
    process_identity: str,
) -> tuple[str, ...]:
    """Verify every mandatory trust root and recompute evidence; never trust body facts."""
    try:
        config = parse_public_config(canonical_json_bytes(public_config))
        if (
            _HEX64.fullmatch(verifier_nonce) is None
            or _IMAGE.fullmatch(verifier_image_digest) is None
            or not process_identity
        ):
            raise ValueError("fresh verifier binding invalid")
        verify_receipt(
            receipt,
            config["executor"]["key_id"],
            bytes.fromhex(config["executor"]["public_key_hex"]),
            config["approver"]["key_id"],
            bytes.fromhex(config["approver"]["public_key_hex"]),
        )
        body = receipt["body"]
        if (
            process_identity
            in {
                body["process_audit"]["producer_container_id"],
                body["process_audit"]["cgroup_id"],
            }
            or verifier_image_digest == body["process_audit"]["image_digest"]
        ):
            raise ValueError("verifier is not fresh")
        _verify_verity(body, evidence, runner)
        audit = _verify_external_audit(body, evidence)
        if audit["image_digest"] != body["environment"]["image_digest"]:
            raise ValueError("producer image mismatch")
        with tempfile.TemporaryDirectory(prefix="no1-008a-verify-") as temporary:
            extracted = Path(temporary)
            extractor(_safe_path(evidence["data_image"], "data image"), extracted)
            _verify_recomputed(body, plan, inventory, extracted)
        return ()
    except (KeyError, OSError, subprocess.SubprocessError, TypeError, ValueError):
        return ("CELL_EVIDENCE_INVALID",)


# Lazy compatibility wrappers keep one public API without an import cycle.
def aggregate_verdict(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from benchmarks.codegraph_compare.verifier_aggregate import (
        aggregate_verdict as implementation,
    )

    return implementation(*args, **kwargs)


def validate_manifest(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
    from benchmarks.codegraph_compare.verifier_aggregate import (
        validate_manifest as implementation,
    )

    return implementation(*args, **kwargs)


def main(argv: Sequence[str] | None = None) -> int:
    from benchmarks.codegraph_compare.verifier_aggregate import main as implementation

    return implementation(argv)


if __name__ == "__main__":
    raise SystemExit(main())
