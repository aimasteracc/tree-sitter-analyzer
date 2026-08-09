"""Immutable trust-root, dm-verity, and signed host-audit verification."""

from __future__ import annotations

import hashlib
import os
import stat
import tarfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    canonical_plan_hash,
    strict_json_loads,
)
from benchmarks.codegraph_compare.setup_qualification_paths import (
    canonical_relative_path,
)
from benchmarks.codegraph_compare.setup_qualification_plan import DEFAULT_SOURCE_RULES
from benchmarks.codegraph_compare.verifier_authority import (
    AUTHORITY_AUDIT_KEYS,
    verify_authority_provenance,
)

Runner = Callable[[Sequence[str]], Any]
TMPFS_TARGET = Path("/").joinpath("tmp").as_posix()

RECEIPT_IMAGE_ROLES = ("producer", "executor", "approver", "auditor", "verifier")


def _receipt_images(trusted: Mapping[str, Any]) -> dict[str, Any]:
    images = trusted["images"]
    return {role: images[role] for role in RECEIPT_IMAGE_ROLES}


def _safe_path(raw: Any, label: str) -> Path:
    if (
        type(raw) is not str
        or not raw
        or "," in raw
        or any(ord(c) < 32 or ord(c) == 127 for c in raw)
    ):
        raise ValueError(f"{label} contains a comma or control character")
    path = Path(raw)
    if str(path).startswith("/proc/self/fd/"):
        descriptor = int(path.name)
        os.fstat(descriptor)
        return path
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError(f"{label} must be canonical, absolute, and existing")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        if stat.S_ISLNK(os.lstat(current).st_mode):
            raise ValueError(f"{label} parent components must not be symbolic links")
    return path


def _open_evidence(path: Path) -> int:
    if str(path).startswith("/proc/self/fd/"):
        descriptor = os.dup(int(path.name))
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    return os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))


def _sha_file(
    path: Path, *, deadline_monotonic: float | None = None
) -> tuple[int, str]:
    descriptor = _open_evidence(path)
    digest = hashlib.sha256()
    size = 0
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("evidence image is not regular")
        while True:
            if (
                deadline_monotonic is not None
                and time.monotonic() >= deadline_monotonic
            ):
                raise TimeoutError("evidence hashing deadline expired")
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return size, digest.hexdigest()


def _recompute_git_root(records: list[list[str]]) -> str:
    """Rebuild nested Git tree objects from the closed leaf inventory."""
    if not records:
        raise ValueError("empty Git inventory")
    oid_bytes = len(bytes.fromhex(records[0][2]))
    algorithm = (
        hashlib.sha1 if oid_bytes == 20 else hashlib.sha256 if oid_bytes == 32 else None
    )
    if algorithm is None or any(
        len(bytes.fromhex(item[2])) != oid_bytes for item in records
    ):
        raise ValueError("mixed or unsupported Git object format")
    root: dict[str, Any] = {}
    for path, mode, oid in records:
        node = root
        parts = path.split("/")
        for component in parts[:-1]:
            existing = node.setdefault(component, {})
            if type(existing) is not dict:
                raise ValueError("Git inventory file/directory collision")
            node = existing
        if parts[-1] in node:
            raise ValueError("duplicate Git inventory path")
        node[parts[-1]] = (mode, oid)

    def tree_oid(node: dict[str, Any]) -> str:
        encoded: list[tuple[bytes, bytes]] = []
        for name, value in node.items():
            raw_name = name.encode("utf-8")
            if type(value) is dict:
                mode, oid = "40000", tree_oid(value)
            else:
                mode, oid = value
            encoded.append(
                (
                    raw_name + (b"/" if mode == "40000" else b""),
                    mode.encode() + b" " + raw_name + b"\0" + bytes.fromhex(oid),
                )
            )
        body = b"".join(
            value for _key, value in sorted(encoded, key=lambda item: item[0])
        )
        return algorithm(f"tree {len(body)}\0".encode("ascii") + body).hexdigest()

    return tree_oid(root)


def _sha_evidence(
    path: Any, label: str, *, deadline_monotonic: float | None = None
) -> str:
    return _sha_file(_safe_path(path, label), deadline_monotonic=deadline_monotonic)[1]


def _verify_trusted_inputs(
    body: Mapping[str, Any],
    plan: Mapping[str, Any],
    inventory: Mapping[str, Any],
    evidence: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    deadline_monotonic: float | None = None,
) -> None:
    trusted = config["trusted"]
    identity = f"{body['cell']['repo_id']}/{body['cell']['arm_id']}"
    repo = body["cell"]["repo_id"]
    logical_plan_hash = canonical_plan_hash(plan)
    if (
        plan.get("plan_hash") != logical_plan_hash
        or logical_plan_hash != trusted["plan_hashes"][identity]
    ):
        raise ValueError("canonical plan hash mismatch")
    if (
        plan.get("plan_set_hash") != trusted["plan_set_hash"]
        or body["plan"]["plan_set_hash"] != trusted["plan_set_hash"]
    ):
        raise ValueError("common plan-set hash mismatch")
    if (
        hashlib.sha256(canonical_json_bytes(inventory)).hexdigest()
        != trusted["inventory_sha256"][repo]
    ):
        raise ValueError("canonical inventory hash mismatch")
    source_path = _safe_path(evidence["source_snapshot"], "source snapshot")
    source_fd = _open_evidence(source_path)
    try:
        source_digest = hashlib.sha256()
        while True:
            if (
                deadline_monotonic is not None
                and time.monotonic() >= deadline_monotonic
            ):
                raise TimeoutError("source snapshot hashing deadline expired")
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            source_digest.update(chunk)
        if source_digest.hexdigest() != trusted["source_snapshot_sha256"][repo]:
            raise ValueError("immutable source snapshot hash mismatch")
        os.lseek(source_fd, 0, os.SEEK_SET)
        eligibility = inventory.get("eligibility", inventory)
        tracked = eligibility.get("tracked_files")
        if type(tracked) is not list:
            raise ValueError("source inventory lacks tracked file records")
        tracked_paths = [item[0] for item in tracked]
        if tracked_paths != eligibility.get("tracked_regular_paths"):
            raise ValueError("tracked source paths mismatch")
        generated_paths: set[str] = set()
        fingerprint = hashlib.sha256()
        fingerprint.update(b'{"commit":')
        fingerprint.update(canonical_json_bytes(eligibility.get("commit")))
        fingerprint.update(b',"files":[')
        with (
            os.fdopen(os.dup(source_fd), "rb") as stream,
            tarfile.open(fileobj=stream, mode="r|") as archive,
        ):
            seen: set[str] = set()
            count = 0
            for member in archive:
                if count >= len(tracked):
                    raise ValueError("source snapshot contains extra members")
                path, mode, object_id, expected_size, content_hash = tracked[count]
                canonical_relative_path(member.name)
                if member.name != path or member.name in seen or not member.isfile():
                    raise ValueError(
                        "source snapshot order or regular inventory mismatch"
                    )
                seen.add(member.name)
                if (
                    member.uid != 0
                    or member.gid != 0
                    or member.uname
                    or member.gname
                    or member.mtime != 0
                    or member.mode != (0o755 if mode == "100755" else 0o644)
                    or member.size != expected_size
                ):
                    raise ValueError("source snapshot metadata is not deterministic")
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ValueError("tracked source is not extractable")
                content_digest = hashlib.sha256()
                algorithms = {40: hashlib.sha1, 64: hashlib.sha256}
                try:
                    object_digest = algorithms[len(object_id)]()
                except KeyError as exc:
                    raise ValueError(
                        "tracked source Git object format invalid"
                    ) from exc
                object_digest.update(f"blob {expected_size}\0".encode("ascii"))
                overlap = b""
                overlap_bytes = (
                    max(
                        (
                            len(marker)
                            for marker in DEFAULT_SOURCE_RULES.generated_markers
                        ),
                        default=1,
                    )
                    - 1
                )
                remaining = expected_size
                generated = False
                while remaining:
                    if (
                        deadline_monotonic is not None
                        and time.monotonic() >= deadline_monotonic
                    ):
                        raise TimeoutError("source blob hashing deadline expired")
                    chunk = extracted.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("tracked source size mismatch")
                    remaining -= len(chunk)
                    content_digest.update(chunk)
                    object_digest.update(chunk)
                    window = overlap + chunk
                    if not generated and any(
                        marker in window
                        for marker in DEFAULT_SOURCE_RULES.generated_markers
                    ):
                        generated = True
                    overlap = window[-overlap_bytes:] if overlap_bytes else b""
                if (
                    deadline_monotonic is not None
                    and time.monotonic() >= deadline_monotonic
                ):
                    raise TimeoutError("source blob hashing deadline expired")
                if extracted.read(1):
                    raise ValueError("tracked source exceeds declared size")
                digest = content_digest.hexdigest()
                if digest != content_hash or object_digest.hexdigest() != object_id:
                    raise ValueError("tracked source blob identity mismatch")
                if generated:
                    generated_paths.add(path)
                if count:
                    fingerprint.update(b",")
                fingerprint.update(
                    canonical_json_bytes([path, mode, object_id, digest])
                )
                count += 1
            if count != len(tracked):
                raise ValueError("source snapshot regular inventory mismatch")
        fingerprint.update(b'],"inventory":')
        fingerprint.update(canonical_json_bytes(eligibility.get("tracked_entries")))
        fingerprint.update(b"}")
        repo_fingerprint = fingerprint.hexdigest()
    finally:
        os.close(source_fd)
    rules = DEFAULT_SOURCE_RULES
    if (
        eligibility.get("repo_id") != repo
        or eligibility.get("source_rules_hash") != rules.digest
    ):
        raise ValueError("source rules authority mismatch")
    records = eligibility.get("tracked_entries")
    if type(records) is not list or any(
        type(item) is not list or len(item) != 3 for item in records
    ):
        raise ValueError("tracked Git entries missing")
    regular_records = [[item[0], item[1], item[2]] for item in tracked]
    if [item for item in records if item[1] in {"100644", "100755"}] != regular_records:
        raise ValueError("tracked regular Git entries mismatch")
    expected_eligible: list[str] = []
    expected_excluded: list[list[str]] = [
        [path, "gitlink" if mode == "160000" else "symlink"]
        for path, mode, _oid in records
        if mode in {"160000", "120000"}
    ]
    if any(
        mode not in {"100644", "100755", "160000", "120000"} for _, mode, _ in records
    ):
        raise ValueError("unsupported tracked Git mode")
    extensions = rules.extensions(repo)
    for path in tracked_paths:
        components = path.split("/")
        reason = None
        if PurePosixPath(path).suffix not in extensions:
            reason = "extension"
        elif any(part in rules.excluded_components for part in components[:-1]):
            reason = "excluded-component"
        elif any(path.endswith(suffix) for suffix in rules.minified_suffixes):
            reason = "minified"
        elif path in generated_paths:
            reason = "generated"
        if reason is None:
            expected_eligible.append(path)
        else:
            expected_excluded.append([path, reason])
    expected_excluded.sort()

    def sha_json(value: Any) -> str:
        return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

    if (
        eligibility.get("tracked_inventory_hash") != sha_json(records)
        or eligibility.get("root_tree_id") != _recompute_git_root(records)
        or eligibility.get("eligible_paths") != expected_eligible
        or eligibility.get("eligible_paths_hash") != sha_json(expected_eligible)
        or eligibility.get("prefilter_exclusions") != expected_excluded
        or eligibility.get("repo_fingerprint") != repo_fingerprint
    ):
        raise ValueError("source inventory semantic recomputation mismatch")
    for name in ("tool", "config", "seccomp"):
        if (
            _sha_evidence(evidence[name], name, deadline_monotonic=deadline_monotonic)
            != trusted[f"{name}_sha256"]
        ):
            raise ValueError(f"trusted {name} bytes mismatch")
    if (
        body["plan"]["tool_sha256"] != trusted["tool_sha256"]
        or body["plan"]["config_sha256"] != trusted["config_sha256"]
        or body["plan"]["seccomp_sha256"] != trusted["seccomp_sha256"]
    ):
        raise ValueError("receipt trust-root digest mismatch")
    images = _receipt_images(trusted)
    if body["role_images"] != images:
        raise ValueError("signed role image provenance mismatch")
    if body["environment"]["image_digest"] != images["producer"]:
        raise ValueError("unauthorized producer image")


def _verify_verity(
    body: Mapping[str, Any],
    evidence: Mapping[str, Any],
    runner: Runner,
    *,
    deadline_monotonic: float | None = None,
) -> tuple[int, int]:
    snapshot = body["snapshot"]
    paths = (
        _safe_path(evidence["data_image"], "data image"),
        _safe_path(evidence["hash_image"], "hash image"),
    )
    descriptors = tuple(_open_evidence(path) for path in paths)
    try:
        observed: list[int | str] = []
        for descriptor in descriptors:
            digest = hashlib.sha256()
            size = 0
            while True:
                if (
                    deadline_monotonic is not None
                    and time.monotonic() >= deadline_monotonic
                ):
                    raise TimeoutError("verity image hashing deadline expired")
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
            os.lseek(descriptor, 0, os.SEEK_SET)
            observed.extend((size, digest.hexdigest()))
        if tuple(observed) != (
            snapshot["data_image_size"],
            snapshot["data_image_sha256"],
            snapshot["hash_image_size"],
            snapshot["hash_image_sha256"],
        ):
            raise ValueError("image digest or size mismatch")
        expected_blocks = (
            snapshot["data_image_size"] + snapshot["data_block_size"] - 1
        ) // snapshot["data_block_size"]
        if snapshot["data_blocks"] != expected_blocks:
            raise ValueError("dm-verity data_blocks mismatch")
        result = runner(
            [
                "veritysetup",
                "verify",
                f"/proc/self/fd/{descriptors[0]}",
                f"/proc/self/fd/{descriptors[1]}",
                snapshot["root_hash"],
                "--hash",
                "sha256",
                "--salt",
                snapshot["salt"],
                "--data-block-size",
                str(snapshot["data_block_size"]),
                "--hash-block-size",
                str(snapshot["hash_block_size"]),
                "--data-blocks",
                str(snapshot["data_blocks"]),
            ]
        )
        if result.returncode != 0:
            raise ValueError("veritysetup verification failed")
        return descriptors[0], descriptors[1]
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise


def _verify_external_audit(
    body: Mapping[str, Any], evidence: Mapping[str, Any], config: Mapping[str, Any]
) -> Mapping[str, Any]:
    audit_path = _safe_path(evidence["process_audit"], "signed host audit")
    audit_fd = _open_evidence(audit_path)
    try:
        if not stat.S_ISREG(os.fstat(audit_fd).st_mode):
            raise ValueError("signed host audit is not regular")
        chunks = bytearray()
        while chunk := os.read(audit_fd, 1024 * 1024):
            chunks.extend(chunk)
        payload = bytes(chunks)
    finally:
        os.close(audit_fd)
    envelope = strict_json_loads(payload)
    if frozenset(envelope) != frozenset({"audit", "key_id", "algorithm", "signature"}):
        raise ValueError("host audit envelope is not closed")
    request = envelope["audit"]
    auditor = config["auditor"]
    if (
        type(request) is not dict
        or frozenset(request) != {"protocol", "phase", "service_measurement", "audit"}
        or request["protocol"] != auditor["protocol"]
        or request["phase"] != "terminal"
        or request["service_measurement"] != auditor["service_measurement"]
        or type(request["audit"]) is not dict
    ):
        raise ValueError("external audit authority request is not closed")
    audit = request["audit"]
    required = AUTHORITY_AUDIT_KEYS
    if frozenset(audit) != required:
        raise ValueError("host audit ledger is not closed")
    if envelope["key_id"] != auditor["key_id"] or envelope["algorithm"] != "Ed25519":
        raise ValueError("host audit authority mismatch")
    try:
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(auditor["public_key_hex"])
        ).verify(
            bytes.fromhex(envelope["signature"]),
            b"NO1-008A-HOST-AUDIT-V1\0" + canonical_json_bytes(request),
        )
    except (InvalidSignature, ValueError) as error:
        raise ValueError("host audit signature mismatch") from error
    if (
        audit["network_mode"] != "none"
        or audit["restart_count"] != 0
        or audit["terminal_pid"] != 0
        or audit["launch_count"] != 1
        or audit["cgroup_processes_after_stop"] != []
        or audit["pid1_exit"] != 0
    ):
        raise ValueError(
            "host audit does not prove terminal isolated one-launch execution"
        )
    observed_security = audit["security_opt"]
    if (
        type(observed_security) is not list
        or len(observed_security) != 2
        or observed_security[0] != "no-new-privileges"
        or type(observed_security[1]) is not str
        or not observed_security[1].startswith("seccomp=/")
    ):
        raise ValueError("host audit security options mismatch")
    if (
        audit["container_user"] != "65532:65532"
        or audit["readonly_rootfs"] is not True
        or audit["cap_drop"] != ["ALL"]
        or audit["resource_limits"]
        != {"pids_limit": 64, "memory": 4294967296, "nano_cpus": 1000000000}
        or audit["tmpfs"] != {TMPFS_TARGET: "rw,noexec,nosuid,nodev,size=64m"}
    ):
        raise ValueError("host audit isolation facts mismatch")
    if audit["run_nonce"] != body["run_nonce"]:
        raise ValueError("signed host audit nonce mismatch")
    if audit["resource_observations"] != {
        key: value for key, value in body["resources"].items() if key != "plan_digest"
    }:
        raise ValueError("resource observations are not host-audit derived")
    expected = {
        key: value
        for key, value in body["process_audit"].items()
        if key != "audit_bytes"
    }
    # Receipt carries the stable subset; the signed request additionally binds
    # host path identities, terminal state, and both immutable image files.
    if any(audit.get(key) != value for key, value in expected.items()):
        raise ValueError("receipt host audit facts mismatch")
    if audit["actual_image_id"] != config["trusted"]["image_ids"]["producer"]:
        raise ValueError("host audit top-level Docker Image ID mismatch")
    verify_authority_provenance(audit, body, config)
    if (
        audit["data_image"]["sha256"] != body["snapshot"]["data_image_sha256"]
        or audit["data_image"]["size"] != body["snapshot"]["data_image_size"]
        or audit["hash_image"]["sha256"] != body["snapshot"]["hash_image_sha256"]
        or audit["hash_image"]["size"] != body["snapshot"]["hash_image_size"]
    ):
        raise ValueError("authority-signed dm-verity image identity mismatch")
    blob = body["process_audit"]["audit_bytes"]
    if (
        len(payload) != blob["size_bytes"]
        or hashlib.sha256(payload).hexdigest() != blob["sha256"]
    ):
        raise ValueError("signed host audit bytes mismatch")
    return audit
