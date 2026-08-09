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

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
    verify_receipt,
)
from benchmarks.codegraph_compare.setup_qualification_paths import (
    _open_beneath,
    _open_root,
    canonical_relative_path,
)
from benchmarks.codegraph_compare.verifier_evidence import (
    _verify_external_audit,
    _verify_trusted_inputs,
    _verify_verity,
)
from benchmarks.codegraph_compare.verifier_recompute import _verify_recomputed

CLAIMS = {
    "evaluation_stage": "E0",
    "publishable": False,
    "winner": None,
    "dominance_allowed": False,
    "unlock_allowed": False,
}
PUBLIC_CONFIG_KEYS = frozenset(
    {"schema_version", "executor", "approver", "auditor", "trusted", "root_signature"}
)
ROOT_SIGNATURE_DOMAIN = b"NO1-008A-PUBLIC-CONFIG-ROOT-V1\0"
TRUSTED_KEYS = frozenset(
    {
        "plan_set_hash",
        "plan_hashes",
        "inventory_sha256",
        "source_snapshot_sha256",
        "tool_sha256",
        "config_sha256",
        "seccomp_sha256",
        "images",
        "auditor_runtime",
    }
)
IMAGE_ROLES = ("producer", "executor", "approver", "auditor", "verifier")
PUBLIC_ROLE_KEYS = frozenset({"key_id", "public_key_hex"})
MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "verifier_nonce",
        "verifier_image_digest",
        "run_contract",
        "cells",
    }
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
        "source_snapshot",
        "tool",
        "config",
        "seccomp",
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


def parse_public_config(
    payload: bytes,
    *,
    diagnostic_mode: bool = False,
    diagnostic_root_public_key: bytes | None = None,
) -> dict[str, Any]:
    """Authenticate the closed config with the image-baked root in production."""
    raw = strict_json_loads(payload)
    config: Mapping[str, Any]
    if diagnostic_mode and frozenset(raw) == PUBLIC_CONFIG_KEYS - {"root_signature"}:
        config = raw
    else:
        config = _exact(raw, PUBLIC_CONFIG_KEYS, "public config")
    if type(config["schema_version"]) is not int or config["schema_version"] not in (
        {2, 3} if diagnostic_mode else {3}
    ):
        raise ValueError("public config schema is not authorized")
    if "root_signature" in config:
        signature = config["root_signature"]
        if (
            type(signature) is not str
            or re.fullmatch(r"[0-9a-f]{128}", signature) is None
        ):
            raise ValueError("root signature must be 64 lowercase hexadecimal bytes")
        unsigned = {
            key: value for key, value in config.items() if key != "root_signature"
        }
        if diagnostic_mode:
            root = diagnostic_root_public_key
            if root is None:
                raise ValueError("diagnostic root key is required for a signed config")
        else:
            from benchmarks.codegraph_compare.trust_anchor import baked_root_public_key

            root = baked_root_public_key()
        if type(root) is not bytes or len(root) != 32:
            raise ValueError("root public key must be exactly 32 bytes")
        try:
            Ed25519PublicKey.from_public_bytes(root).verify(
                bytes.fromhex(signature),
                ROOT_SIGNATURE_DOMAIN + canonical_json_bytes(unsigned),
            )
        except (InvalidSignature, ValueError) as exc:
            raise ValueError("public config root signature mismatch") from exc
    keys: list[bytes] = []
    ids: list[str] = []
    for role in ("executor", "approver", "auditor"):
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
    if len(set(ids)) != 3 or len(set(keys)) != 3:
        raise ValueError("public signer identities must differ")
    trusted = _exact(config["trusted"], TRUSTED_KEYS, "trusted config")
    for name in ("plan_set_hash", "tool_sha256", "config_sha256", "seccomp_sha256"):
        if _HEX64.fullmatch(trusted[name]) is None:
            raise ValueError(f"trusted {name} invalid")
    expected_plan_keys = {
        f"{repo}/{arm}"
        for repo, arm in __import__(
            "benchmarks.codegraph_compare.setup_qualification_plan",
            fromlist=["EXPECTED_CELLS"],
        ).EXPECTED_CELLS
    }
    if (
        set(trusted["plan_hashes"]) != expected_plan_keys
        or set(trusted["inventory_sha256"])
        != {key.split("/")[0] for key in expected_plan_keys}
        or set(trusted["source_snapshot_sha256"])
        != {key.split("/")[0] for key in expected_plan_keys}
    ):
        raise ValueError("trusted plan/inventory/source set is not exact")
    if any(
        _HEX64.fullmatch(value) is None
        for table in (
            trusted["plan_hashes"],
            trusted["inventory_sha256"],
            trusted["source_snapshot_sha256"],
        )
        for value in table.values()
    ):
        raise ValueError("trusted evidence digest invalid")
    images = _exact(trusted["images"], frozenset(IMAGE_ROLES), "trusted images")
    if (
        any(_IMAGE.fullmatch(images[role]) is None for role in IMAGE_ROLES)
        or len(set(images.values())) != 5
    ):
        raise ValueError("role images must be exact, authorized, and distinct")
    runtime = _exact(
        trusted["auditor_runtime"],
        frozenset({"image_digest", "interpreter_sha256", "module_sha256"}),
        "auditor runtime",
    )
    if runtime["image_digest"] != images["auditor"] or any(
        _HEX64.fullmatch(runtime[name]) is None
        for name in ("interpreter_sha256", "module_sha256")
    ):
        raise ValueError("auditor runtime authority is invalid")
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
    descriptors = tuple(
        int(part.rsplit("/", 1)[-1])
        for part in command
        if str(part).startswith("/proc/self/fd/")
    )
    return subprocess.run(
        list(command),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=120,
        pass_fds=descriptors,
    )


def _extract_ext4(data_image: Path, destination: Path) -> None:
    # debugfs opens the image read-only by default; destination is a fresh 0700 directory.
    result = subprocess.run(
        ["debugfs", "-R", f"rdump / {destination}", str(data_image)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=120,
        pass_fds=(int(str(data_image).rsplit("/", 1)[-1]),)
        if str(data_image).startswith("/proc/self/fd/")
        else (),
    )
    if result.returncode != 0:
        raise ValueError("read-only ext4 extraction failed")


def _hash_list(paths: list[str]) -> str:
    return hashlib.sha256(canonical_json_bytes(paths)).hexdigest()


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
    diagnostic_mode: bool = False,
    diagnostic_root_public_key: bytes | None = None,
) -> tuple[str, ...]:
    """Verify every mandatory trust root and recompute evidence; never trust body facts."""
    try:
        config = parse_public_config(
            canonical_json_bytes(public_config),
            diagnostic_mode=diagnostic_mode,
            diagnostic_root_public_key=diagnostic_root_public_key,
        )
        if (
            _HEX64.fullmatch(verifier_nonce) is None
            or _IMAGE.fullmatch(verifier_image_digest) is None
            or not process_identity
        ):
            raise ValueError("run correlation/verifier binding invalid")
        verify_receipt(
            receipt,
            config["executor"]["key_id"],
            bytes.fromhex(config["executor"]["public_key_hex"]),
            config["approver"]["key_id"],
            bytes.fromhex(config["approver"]["public_key_hex"]),
        )
        body = receipt["body"]
        if body["run_nonce"] != verifier_nonce:
            raise ValueError("run correlation nonce mismatch")
        if (
            process_identity
            in {
                body["process_audit"]["producer_container_id"],
                body["process_audit"]["cgroup_id"],
            }
            or verifier_image_digest == body["process_audit"]["image_digest"]
        ):
            raise ValueError("verifier process is not isolated from producer")
        _verify_trusted_inputs(body, plan, inventory, evidence, config)
        if verifier_image_digest != config["trusted"]["images"]["verifier"]:
            raise ValueError("unauthorized verifier image")
        image_fds = _verify_verity(body, evidence, runner)
        try:
            audit = _verify_external_audit(body, evidence, config)
            if audit["image_digest"] != body["environment"]["image_digest"]:
                raise ValueError("producer image mismatch")
            with tempfile.TemporaryDirectory(prefix="no1-008a-verify-") as temporary:
                extracted = Path(temporary)
                extractor(Path(f"/proc/self/fd/{image_fds[0]}"), extracted)
                _verify_recomputed(body, plan, inventory, extracted)
        finally:
            for descriptor in image_fds:
                os.close(descriptor)
        return ()
    except (
        KeyError,
        OSError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as error:
        reason = str(error).strip().replace("\n", " ")[:512] or type(error).__name__
        return (f"CELL_EVIDENCE_INVALID:{reason}",)


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
