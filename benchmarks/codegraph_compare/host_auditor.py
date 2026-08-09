"""Independent two-phase signed host auditor for NO1-008A."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)

DOMAIN = b"NO1-008A-HOST-AUDIT-V1\0"
LAUNCH_DOMAIN = b"NO1-008A-HOST-LAUNCH-V1\0"
TMPFS_TARGET = Path("/").joinpath("tmp").as_posix()


def _run(*args: str) -> bytes:
    result = subprocess.run(
        args, stdin=subprocess.DEVNULL, capture_output=True, check=False, timeout=30
    )
    if result.returncode:
        raise ValueError(f"host observation failed: {args[1]}")
    return result.stdout


def _inspect(container: str) -> dict[str, Any]:
    rows = json.loads(_run("docker", "inspect", container))
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        raise ValueError("docker inspect identity mismatch")
    inspected: dict[str, Any] = rows[0]
    # Names are permitted at launch; returned immutable ID becomes authority.
    return inspected


def _read(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("host fact is not regular")
        out = bytearray()
        while chunk := os.read(fd, 1024 * 1024):
            out.extend(chunk)
        return bytes(out)
    finally:
        os.close(fd)


def _cgroup(pid: int) -> tuple[Path, str]:
    raw = _read(Path(f"/proc/{pid}/cgroup")).decode("ascii")
    rows = [line.split(":", 2) for line in raw.splitlines()]
    matches = [row[2] for row in rows if row[:2] == ["0", ""]]
    if len(matches) != 1 or not matches[0].startswith("/"):
        raise ValueError("container unified cgroup missing")
    relative = matches[0]
    root = Path("/sys/fs/cgroup") / relative.lstrip("/")
    if root.resolve(strict=True) != root:
        raise ValueError("container cgroup is not canonical")
    parent = root.parent
    if parent == Path("/sys/fs/cgroup") or not (parent / "cgroup.procs").is_file():
        raise ValueError("producer lacks a dedicated cgroup v2 parent")
    return parent, "/" + parent.relative_to("/sys/fs/cgroup").as_posix()


def _key(path: Path) -> bytes:
    payload = _read(path)
    if len(payload) != 32:
        raise ValueError("auditor key size invalid")
    return payload


def _sign(
    payload: dict[str, Any], key: bytes, key_id: str, domain: bytes = DOMAIN
) -> dict[str, Any]:
    return {
        "audit": payload,
        "key_id": key_id,
        "algorithm": "Ed25519",
        "signature": Ed25519PrivateKey.from_private_bytes(key)
        .sign(domain + canonical_json_bytes(payload))
        .hex(),
    }


def _verify_launch(envelope: dict[str, Any], key: bytes) -> dict[str, Any]:
    if frozenset(envelope) != {"audit", "key_id", "algorithm", "signature"}:
        raise ValueError("launch token envelope invalid")
    Ed25519PrivateKey.from_private_bytes(key).public_key().verify(
        bytes.fromhex(envelope["signature"]),
        LAUNCH_DOMAIN + canonical_json_bytes(envelope["audit"]),
    )
    audit = envelope["audit"]
    if type(audit) is not dict:
        raise ValueError("launch token payload invalid")
    return audit


def launch(
    container: str,
    expected_image: str,
    seccomp: Path,
    seccomp_host_path: str,
    source: Path,
    plan: Path,
    inventory: Path,
    output: Path,
    since: str,
    run_nonce: str,
) -> dict[str, Any]:
    inspected = _inspect(container)
    state = inspected["State"]
    host = inspected["HostConfig"]
    cid = inspected["Id"]
    pid = state["Pid"]
    if not state["Running"] or type(pid) is not int or pid <= 0:
        raise ValueError("producer is not running at launch audit")
    cgroup_root, cgroup_rel = _cgroup(pid)
    actual_image = json.loads(_run("docker", "image", "inspect", expected_image))[0][
        "Id"
    ]
    if (
        inspected["Config"]["Image"] != expected_image
        or inspected["Image"] != actual_image
    ):
        raise ValueError("actual producer image identity mismatch")
    expected_mounts = {
        (str(source), "/source", True),
        (str(plan), "/plan/cell-plan.json", True),
        (str(inventory), "/plan/inventory.json", True),
        (str(output), "/out", False),
    }
    actual_mounts = {
        (m["Source"], m["Destination"], not m["RW"]) for m in inspected["Mounts"]
    }
    if actual_mounts != expected_mounts:
        raise ValueError("producer bind mounts/source paths/RO flags mismatch")
    seccomp_path = str(seccomp)
    expected_security = ["no-new-privileges", f"seccomp={seccomp_host_path}"]
    if host["SecurityOpt"] != expected_security:
        raise ValueError("actual Docker security options mismatch")
    if (
        inspected["Config"]["User"] != "65532:65532"
        or host["ReadonlyRootfs"] is not True
        or host["CapDrop"] != ["ALL"]
        or host["NetworkMode"] != "none"
    ):
        raise ValueError("producer isolation flags mismatch")
    limits = {
        "pids_limit": host["PidsLimit"],
        "memory": host["Memory"],
        "nano_cpus": host["NanoCpus"],
    }
    if limits != {"pids_limit": 64, "memory": 4294967296, "nano_cpus": 1000000000}:
        raise ValueError("producer resource limits mismatch")
    tmpfs = host["Tmpfs"]
    if tmpfs != {TMPFS_TARGET: "rw,noexec,nosuid,nodev,size=64m"}:
        raise ValueError("producer tmpfs flags mismatch")
    return {
        "producer_container_id": cid,
        "launch_pid": pid,
        "cgroup_relative": cgroup_rel,
        "cgroup_id": str(cgroup_root),
        "image_digest": expected_image.split("@")[-1],
        "actual_image_id": actual_image,
        "run_nonce": run_nonce,
        "since": since,
        "seccomp_path": seccomp_path,
        "seccomp_sha256": hashlib.sha256(_read(seccomp)).hexdigest(),
        "security_opt": expected_security,
        "mounts": [list(x) for x in sorted(expected_mounts)],
        "resource_limits": limits,
        "tmpfs": tmpfs,
        "container_user": "65532:65532",
        "readonly_rootfs": True,
        "cap_drop": ["ALL"],
    }


def terminal(
    token_payload: bytes, seccomp: Path, expected_image: str, key: bytes
) -> dict[str, Any]:
    envelope = strict_json_loads(token_payload)
    launched = _verify_launch(envelope, key)
    cid = launched["producer_container_id"]
    inspected = _inspect(cid)
    state = inspected["State"]
    if (
        state["Running"]
        or state["Pid"] != 0
        or inspected["RestartCount"] != 0
        or state["ExitCode"] != 0
    ):
        raise ValueError("producer terminal state invalid")
    if (
        inspected["Config"]["Image"] != expected_image
        or inspected["Image"] != launched["actual_image_id"]
    ):
        raise ValueError("terminal image identity changed")
    host = inspected["HostConfig"]
    actual_mounts = sorted(
        [[m["Source"], m["Destination"], not m["RW"]] for m in inspected["Mounts"]]
    )
    actual_limits = {
        "pids_limit": host["PidsLimit"],
        "memory": host["Memory"],
        "nano_cpus": host["NanoCpus"],
    }
    if (
        inspected["Config"]["User"] != launched["container_user"]
        or host["ReadonlyRootfs"] is not launched["readonly_rootfs"]
        or host["CapDrop"] != launched["cap_drop"]
        or host["NetworkMode"] != "none"
        or host["SecurityOpt"] != launched["security_opt"]
        or actual_mounts != launched["mounts"]
        or actual_limits != launched["resource_limits"]
        or host["Tmpfs"] != launched["tmpfs"]
    ):
        raise ValueError(
            "terminal Docker security facts differ from staged launch audit"
        )
    if (
        launched["seccomp_path"] != str(seccomp)
        or hashlib.sha256(_read(seccomp)).hexdigest() != launched["seccomp_sha256"]
    ):
        raise ValueError("staged seccomp identity changed")
    launches = sum(
        1
        for line in _run(
            "docker",
            "events",
            "--since",
            launched["since"],
            "--until",
            str(int(time.time()) + 1),
            "--filter",
            f"container={cid}",
            "--filter",
            "event=start",
            "--format",
            "{{.ID}}",
        ).splitlines()
        if line.strip() == cid.encode()
    )
    root = Path(launched["cgroup_id"])
    processes = [
        int(line) for line in _read(root / "cgroup.procs").splitlines() if line
    ]
    if launches != 1 or processes:
        raise ValueError("launch count or terminal cgroup invalid")

    def scalar(name: str) -> int:
        return int(_read(root / name).strip())

    cpu = dict(line.split() for line in _read(root / "cpu.stat").decode().splitlines())
    io_bytes = sum(
        int(field.split("=")[1])
        for line in _read(root / "io.stat").decode().splitlines()
        for field in line.split()[1:]
        if field.startswith(("rbytes=", "wbytes="))
    )
    from datetime import datetime

    def parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    resources = {
        "wall_ns": int(
            (parse(state["FinishedAt"]) - parse(state["StartedAt"])).total_seconds()
            * 1_000_000_000
        ),
        "cpu_usec": int(cpu["usage_usec"]),
        "io_bytes": io_bytes,
        "memory_peak_bytes": scalar("memory.peak"),
        "pids_peak": scalar("pids.peak"),
    }
    return {
        "producer_container_id": cid,
        "image_digest": launched["image_digest"],
        "actual_image_id": launched["actual_image_id"],
        "cgroup_id": launched["cgroup_id"],
        "network_mode": "none",
        "security_opt": ["no-new-privileges", f"seccomp={launched['seccomp_sha256']}"],
        "restart_count": 0,
        "terminal_pid": 0,
        "launch_count": 1,
        "cgroup_processes_after_stop": [],
        "pid1_exit": 0,
        "run_nonce": launched["run_nonce"],
        "launch_token_sha256": hashlib.sha256(token_payload).hexdigest(),
        "container_user": launched["container_user"],
        "readonly_rootfs": launched["readonly_rootfs"],
        "cap_drop": launched["cap_drop"],
        "mounts": launched["mounts"],
        "resource_limits": launched["resource_limits"],
        "tmpfs": launched["tmpfs"],
        "resource_observations": resources,
    }


def _authorize_runtime(public_config: Path) -> dict[str, Any]:
    from benchmarks.codegraph_compare.verifier import parse_public_config

    config = parse_public_config(_read(public_config))
    expected = config["trusted"]["auditor_runtime"]
    own = _inspect(os.environ.get("HOSTNAME", ""))
    interpreter = hashlib.sha256(
        _read(Path(sys.executable).resolve(strict=True))
    ).hexdigest()
    module = hashlib.sha256(_read(Path(__file__))).hexdigest()
    if (
        own["Config"]["Image"].split("@")[-1] != expected["image_digest"]
        or interpreter != expected["interpreter_sha256"]
        or module != expected["module_sha256"]
    ):
        raise ValueError("unauthorized host-auditor image or executable bytes")
    return config


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="phase", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--seccomp", required=True)
    common.add_argument("--expected-image", required=True)
    common.add_argument("--private-key", required=True)
    common.add_argument("--key-id", required=True)
    common.add_argument("--public-config", required=True)
    launch_p = sub.add_parser("launch", parents=[common])
    launch_p.add_argument("--container", required=True)
    launch_p.add_argument("--seccomp-host-path", required=True)
    launch_p.add_argument("--source", required=True)
    launch_p.add_argument("--plan", required=True)
    launch_p.add_argument("--inventory", required=True)
    launch_p.add_argument("--output", required=True)
    launch_p.add_argument("--since", required=True)
    launch_p.add_argument("--run-nonce", required=True)
    term = sub.add_parser("terminal", parents=[common])
    term.add_argument("--launch-token", required=True)
    a = p.parse_args(argv)
    config = _authorize_runtime(Path(a.public_config))
    if a.key_id != config["auditor"]["key_id"]:
        raise ValueError("auditor key ID is not root-authorized")
    if a.expected_image.split("@")[-1] != config["trusted"]["images"]["producer"]:
        raise ValueError("producer image is not root-authorized")
    key = _key(Path(a.private_key))
    if (
        Ed25519PrivateKey.from_private_bytes(key).public_key().public_bytes_raw().hex()
        != config["auditor"]["public_key_hex"]
    ):
        raise ValueError("auditor private key is not root-authorized")
    if a.phase == "launch":
        result = _sign(
            launch(
                a.container,
                a.expected_image,
                Path(a.seccomp),
                a.seccomp_host_path,
                Path(a.source),
                Path(a.plan),
                Path(a.inventory),
                Path(a.output),
                a.since,
                a.run_nonce,
            ),
            key,
            a.key_id,
            LAUNCH_DOMAIN,
        )
    else:
        result = _sign(
            terminal(
                _read(Path(a.launch_token)),
                Path(a.seccomp),
                a.expected_image,
                key,
            ),
            key,
            a.key_id,
        )
    sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
