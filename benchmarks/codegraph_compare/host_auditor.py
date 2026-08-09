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

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from benchmarks.codegraph_compare.audit_authority_client import exchange as _authority
from benchmarks.codegraph_compare.audit_authority_storage import _producer_mount_targets
from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)

DOMAIN = b"NO1-008A-HOST-AUDIT-V1\0"
LAUNCH_DOMAIN = b"NO1-008A-HOST-LAUNCH-V1\0"
PROTOCOL = "no1-008a-audit-v1"
TMPFS_TARGET = Path("/").joinpath("tmp").as_posix()
MAX_MESSAGE = 4 * 1024 * 1024


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
    return rows[0]


def _read(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("host fact is not regular")
        out = bytearray()
        while chunk := os.read(fd, 1024 * 1024):
            out.extend(chunk)
            if len(out) > MAX_MESSAGE:
                raise ValueError("host fact exceeds audit bound")
        return bytes(out)
    finally:
        os.close(fd)


def _identity(path: Path, *, digest: bool = False) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    if resolved != path:
        raise ValueError("host identity path is not canonical")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(fd)
        result: dict[str, Any] = {
            "path": str(path),
            "device": metadata.st_dev,
            "inode": metadata.st_ino,
            "mode": stat.S_IMODE(metadata.st_mode),
            "uid": metadata.st_uid,
            "gid": metadata.st_gid,
        }
        if digest:
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("hashed identity is not regular")
            hasher = hashlib.sha256()
            size = 0
            while chunk := os.read(fd, 1024 * 1024):
                hasher.update(chunk)
                size += len(chunk)
            result.update(size=size, sha256=hasher.hexdigest())
        elif not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("directory identity is not a directory")
        return result
    finally:
        os.close(fd)


def _cgroup(pid: int) -> tuple[Path, str]:
    raw = _read(Path(f"/proc/{pid}/cgroup")).decode("ascii")
    rows = [line.split(":", 2) for line in raw.splitlines()]
    matches = [row[2] for row in rows if row[:2] == ["0", ""]]
    if len(matches) != 1 or not matches[0].startswith("/"):
        raise ValueError("container unified cgroup missing")
    root = Path("/sys/fs/cgroup") / matches[0].lstrip("/")
    if root.resolve(strict=True) != root:
        raise ValueError("container cgroup is not canonical")
    parent = root.parent
    if parent == Path("/sys/fs/cgroup") or not (parent / "cgroup.procs").is_file():
        raise ValueError("producer lacks a dedicated cgroup v2 parent")
    return parent, "/" + parent.relative_to("/sys/fs/cgroup").as_posix()


def _mounts(inspected: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mounts = inspected.get("Mounts")
    if type(mounts) is not list:
        raise ValueError("Docker mounts absent")
    by_target: dict[str, dict[str, Any]] = {}
    for item in mounts:
        if type(item) is not dict or type(item.get("Destination")) is not str:
            raise ValueError("producer mount record invalid")
        target = item["Destination"]
        if target in by_target:
            raise ValueError("producer mount target is duplicated")
        by_target[target] = item
    fixed = {
        "/source",
        "/plan/cell-plan.json",
        "/plan/inventory.json",
        "/plan/seccomp.json",
        "/out",
    }
    if not fixed.issubset(by_target):
        raise ValueError("producer fixed mount target set mismatch")
    plan_path = Path(by_target["/plan/cell-plan.json"].get("Source", ""))
    plan = strict_json_loads(_read(plan_path))
    source_target, tool_target, config_target = _producer_mount_targets(plan)
    expected_targets = fixed | {tool_target, config_target}
    if source_target != "/source" or set(by_target) != expected_targets:
        raise ValueError("producer mount target set mismatch")
    access = {target: target != "/out" for target in expected_targets}
    if any(
        by_target[target].get("RW") is access[target] for target in expected_targets
    ):
        raise ValueError("producer mount access mismatch")
    staged = plan_path.parent
    expected_sources = {
        "/plan/cell-plan.json": staged / "plan.json",
        "/plan/inventory.json": staged / "inventory.json",
        "/plan/seccomp.json": staged / "seccomp",
        tool_target: staged / "tool",
        config_target: staged / "config",
    }
    for target, item in by_target.items():
        source = item.get("Source")
        if (
            item.get("Type") != "bind"
            or type(source) is not str
            or Path(source).resolve(strict=True).as_posix() != source
            or item.get("Propagation") not in (None, "rprivate")
        ):
            raise ValueError("producer mount source is not exact canonical bind")
        expected = expected_sources.get(target)
        if expected is not None and Path(source) != expected:
            raise ValueError("producer authenticated mount source mismatch")
    source_path = Path(by_target["/source"]["Source"])
    output_path = Path(by_target["/out"]["Source"])
    if (
        source_path.name != "source"
        or output_path.name != "producer-output"
        or source_path.parent != output_path.parent
    ):
        raise ValueError("producer source/output mount source mismatch")
    return by_target


def _docker_facts(
    inspected: dict[str, Any], expected_image: str, expected_id: str
) -> dict[str, Any]:
    host = inspected["HostConfig"]
    if inspected.get("Image") != expected_id:
        raise ValueError("Docker top-level Image ID is not root-authorized")
    if inspected["Config"].get("Image") != expected_image:
        raise ValueError("Docker Config.Image is not the authorized launch reference")
    security = {
        "config_image": inspected["Config"]["Image"],
        "image_id": inspected["Image"],
        "user": inspected["Config"].get("User"),
        "readonly_rootfs": host.get("ReadonlyRootfs"),
        "cap_drop": host.get("CapDrop"),
        "network_mode": host.get("NetworkMode"),
        "security_opt": host.get("SecurityOpt"),
        "pids_limit": host.get("PidsLimit"),
        "memory": host.get("Memory"),
        "nano_cpus": host.get("NanoCpus"),
        "tmpfs": host.get("Tmpfs"),
    }
    if (
        security["user"] != "65532:65532"
        or security["readonly_rootfs"] is not True
        or security["cap_drop"] != ["ALL"]
        or security["network_mode"] != "none"
        or security["pids_limit"] != 64
        or security["memory"] != 4294967296
        or security["nano_cpus"] != 1000000000
        or security["tmpfs"] != {TMPFS_TARGET: "rw,noexec,nosuid,nodev,size=64m"}
    ):
        raise ValueError("producer Docker security facts mismatch")
    return security


def _verify_launch(payload: bytes, authority: dict[str, Any]) -> dict[str, Any]:
    envelope = strict_json_loads(payload)
    if type(envelope) is not dict or frozenset(envelope) != {
        "audit",
        "key_id",
        "algorithm",
        "signature",
    }:
        raise ValueError("launch token envelope invalid")
    request = envelope["audit"]
    if (
        type(request) is not dict
        or envelope["key_id"] != authority["key_id"]
        or envelope["algorithm"] != "Ed25519"
    ):
        raise ValueError("launch token request or authority invalid")
    Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(authority["public_key_hex"])
    ).verify(
        bytes.fromhex(envelope["signature"]),
        LAUNCH_DOMAIN + canonical_json_bytes(request),
    )
    if request.get("protocol") != PROTOCOL or request.get("phase") != "launch":
        raise ValueError("launch protocol mismatch")
    return request


def _request(
    phase: str, audit: dict[str, Any], authority: dict[str, Any]
) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL,
        "phase": phase,
        "service_measurement": authority["service_measurement"],
        "audit": audit,
    }


def launch(
    container: str,
    expected_image: str,
    seccomp: Path,
    since: str,
    run_nonce: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    inspected = _inspect(container)
    state = inspected["State"]
    if (
        state.get("Running") is not True
        or type(state.get("Pid")) is not int
        or state["Pid"] <= 0
    ):
        raise ValueError("producer is not running at launch audit")
    cgroup_root, cgroup_relative = _cgroup(state["Pid"])
    mounts = _mounts(inspected)
    plan_path = Path(mounts["/plan/cell-plan.json"]["Source"])
    plan = strict_json_loads(_read(plan_path))
    security = _docker_facts(
        inspected, expected_image, config["trusted"]["image_ids"]["producer"]
    )
    return {
        "producer_container_id": inspected["Id"],
        "run_nonce": run_nonce,
        "since": since,
        "cell": plan["cell"],
        "plan": _identity(plan_path, digest=True),
        "source": _identity(Path(mounts["/source"]["Source"])),
        "output": _identity(Path(mounts["/out"]["Source"])),
        "inventory": _identity(
            Path(mounts["/plan/inventory.json"]["Source"]), digest=True
        ),
        "mounts": [
            [m["Source"], target, not m["RW"]] for target, m in sorted(mounts.items())
        ],
        "launch_pid": state["Pid"],
        "cgroup_id": str(cgroup_root),
        "cgroup_relative": cgroup_relative,
        "image_digest": expected_image.split("@")[-1],
        "actual_image_id": inspected["Image"],
        "security": security,
        "seccomp_sha256": hashlib.sha256(_read(seccomp)).hexdigest(),
    }


def terminal(
    launch_payload: bytes,
    seccomp: Path,
    expected_image: str,
    data_image: Path,
    hash_image: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    launched = _verify_launch(launch_payload, config["auditor"])
    prior = launched["audit"]
    inspected = _inspect(prior["producer_container_id"])
    state = inspected["State"]
    if (
        state.get("Running")
        or state.get("Pid") != 0
        or inspected.get("RestartCount") != 0
        or state.get("ExitCode") != 0
    ):
        raise ValueError("producer terminal state invalid")
    security = _docker_facts(
        inspected, expected_image, config["trusted"]["image_ids"]["producer"]
    )
    mounts = _mounts(inspected)
    actual_mounts = [
        [item["Source"], target, not item["RW"]]
        for target, item in sorted(mounts.items())
    ]
    identities = {
        "plan": _identity(Path(mounts["/plan/cell-plan.json"]["Source"]), digest=True),
        "source": _identity(Path(mounts["/source"]["Source"])),
        "output": _identity(Path(mounts["/out"]["Source"])),
    }
    if (
        security != prior["security"]
        or actual_mounts != prior["mounts"]
        or any(identities[name] != prior[name] for name in identities)
    ):
        raise ValueError("terminal Docker facts or mount identities changed")
    launches = sum(
        1
        for line in _run(
            "docker",
            "events",
            "--since",
            prior["since"],
            "--until",
            str(int(time.time()) + 1),
            "--filter",
            f"container={inspected['Id']}",
            "--filter",
            "event=start",
            "--format",
            "{{.ID}}",
        ).splitlines()
        if line.strip() == inspected["Id"].encode()
    )
    root = Path(prior["cgroup_id"])
    processes = [
        int(line) for line in _read(root / "cgroup.procs").splitlines() if line
    ]
    if launches != 1 or processes:
        raise ValueError("launch count or terminal cgroup invalid")
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
        "memory_peak_bytes": int(_read(root / "memory.peak").strip()),
        "pids_peak": int(_read(root / "pids.peak").strip()),
    }
    plan = strict_json_loads(_read(Path(mounts["/plan/cell-plan.json"]["Source"])))
    if resources["wall_ns"] > plan["wall_timeout_seconds"] * 1_000_000_000:
        raise TimeoutError("producer Docker wall deadline exceeded")
    return {
        "producer_container_id": inspected["Id"],
        "image_digest": prior["image_digest"],
        "actual_image_id": inspected["Image"],
        "cgroup_id": prior["cgroup_id"],
        "network_mode": "none",
        "security_opt": ["no-new-privileges", "seccomp=" + prior["seccomp_sha256"]],
        "restart_count": 0,
        "terminal_pid": 0,
        "launch_count": 1,
        "cgroup_processes_after_stop": [],
        "pid1_exit": 0,
        "run_nonce": prior["run_nonce"],
        "launch_token_sha256": hashlib.sha256(launch_payload).hexdigest(),
        "container_user": security["user"],
        "readonly_rootfs": security["readonly_rootfs"],
        "cap_drop": security["cap_drop"],
        "mounts": prior["mounts"],
        "resource_limits": {
            k: security[k] for k in ("pids_limit", "memory", "nano_cpus")
        },
        "tmpfs": security["tmpfs"],
        "resource_observations": resources,
        "cell": prior["cell"],
        "plan": prior["plan"],
        "source": prior["source"],
        "output": prior["output"],
        "terminal": {
            "finished_at": state["FinishedAt"],
            "started_at": state["StartedAt"],
            "exit_code": state["ExitCode"],
        },
        "data_image": _identity(data_image, digest=True),
        "hash_image": _identity(hash_image, digest=True),
        "seccomp_sha256": hashlib.sha256(_read(seccomp)).hexdigest(),
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
        own["Image"] != config["trusted"]["image_ids"]["auditor"]
        or own["Config"]["Image"].split("@")[-1] != expected["image_digest"]
        or interpreter != expected["interpreter_sha256"]
        or module != expected["module_sha256"]
    ):
        raise ValueError("unauthorized host-auditor image or executable bytes")
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="phase", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--seccomp", required=True)
    common.add_argument("--expected-image", required=True)
    common.add_argument("--authority-socket", required=True)
    common.add_argument("--public-config", required=True)
    launch_parser = sub.add_parser("launch", parents=[common])
    launch_parser.add_argument("--container", required=True)
    launch_parser.add_argument("--since", required=True)
    launch_parser.add_argument("--run-nonce", required=True)
    terminal_parser = sub.add_parser("terminal", parents=[common])
    terminal_parser.add_argument("--launch-token", required=True)
    terminal_parser.add_argument("--data-image", required=True)
    terminal_parser.add_argument("--hash-image", required=True)
    args = parser.parse_args(argv)
    config = _authorize_runtime(Path(args.public_config))
    if args.expected_image.split("@")[-1] != config["trusted"]["images"]["producer"]:
        raise ValueError("producer image is not root-authorized")
    authority = config["auditor"]
    if authority["protocol"] != PROTOCOL:
        raise ValueError("audit authority protocol mismatch")
    if args.phase == "launch":
        audit = launch(
            args.container,
            args.expected_image,
            Path(args.seccomp),
            args.since,
            args.run_nonce,
            config,
        )
        result = _authority(
            _request("launch", audit, authority),
            Path(args.authority_socket),
            authority,
            LAUNCH_DOMAIN,
        )
    else:
        audit = terminal(
            _read(Path(args.launch_token)),
            Path(args.seccomp),
            args.expected_image,
            Path(args.data_image),
            Path(args.hash_image),
            config,
        )
        result = _authority(
            _request("terminal", audit, authority),
            Path(args.authority_socket),
            authority,
            DOMAIN,
        )
    sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
