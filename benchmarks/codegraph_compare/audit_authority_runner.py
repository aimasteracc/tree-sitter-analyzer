"""Privileged execution half of the NO1-008A run-cell authority."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import stat
import subprocess
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare.audit_authority_storage import (
    _fsync_directory,
    _materialize_source,
    _producer_mount_targets,
    _read,
    _secure_directory,
    _sha,
    _source_archive_ceiling,
)
from benchmarks.codegraph_compare.host_auditor import (
    LAUNCH_DOMAIN,
    _request,
    launch,
    terminal,
)
from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    canonical_plan_hash,
    strict_json_loads,
)
from benchmarks.codegraph_compare.setup_qualification_paths import _hash_tree
from benchmarks.codegraph_compare.verifier import parse_public_config


def _run(*args: str, timeout: int = 120) -> bytes:
    """Run every unit of authority work in a killable process group."""
    process = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        os.killpg(process.pid, 9)
        process.communicate()
        raise TimeoutError(f"authority command deadline expired: {args[0]}") from None
    if process.returncode:
        raise ValueError(f"authority command failed: {args[0]}: {stderr[:200]!r}")
    return stdout


def _wait_container(container: str, deadline: float) -> str:
    """Wait only until the producer wall deadline; Docker RPC cleanup is separate."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("producer Docker wall deadline expired")
    process = subprocess.Popen(
        ["docker", "wait", container],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=remaining)
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["docker", "kill", container],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
        process.communicate(timeout=30)
        raise TimeoutError("producer Docker wall deadline expired") from None
    if process.returncode:
        raise ValueError(f"authority command failed: docker wait: {stderr[:200]!r}")
    return stdout.decode().strip()


def _docker_wall_deadline(started_at: str, wall_timeout: int) -> float:
    from datetime import datetime

    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    elapsed = time.time() - started.timestamp()
    return time.monotonic() + max(0.0, wall_timeout - elapsed)


def _validate_producer_output(output: Path) -> Path:
    entries = list(os.scandir(output))
    if (
        len(entries) != 1
        or entries[0].name != "core"
        or not entries[0].is_dir(follow_symlinks=False)
    ):
        raise ValueError("producer output must contain exactly one real core directory")
    core = output / "core"
    seen: set[tuple[int, int]] = set()
    for current, directories, files in os.walk(core, followlinks=False):
        for name in directories + files:
            path = Path(current) / name
            metadata = os.lstat(path)
            if stat.S_ISLNK(metadata.st_mode) or not (
                stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)
            ):
                raise ValueError("producer core contains symlink or special entry")
            identity = (metadata.st_dev, metadata.st_ino)
            if identity in seen or (
                stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1
            ):
                raise ValueError("producer core contains hard-linked entry")
            seen.add(identity)
    return core


def _seal_tree(root: Path) -> None:
    for _current, directories, files, directory_fd in os.fwalk(
        root, topdown=False, follow_symlinks=False
    ):
        for name in files:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("sealed core leaf changed type")
            os.chown(name, 0, 0, dir_fd=directory_fd, follow_symlinks=False)
            os.chmod(name, 0o444, dir_fd=directory_fd, follow_symlinks=False)
        for name in directories:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("sealed core directory changed type")
            os.chown(name, 0, 0, dir_fd=directory_fd, follow_symlinks=False)
            os.chmod(name, 0o555, dir_fd=directory_fd, follow_symlinks=False)  # nosec B103
    os.chown(root, 0, 0, follow_symlinks=False)
    os.chmod(root, 0o555, follow_symlinks=False)  # nosec B103


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
        self._semaphore = threading.BoundedSemaphore(1)
        self._lock_path = self._artifacts / ".authority.lock"
        descriptor = os.open(
            self._lock_path,
            os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != 0
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
            ):
                raise ValueError("authority global lock is not protected")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(self._artifacts)

    @contextmanager
    def _exclusive_execution(self) -> Iterator[None]:
        with self._semaphore:
            descriptor = os.open(
                self._lock_path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
            )
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

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
        hostname = os.environ.get("HOSTNAME", "")
        inspected = json.loads(_run("docker", "inspect", hostname))
        own = inspected[0] if type(inspected) is list and len(inspected) == 1 else {}
        mounts = own.get("Mounts", [])
        if (
            own.get("Image") != runtime["image_id"]
            or own.get("Image") != config["trusted"]["image_ids"]["auditor"]
            or own.get("Config", {}).get("Image", "").split("@")[-1]
            != runtime["image_digest"]
            or own.get("Config", {})
            .get("Labels", {})
            .get("org.tree-sitter-analyzer.no1-008a.closure-sha256")
            != runtime["closure_manifest_sha256"]
            or own.get("HostConfig", {}).get("ReadonlyRootfs") is not True
            or any(
                mount.get("Destination", "").startswith(
                    ("/opt/tsa", "/usr/local/lib/python")
                )
                for mount in mounts
            )
        ):
            raise ValueError("authority immutable image closure is not root-authorized")
        return job, declared, config

    def _verify_staged(
        self, job: Path, contract: Mapping[str, Any], config: Mapping[str, Any]
    ) -> int:
        cell = contract["cell"]
        identity = f"{cell['repo_id']}/{cell['arm_id']}"
        plan = strict_json_loads(_read(job / "plan.json"))
        plan_cell = plan.get("cell")
        if type(plan_cell) is not dict or any(
            plan_cell.get(name) != cell[name] for name in cell
        ):
            raise ValueError("staged plan cell mismatch")
        logical_hash = canonical_plan_hash(plan)
        if (
            plan.get("plan_hash") != logical_hash
            or logical_hash != config["trusted"]["plan_hashes"][identity]
        ):
            raise ValueError("root-authorized canonical plan hash mismatch")
        checks = {
            "plan.json": config["trusted"]["plan_document_sha256"][identity],
            "inventory.json": config["trusted"]["inventory_sha256"][cell["repo_id"]],
            "tool": config["trusted"]["tool_sha256"],
            "config": config["trusted"]["config_sha256"],
            "seccomp": config["trusted"]["seccomp_sha256"],
        }
        for name, expected in checks.items():
            staged = job / name
            metadata = os.lstat(staged)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != 0
                or stat.S_IMODE(metadata.st_mode) & 0o022
                or metadata.st_nlink != 1
            ):
                raise ValueError(
                    f"staged input is not immutable root-owned regular: {name}"
                )
            if _sha(staged) != expected:
                raise ValueError(f"root-authorized staged hash mismatch: {name}")
        inventory_payload = _read(job / "inventory.json")
        archive_ceiling = _source_archive_ceiling(inventory_payload)
        snapshot = job / "source-snapshot.tar"
        metadata = os.lstat(snapshot)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or metadata.st_nlink != 1
        ):
            raise ValueError(
                "staged input is not immutable root-owned regular: source-snapshot.tar"
            )
        if (
            _sha(snapshot, limit=archive_ceiling)
            != config["trusted"]["source_snapshot_sha256"][cell["repo_id"]]
        ):
            raise ValueError(
                "root-authorized staged hash mismatch: source-snapshot.tar"
            )
        wall_timeout = plan.get("wall_timeout_seconds")
        if type(wall_timeout) is not int or wall_timeout < 1 or wall_timeout > 86400:
            raise ValueError("staged plan timeout invalid")
        # The seccomp statement is intentionally an authority-code attestation of
        # the exact staged bytes passed to Docker, not a daemon-returned digest.
        return wall_timeout

    def _execute(self, contract: Mapping[str, Any]) -> Mapping[str, Any]:
        job, declared, config = self._inputs(contract)
        wall_timeout = self._verify_staged(job, contract, config)
        plan = strict_json_loads(_read(job / "plan.json"))
        source_target, tool_target, config_target = _producer_mount_targets(plan)
        image = declared["producer_image"]
        if image.split("@")[-1] != config["trusted"]["images"]["producer"]:
            raise ValueError("producer launch reference is not root-authorized")
        destination = self._artifacts / contract["job_id"]
        _secure_directory(destination, fresh=True)
        source = destination / "source"
        archive_ceiling = _source_archive_ceiling(_read(job / "inventory.json"))
        _materialize_source(
            job / "source-snapshot.tar", source, ceiling=archive_ceiling
        )
        output = destination / "producer-output"
        output.mkdir(mode=0o700)
        os.chown(output, 65532, 65532)
        cgroup_name = f"no1-008a-{contract['job_id']}"
        docker_info = json.loads(_run("docker", "info", "--format", "{{json .}}"))
        if (
            docker_info.get("CgroupVersion") != "2"
            or docker_info.get("CgroupDriver") != "cgroupfs"
        ):
            raise ValueError(
                "authority supports only preflighted cgroup-v2 cgroupfs Docker"
            )
        cgroup_root = Path("/sys/fs/cgroup")
        controllers = set(_read(cgroup_root / "cgroup.controllers").decode().split())
        if not {"cpu", "memory", "pids", "io"}.issubset(controllers):
            raise ValueError("required cgroup-v2 controllers are unavailable")
        cgroup = cgroup_root / cgroup_name
        cgroup.mkdir(mode=0o755)
        name = f"no1-008a-{contract['job_id'][:24]}"
        since = str(int(time.time()))
        mounts = [
            (source, source_target, True),
            (job / "tool", tool_target, True),
            (job / "config", config_target, True),
            (job / "seccomp", "/plan/seccomp.json", True),
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
            f"/{cgroup_name}",
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
            producer_deadline = _docker_wall_deadline(
                inspected["State"]["StartedAt"], wall_timeout
            )
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
            exit_code = _wait_container(container, producer_deadline)
            if exit_code != "0":
                raise ValueError("producer did not exit zero")
            os.chown(output, 0, 0)
            os.chmod(output, 0o500)
            _cgroup_empty(Path(launched["cgroup_id"]))
            core = _validate_producer_output(output)
            _seal_tree(core)
            os.chown(output, 0, 0, follow_symlinks=False)
            os.chmod(output, 0o555, follow_symlinks=False)  # nosec B103
            data = destination / "data.img"
            hashes = destination / "hash.img"
            _run("truncate", "-s", "1G", str(data))
            _run("mkfs.ext4", "-q", "-d", str(core), str(data))
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
            process["plan"]["canonical_sha256"] = canonical_plan_hash(
                strict_json_loads(_read(job / "plan.json"))
            )
            process.update(
                launch_pid=pid,
                launch_starttime=starttime,
                launch_pidfd_opened=True,
                cgroup_populated=0,
                cgroup_subtree_populated=[],
                launch_token=launch_envelope,
                core_tree_sha256=_hash_tree(core),
                source_snapshot_sha256=_sha(
                    job / "source-snapshot.tar", limit=archive_ceiling
                ),
                tool_sha256=_sha(job / "tool"),
                config_sha256=_sha(job / "config"),
            )
            audit = _request("terminal", process, config["auditor"])
            (destination / "verity-format.txt").write_bytes(format_output)
            for path in (data, hashes, launch_path, destination / "verity-format.txt"):
                metadata = os.lstat(path)
                if not stat.S_ISREG(metadata.st_mode):
                    raise ValueError("authority artifact changed type before sealing")
                os.chown(path, 0, 0, follow_symlinks=False)
                os.chmod(path, 0o444, follow_symlinks=False)
            os.chmod(destination, 0o555)  # nosec B103
            refs = {
                name: str(destination / name)
                for name in (
                    "data.img",
                    "hash.img",
                    "launch-audit.json",
                    "verity-format.txt",
                )
            }
            return {"audit": audit, "artifacts": refs}
        finally:
            if pidfd_descriptor >= 0:
                os.close(pidfd_descriptor)
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            try:
                cgroup.rmdir()
            except OSError:
                pass

    def __call__(self, contract: Mapping[str, Any]) -> Mapping[str, Any]:
        with self._exclusive_execution():
            job_id = contract.get("job_id")
            if type(job_id) is not str or len(job_id) != 64:
                raise ValueError("job id invalid before one-shot reservation")
            state = self._artifacts / f"{job_id}.state"
            descriptor = os.open(
                state, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400
            )
            try:
                os.write(descriptor, b"RUNNING\n")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            _fsync_directory(self._artifacts)
            try:
                result = self._execute(contract)
            except Exception as error:
                destination = self._artifacts / job_id
                if destination.exists():
                    shutil.rmtree(destination)
                self._terminal_state(
                    job_id, state, f"FAILED:{type(error).__name__}\n".encode("ascii")
                )
                raise
            self._terminal_state(job_id, state, b"SUCCESS\n")
            return result

    def _terminal_state(self, job_id: str, state: Path, payload: bytes) -> None:
        temporary = self._artifacts / f".{job_id}.state.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o400,
        )
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, state)
        _fsync_directory(self._artifacts)
