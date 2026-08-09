"""Privileged execution half of the NO1-008A run-cell authority."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare.host_auditor import (
    LAUNCH_DOMAIN,
    _request,
    launch,
    terminal,
)
from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)
from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree
from benchmarks.codegraph_compare.verifier import parse_public_config


def _run(*args: str, timeout: int = 120) -> bytes:
    result = subprocess.run(
        args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout
    )
    if result.returncode:
        raise ValueError(
            f"authority command failed: {args[0]}: {result.stderr[:200]!r}"
        )
    return result.stdout


def _read(path: Path, limit: int = 16 * 1024 * 1024) -> bytes:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("staged input is not regular")
        payload = bytearray()
        while chunk := os.read(descriptor, 1024 * 1024):
            payload.extend(chunk)
            if len(payload) > limit:
                raise ValueError("staged input exceeds bound")
        return bytes(payload)
    finally:
        os.close(descriptor)


def _sha(path: Path) -> str:
    return hashlib.sha256(_read(path)).hexdigest()


def _secure_directory(path: Path, *, fresh: bool = False) -> None:
    if fresh:
        path.mkdir(mode=0o700)
    resolved = path.resolve(strict=True)
    metadata = os.stat(resolved)
    if (
        resolved != path
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise ValueError("authority directory is not root-controlled")


def _cgroup_empty(root: Path) -> list[str]:
    populated: list[str] = []
    for current, directories, _files in os.walk(root, followlinks=False):
        directories.sort()
        events = dict(
            line.split()
            for line in _read(Path(current) / "cgroup.events").decode().splitlines()
        )
        if events.get("populated") != "0":
            populated.append(current)
    if populated:
        raise ValueError("producer cgroup subtree remains populated")
    return populated


def _pid_identity(pid: int) -> tuple[str, int]:
    raw = _read(Path(f"/proc/{pid}/stat")).decode()
    if ")" not in raw:
        raise ValueError("launch process stat is incomplete")
    fields = raw.rsplit(")", 1)[1].split()
    if len(fields) < 20:
        raise ValueError("launch process stat is incomplete")
    pidfd_open = getattr(os, "pidfd_open", None)
    if pidfd_open is None:
        raise ValueError("pidfd_open is required for authority launch identity")
    descriptor = pidfd_open(pid)
    return fields[19], descriptor


class AuthorityRunner:
    """Runs only pre-staged, root-authorized jobs and seals their outputs."""

    def __init__(self, staged_root: Path, artifact_root: Path, key: Ed25519PrivateKey):
        self._staged = staged_root.resolve(strict=True)
        self._artifacts = artifact_root.resolve(strict=True)
        _secure_directory(self._staged)
        _secure_directory(self._artifacts)
        self._key = key

    def _inputs(
        self, contract: Mapping[str, Any]
    ) -> tuple[Path, Mapping[str, Any], dict[str, Any]]:
        job = self._staged / contract["job_id"]
        _secure_directory(job)
        declared = strict_json_loads(_read(job / "authority-job.json"))
        expected = frozenset({"job_id", "cell", "nonce", "producer_image"})
        if type(declared) is not dict or frozenset(declared) != expected:
            raise ValueError("authority job declaration is not closed")
        if any(
            declared[name] != contract[name] for name in ("job_id", "cell", "nonce")
        ):
            raise ValueError("staged job does not match root contract")
        config = parse_public_config(_read(job / "public-config.json"))
        runtime = config["trusted"]["auditor_runtime"]
        own_module = hashlib.sha256(_read(Path(__file__))).hexdigest()
        interpreter = hashlib.sha256(
            _read(Path(os.path.realpath(sys.executable)))
        ).hexdigest()
        if (
            own_module != runtime["module_sha256"]
            or interpreter != runtime["interpreter_sha256"]
            or own_module != config["auditor"]["service_measurement"]
        ):
            raise ValueError("authority executable measurement is not root-authorized")
        hostname = os.environ.get("HOSTNAME", "")
        inspected = json.loads(_run("docker", "inspect", hostname))
        if (
            type(inspected) is not list
            or len(inspected) != 1
            or inspected[0].get("Image") != config["trusted"]["image_ids"]["auditor"]
            or inspected[0].get("Config", {}).get("Image", "").split("@")[-1]
            != runtime["image_digest"]
        ):
            raise ValueError(
                "authority service image measurement is not root-authorized"
            )
        return job, declared, config

    def _verify_staged(
        self, job: Path, contract: Mapping[str, Any], config: Mapping[str, Any]
    ) -> None:
        cell = contract["cell"]
        identity = f"{cell['repo_id']}/{cell['arm_id']}"
        plan = strict_json_loads(_read(job / "plan.json"))
        plan_cell = plan.get("cell")
        if type(plan_cell) is not dict or any(
            plan_cell.get(name) != cell[name] for name in cell
        ):
            raise ValueError("staged plan cell mismatch")
        checks = {
            "plan.json": config["trusted"]["plan_hashes"][identity],
            "inventory.json": config["trusted"]["inventory_sha256"][cell["repo_id"]],
            "source-snapshot.tar": config["trusted"]["source_snapshot_sha256"][
                cell["repo_id"]
            ],
            "tool": config["trusted"]["tool_sha256"],
            "config": config["trusted"]["config_sha256"],
            "seccomp": config["trusted"]["seccomp_sha256"],
        }
        for name, expected in checks.items():
            if _sha(job / name) != expected:
                raise ValueError(f"root-authorized staged hash mismatch: {name}")
        # The seccomp statement is intentionally an authority-code attestation of
        # the exact staged bytes passed to Docker, not a daemon-returned digest.

    def __call__(self, contract: Mapping[str, Any]) -> Mapping[str, Any]:
        job, declared, config = self._inputs(contract)
        self._verify_staged(job, contract, config)
        image = declared["producer_image"]
        if image.split("@")[-1] != config["trusted"]["images"]["producer"]:
            raise ValueError("producer launch reference is not root-authorized")
        destination = self._artifacts / contract["job_id"]
        _secure_directory(destination, fresh=True)
        output = destination / "producer-output"
        output.mkdir(mode=0o700)
        os.chown(output, 65532, 65532)
        cgroup = Path("/sys/fs/cgroup") / f"no1-008a-{contract['job_id']}"
        cgroup.mkdir(mode=0o755)
        name = f"no1-008a-{contract['job_id'][:24]}"
        since = str(int(time.time()))
        mounts = [
            (job / "source", "/source", True),
            (job / "plan.json", "/plan/cell-plan.json", True),
            (job / "inventory.json", "/plan/inventory.json", True),
            (output, "/out", False),
        ]
        command = [
            "docker",
            "create",
            "--name",
            name,
            "--cgroup-parent",
            str(cgroup),
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--security-opt",
            f"seccomp={job / 'seccomp'}",
            "--user",
            "65532:65532",
            "--pids-limit",
            "64",
            "--memory",
            "4g",
            "--cpus",
            "1",
            "--tmpfs",
            f"{Path('/') / 'tmp'}:rw,noexec,nosuid,nodev,size=64m",
        ]
        for source, target, readonly in mounts:
            suffix = ",readonly,bind-propagation=rprivate" if readonly else ""
            command += ["--mount", f"type=bind,src={source},dst={target}{suffix}"]
        container = (
            _run(
                *(command + [image, "--plan", "/plan/cell-plan.json", "--out", "/out"])
            )
            .decode()
            .strip()
        )
        pidfd_descriptor = -1
        try:
            _run("docker", "start", container)
            inspected = json.loads(_run("docker", "inspect", container))[0]
            pid = inspected["State"]["Pid"]
            starttime, pidfd_descriptor = _pid_identity(pid)
            launched = launch(
                container, image, job / "seccomp", since, contract["nonce"], config
            )
            if launched["launch_pid"] != pid:
                raise ValueError("Docker launch PID changed during pidfd capture")
            launched.update(launch_starttime=starttime, launch_pidfd_opened=True)
            launch_request = _request("launch", launched, config["auditor"])
            launch_envelope = {
                "audit": launch_request,
                "key_id": config["auditor"]["key_id"],
                "algorithm": "Ed25519",
                "signature": self._key.sign(
                    LAUNCH_DOMAIN + canonical_json_bytes(launch_request)
                ).hex(),
            }
            launch_path = destination / "launch-audit.json"
            launch_path.write_bytes(canonical_json_bytes(launch_envelope))
            exit_code = _run("docker", "wait", container).decode().strip()
            if exit_code != "0":
                raise ValueError("producer did not exit zero")
            os.chown(output, 0, 0)
            os.chmod(output, 0o500)
            _cgroup_empty(Path(launched["cgroup_id"]))
            data = destination / "data.img"
            hashes = destination / "hash.img"
            _run("truncate", "-s", "1G", str(data))
            _run("mkfs.ext4", "-q", "-d", str(output / "core"), str(data))
            _run("truncate", "-s", "256M", str(hashes))
            format_output = _run(
                "veritysetup", "format", str(data), str(hashes), "--hash", "sha256"
            )
            process = terminal(
                canonical_json_bytes(launch_envelope),
                job / "seccomp",
                image,
                data,
                hashes,
                config,
            )
            process.update(
                launch_pid=pid,
                launch_starttime=starttime,
                launch_pidfd_opened=True,
                cgroup_populated=0,
                cgroup_subtree_populated=[],
                launch_token=launch_envelope,
                core_tree_sha256=_hash_tree(output / "core"),
                source_snapshot_sha256=_sha(job / "source-snapshot.tar"),
                tool_sha256=_sha(job / "tool"),
                config_sha256=_sha(job / "config"),
            )
            audit = _request("terminal", process, config["auditor"])
            (destination / "verity-format.txt").write_bytes(format_output)
            for path in destination.rglob("*"):
                if path.is_file():
                    os.chown(path, 0, 0)
                    os.chmod(path, 0o444)
            os.chmod(destination, 0o500)
            refs = {
                name: str(destination / name)
                for name in (
                    "data.img",
                    "hash.img",
                    "launch-audit.json",
                    "verity-format.txt",
                )
            }
            refs["core"] = str(output / "core")
            return {"audit": audit, "artifacts": refs}
        finally:
            if pidfd_descriptor >= 0:
                os.close(pidfd_descriptor)
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
