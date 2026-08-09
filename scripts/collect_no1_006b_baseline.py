#!/usr/bin/env python3
"""Collect the bounded, offline NO1-006B dependency/startup E0 baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import select
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_COMMIT = "7e0e8f6e03270fcbf4025d717415ef69c9354145"
ROOT_NAME = "tree-sitter-analyzer"
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "no1-006b-baseline", "version": "1"},
    },
}


def run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, capture_output=True, text=True, check=True, timeout=timeout
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def distribution_inventory(python: Path) -> dict[str, Any]:
    code = r"""import importlib.metadata as m, json
import re, sys
root=m.distribution("tree-sitter-analyzer"); direct=[]
for value in root.requires or []:
 if "extra ==" in value: continue
 if "python_version < '3.11'" in value and sys.version_info >= (3, 11): continue
 match=re.match(r"[A-Za-z0-9_.-]+", value)
 if match: direct.append(match.group(0).lower().replace("_", "-"))
seen=set(); total=0
for dist in m.distributions():
 name=(dist.metadata.get("Name") or "").lower().replace("_", "-")
 if not name or name in seen: continue
 seen.add(name)
 for file in dist.files or []:
  path=dist.locate_file(file)
  try:
   if path.is_file() and path.suffix != ".pyc" and path.name != "direct_url.json": total += path.stat().st_size
  except OSError: pass
print(json.dumps({"direct_names":sorted(set(direct)),"installed_names":sorted(seen),"installed_size_bytes":total}))"""
    return json.loads(run([str(python), "-c", code]).stdout)


def cli_sample(executable: Path) -> float:
    started = time.perf_counter_ns()
    subprocess.run(
        [str(executable), "--show-supported-languages"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=30,
    )
    return round((time.perf_counter_ns() - started) / 1_000_000, 3)


def mcp_sample(executable: Path, project_root: Path) -> float:
    process = subprocess.Popen(
        [str(executable), "--project-root", str(project_root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    started = time.perf_counter_ns()
    try:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(INITIALIZE, separators=(",", ":")) + "\n")
        process.stdin.flush()
        ready, _, _ = select.select([process.stdout], [], [], 30)
        if not ready:
            raise TimeoutError("MCP initialize response exceeded 30 seconds")
        response = json.loads(process.stdout.readline())
        if response.get("id") != 1 or "result" not in response:
            raise RuntimeError("MCP initialize did not return a successful response")
        return round((time.perf_counter_ns() - started) / 1_000_000, 3)
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def canonical_hash(report: dict[str, Any]) -> str:
    body = dict(report)
    body.pop("report_sha256", None)
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def collect(
    repo: Path, output: Path, repeats: int, expected_commit: str
) -> dict[str, Any]:
    if platform.system() != "Darwin":
        raise RuntimeError("this E0 collector is qualified only for the macOS axis")
    if repeats not in range(3, 21):
        raise ValueError("repeats must be between 3 and 20")
    commit = run(["git", "-C", str(repo), "rev-parse", "HEAD"]).stdout.strip()
    if commit != expected_commit:
        raise RuntimeError(f"expected commit {expected_commit}, found {commit}")
    with tempfile.TemporaryDirectory(prefix="no1-006b-") as temporary:
        temp = Path(temporary)
        dist = temp / "dist"
        venv = temp / "venv"
        build_command = ["uv", "build", "--wheel", "--offline", "--out-dir", str(dist)]
        run(build_command, timeout=180)
        wheel = next(dist.glob("*.whl"))
        run(
            [
                "uv",
                "venv",
                str(venv),
                "--python",
                os.environ.get("NO1_006B_PYTHON", "3.14"),
                "--offline",
            ],
            timeout=120,
        )
        python = venv / "bin" / "python"
        run(
            ["uv", "pip", "install", "--python", str(python), "--offline", str(wheel)],
            timeout=180,
        )
        inventory = distribution_inventory(python)
        cli_samples = [
            cli_sample(venv / "bin" / "tree-sitter-analyzer")
            for _ in range(repeats + 1)
        ]
        mcp_samples = [
            mcp_sample(venv / "bin" / "tree-sitter-analyzer-mcp", repo)
            for _ in range(repeats + 1)
        ]
        py = json.loads(
            run(
                [
                    str(python),
                    "-c",
                    "import json,platform,sys;print(json.dumps({'version':platform.python_version(),'implementation':platform.python_implementation(),'executable':sys.executable}))",
                ]
            ).stdout
        )
        wheel_size = wheel.stat().st_size
        report: dict[str, Any] = {
            "schema_version": 1,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "roadmap_id": "NO1-006B",
            "evidence_level": "E0",
            "source": {
                "commit": commit,
                "wheel_filename": wheel.name,
                "wheel_sha256": sha256(wheel),
                "wheel_size_bytes": wheel_size,
            },
            "environment": {
                "os": platform.platform(),
                "system": "macos",
                "machine": platform.machine(),
                "python": {**py, "executable": "<temp>/venv/bin/python"},
                "uv": run(["uv", "--version"]).stdout.strip(),
                "network_policy": "uv --offline; no network measurement",
            },
            "commands": {
                "build": [
                    "uv",
                    "build",
                    "--wheel",
                    "--offline",
                    "--out-dir",
                    "<temp>/dist",
                ],
                "install": [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    "<temp>/venv/bin/python",
                    "--offline",
                    "<built-wheel>",
                ],
                "cli_probe": ["tree-sitter-analyzer", "--show-supported-languages"],
                "mcp_probe": [
                    "tree-sitter-analyzer-mcp",
                    "--project-root",
                    str(repo),
                    "<initialize JSON-RPC>",
                ],
            },
            "measurements": {
                "download_size_bytes": wheel_size,
                "download_scope": "root wheel artifact only; dependency transfer is unknown offline",
                "installed_size_bytes": inventory["installed_size_bytes"],
                "installed_size_scope": "unique non-pyc, non-direct_url regular files listed by installed distribution metadata; interpreter excluded",
                "direct_dependency_count": len(inventory["direct_names"]),
                "transitive_dependency_count": len(
                    set(inventory["installed_names"])
                    - {ROOT_NAME}
                    - set(inventory["direct_names"])
                ),
                "installed_distribution_count": len(inventory["installed_names"]),
                "direct_dependency_names": inventory["direct_names"],
                "cli_startup": {
                    "definition": "process start to successful --show-supported-languages exit",
                    "cold_ms": cli_samples[0],
                    "warm_ms": cli_samples[1:],
                },
                "mcp_startup": {
                    "definition": "process start to successful initialize JSON-RPC response",
                    "cold_ms": mcp_samples[0],
                    "warm_ms": mcp_samples[1:],
                },
            },
            "repeats": repeats,
            "platform_axes": {
                "macos": "measured_e0",
                "linux": "unknown",
                "windows": "unknown",
            },
        }
        report["report_sha256"] = canonical_hash(report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--expected-commit", default=EXPECTED_COMMIT)
    args = parser.parse_args()
    collect(
        args.repo.resolve(), args.output.resolve(), args.repeats, args.expected_commit
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
