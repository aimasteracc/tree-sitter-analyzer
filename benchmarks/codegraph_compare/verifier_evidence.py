"""Immutable trust-root, dm-verity, and signed host-audit verification."""

from __future__ import annotations

import hashlib
import os
import stat
import tarfile
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


def _sha_file(path: Path) -> tuple[int, str]:
    descriptor = _open_evidence(path)
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


def _sha_evidence(path: Any, label: str) -> str:
    return _sha_file(_safe_path(path, label))[1]


def _verify_trusted_inputs(
    body: Mapping[str, Any],
    plan: Mapping[str, Any],
    inventory: Mapping[str, Any],
    evidence: Mapping[str, Any],
    config: Mapping[str, Any],
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
        while chunk := os.read(source_fd, 1024 * 1024):
            source_digest.update(chunk)
        if source_digest.hexdigest() != trusted["source_snapshot_sha256"][repo]:
            raise ValueError("immutable source snapshot hash mismatch")
        os.lseek(source_fd, 0, os.SEEK_SET)
        with (
            os.fdopen(os.dup(source_fd), "rb") as stream,
            tarfile.open(fileobj=stream, mode="r:") as archive,
        ):
            members = archive.getmembers()
            for member in members:
                canonical_relative_path(member.name)
            if any(not member.isfile() for member in members):
                raise ValueError(
                    "source snapshot must contain only tracked regular files"
                )
            if any(
                member.uid != 0
                or member.gid != 0
                or member.uname
                or member.gname
                or member.mtime != 0
                for member in members
            ):
                raise ValueError("source snapshot metadata is not deterministic")
            regular_members = {
                member.name: member for member in members if member.isfile()
            }
            if len(regular_members) != sum(member.isfile() for member in members):
                raise ValueError("source snapshot contains duplicate regular paths")
            eligibility = inventory.get("eligibility", inventory)
            tracked = eligibility.get("tracked_files")
            if type(tracked) is not list:
                raise ValueError("source inventory lacks tracked file records")
            tracked_paths = [item[0] for item in tracked]
            if tracked_paths != eligibility.get("tracked_regular_paths"):
                raise ValueError("tracked source paths mismatch")
            if set(tracked_paths) != set(regular_members):
                raise ValueError("source snapshot regular inventory mismatch")
            if [member.name for member in members] != tracked_paths:
                raise ValueError("source snapshot order is not canonical")
            if any(
                regular_members[path].mode != (0o755 if item[1] == "100755" else 0o644)
                for path, item in zip(tracked_paths, tracked, strict=True)
            ):
                raise ValueError("source snapshot executable modes mismatch")
            files: list[tuple[str, str, str, str]] = []
            contents: dict[str, bytes] = {}
            for path, mode, object_id, expected_size, content_hash in tracked:
                extracted = archive.extractfile(regular_members[path])
                if extracted is None:
                    raise ValueError("tracked source is not extractable")
                payload = extracted.read(expected_size + 1)
                if len(payload) != expected_size:
                    raise ValueError("tracked source size mismatch")
                digest = hashlib.sha256(payload).hexdigest()
                algorithm = hashlib.sha1 if len(object_id) == 40 else hashlib.sha256
                git_oid = algorithm(
                    f"blob {len(payload)}\0".encode("ascii") + payload
                ).hexdigest()
                if digest != content_hash or git_oid != object_id:
                    raise ValueError("tracked source blob identity mismatch")
                contents[path] = payload
                files.append((path, mode, object_id, digest))
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
        elif any(marker in contents[path] for marker in rules.generated_markers):
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
        or eligibility.get("repo_fingerprint")
        != sha_json(
            {
                "commit": eligibility.get("commit"),
                "inventory": records,
                "files": files,
            }
        )
    ):
        raise ValueError("source inventory semantic recomputation mismatch")
    for name in ("tool", "config", "seccomp"):
        if _sha_evidence(evidence[name], name) != trusted[f"{name}_sha256"]:
            raise ValueError(f"trusted {name} bytes mismatch")
    if (
        body["plan"]["tool_sha256"] != trusted["tool_sha256"]
        or body["plan"]["config_sha256"] != trusted["config_sha256"]
        or body["plan"]["seccomp_sha256"] != trusted["seccomp_sha256"]
    ):
        raise ValueError("receipt trust-root digest mismatch")
    images = trusted["images"]
    if body["role_images"] != images:
        raise ValueError("signed role image provenance mismatch")
    if body["environment"]["image_digest"] != images["producer"]:
        raise ValueError("unauthorized producer image")


def _verify_verity(
    body: Mapping[str, Any], evidence: Mapping[str, Any], runner: Runner
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
            while chunk := os.read(descriptor, 1024 * 1024):
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
    expected_security = [
        "no-new-privileges",
        f"seccomp={config['trusted']['seccomp_sha256']}",
    ]
    if audit["security_opt"] != expected_security:
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
