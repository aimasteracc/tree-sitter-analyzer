"""Independent signed host launch auditor for NO1-008A."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

DOMAIN = b"NO1-008A-HOST-AUDIT-V1\0"


def _run(*args: str) -> bytes:
    result = subprocess.run(
        args, stdin=subprocess.DEVNULL, capture_output=True, check=False, timeout=30
    )
    if result.returncode:
        raise ValueError(f"host observation failed: {args[1]}")
    return result.stdout


def audit(
    container: str,
    cgroup_procs: Path,
    seccomp: Path,
    expected_image: str,
    since: str,
    run_nonce: str,
) -> dict[str, object]:
    inspected = json.loads(_run("docker", "inspect", container))[0]
    state = inspected["State"]
    host = inspected["HostConfig"]
    configured_image = inspected["Config"]["Image"]
    if configured_image != expected_image:
        raise ValueError("docker inspect configured producer image differs")
    actual = expected_image.split("@")[-1].removeprefix("sha256:")
    security = []
    for value in host["SecurityOpt"]:
        security.append(
            "seccomp=" + hashlib.sha256(seccomp.read_bytes()).hexdigest()
            if value.startswith("seccomp=")
            else value
        )
    launches = sum(
        1
        for line in _run(
            "docker",
            "events",
            "--since",
            since,
            "--until",
            str(int(__import__("time").time()) + 1),
            "--filter",
            f"container={container}",
            "--filter",
            "event=start",
            "--format",
            "{{.ID}}",
        ).splitlines()
        if line.strip()
    )
    processes = [int(line) for line in cgroup_procs.read_text().splitlines() if line]
    root = cgroup_procs.parent

    def scalar(name: str) -> int:
        return int((root / name).read_text().strip())

    cpu = dict(line.split() for line in (root / "cpu.stat").read_text().splitlines())
    io_bytes = sum(
        int(field.split("=")[1])
        for line in (root / "io.stat").read_text().splitlines()
        for field in line.split()[1:]
        if field.startswith(("rbytes=", "wbytes="))
    )
    from datetime import datetime

    def parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    wall_ns = int(
        (parse(state["FinishedAt"]) - parse(state["StartedAt"])).total_seconds()
        * 1_000_000_000
    )
    resources = {
        "wall_ns": wall_ns,
        "cpu_usec": int(cpu["usage_usec"]),
        "io_bytes": io_bytes,
        "memory_peak_bytes": scalar("memory.peak"),
        "pids_peak": scalar("pids.peak"),
    }
    return {
        "producer_container_id": inspected["Id"],
        "image_digest": "sha256:" + actual,
        "cgroup_id": str(cgroup_procs.parent),
        "network_mode": host["NetworkMode"],
        "security_opt": security,
        "restart_count": state["RestartCount"],
        "terminal_pid": state["Pid"],
        "launch_count": launches,
        "cgroup_processes_after_stop": processes,
        "pid1_exit": state["ExitCode"],
        "run_nonce": run_nonce,
        "resource_observations": resources,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--container", required=True)
    p.add_argument("--cgroup-procs", required=True)
    p.add_argument("--seccomp", required=True)
    p.add_argument("--expected-image", required=True)
    p.add_argument("--since", required=True)
    p.add_argument("--run-nonce", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--key-id", required=True)
    a = p.parse_args(argv)
    key = Path(a.private_key)
    st = key.stat()
    if (
        not stat.S_ISREG(st.st_mode)
        or stat.S_IMODE(st.st_mode) != 0o400
        or st.st_uid != 0
    ):
        raise ValueError("auditor key permissions invalid")
    raw = key.read_bytes()
    if len(raw) != 32:
        raise ValueError("auditor key length invalid")
    facts = audit(
        a.container,
        Path(a.cgroup_procs),
        Path(a.seccomp),
        a.expected_image,
        a.since,
        a.run_nonce,
    )
    signature = (
        Ed25519PrivateKey.from_private_bytes(raw)
        .sign(DOMAIN + canonical_json_bytes(facts))
        .hex()
    )
    sys.stdout.buffer.write(
        canonical_json_bytes(
            {
                "audit": facts,
                "key_id": a.key_id,
                "algorithm": "Ed25519",
                "signature": signature,
            }
        )
        + b"\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
