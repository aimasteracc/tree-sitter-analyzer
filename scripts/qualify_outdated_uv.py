#!/usr/bin/env python3
"""Native outdated-uv qualification bound to NO1-006A package evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "no1-006a-outdated-uv-attestation-v1"
AXES = ("linux", "macos", "windows")
OLD_VERSION = "0.10.9"
OLD_SOURCE = "https://github.com/astral-sh/uv/releases/tag/0.10.9"
MINIMUM_VERSION = (0, 11, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identity(job: str) -> tuple[dict[str, Any], dict[str, str]]:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "local/unknown")
    run_id = os.environ.get("GITHUB_RUN_ID", "0")
    source = {
        "repository": repo,
        "commit": os.environ.get("GITHUB_SHA", "0" * 40),
        "ref": os.environ.get("GITHUB_REF", "local"),
        "dirty": False,
    }
    workflow = {
        "event": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "run_id": run_id,
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "0"),
        "job": job,
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF", "local"),
        "run_url": f"{server}/{repo}/actions/runs/{run_id}",
    }
    return source, workflow


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", "utf-8")
    os.replace(temporary, path)


def uv_details(executable: Path, expected: str | None = None) -> dict[str, Any]:
    executable = executable.resolve(strict=True)
    if not executable.is_file() or executable.is_symlink():
        raise ValueError("uv must be a regular, non-symlink executable")
    completed = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    match = re.fullmatch(
        r"uv ([0-9]+\.[0-9]+\.[0-9]+)(?:[ \t].*)?\n?", completed.stdout
    )
    if completed.returncode or not match or completed.stderr:
        raise ValueError("uv --version did not produce one valid stdout line")
    version = match.group(1)
    if expected is not None and version != expected:
        raise ValueError(f"expected uv {expected}, observed {version}")
    stat = executable.stat()
    return {
        "version": version,
        "path": str(executable),
        "sha256": sha256(executable),
        "size": stat.st_size,
    }


def package_binding(args: argparse.Namespace) -> dict[str, Any]:
    wheel = Path(args.wheel).resolve(strict=True)
    aggregate_path = Path(args.package_aggregate).resolve(strict=True)
    report_path = Path(args.package_report).resolve(strict=True)
    aggregate = json.loads(aggregate_path.read_text("utf-8"))
    report = json.loads(report_path.read_text("utf-8"))
    wheel_meta = aggregate.get("wheel")
    if not isinstance(wheel_meta, dict):
        raise ValueError("package aggregate has no wheel identity")
    actual = {
        "filename": wheel.name,
        "sha256": sha256(wheel),
        "size": wheel.stat().st_size,
    }
    if any(wheel_meta.get(key) != value for key, value in actual.items()):
        raise ValueError("wheel bytes do not match package aggregate")
    axes = {item.get("axis"): item for item in aggregate.get("axes", [])}
    axis_item = axes.get(args.axis)
    if (
        aggregate.get("kind") != "aggregate"
        or aggregate.get("qualification_id") != "NO1-006A"
        or aggregate.get("evidence_scope") != "native_package_mcp_first_answer"
        or axis_item
        != {"axis": args.axis, "report_sha256": sha256(report_path), "passed": True}
        or report.get("axis") != args.axis
        or report.get("passed") is not True
        or report.get("wheel") != wheel_meta
        or report.get("mcp", {}).get("first_call", {}).get("is_error") is not False
    ):
        raise ValueError(
            "package report is not the exact qualified package-to-MCP axis"
        )
    return {
        "aggregate_sha256": sha256(aggregate_path),
        "axis_report_sha256": sha256(report_path),
        "wheel": wheel_meta,
    }


def base_report(axis: str) -> dict[str, Any]:
    source, workflow = identity("outdated-uv-axis")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "outdated_uv_axis",
        "qualification_id": "NO1-006A",
        "evidence_scope": "native_outdated_uv",
        "axis": axis,
        "qualification_performed": True,
        "passed": False,
        "source": source,
        "workflow": workflow,
        "runner": {
            "declared_axis": axis,
            "observed_system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "image_os": os.environ.get("ImageOS", "unknown"),
            "image_version": os.environ.get("ImageVersion", "unknown"),
        },
        "old_uv": None,
        "installer": None,
        "final_uv": None,
        "package_qualification": None,
        "outcome": None,
        "failure": None,
    }


def run_axis(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    report = base_report(args.axis)
    side = output.parent
    side.mkdir(parents=True, exist_ok=True)
    try:
        expected_system = {"linux": "Linux", "macos": "Darwin", "windows": "Windows"}[
            args.axis
        ]
        if platform.system() != expected_system:
            raise ValueError(
                f"declared {args.axis} axis does not match {platform.system()}"
            )
        old_path = Path(args.uv_executable)
        report["old_uv"] = uv_details(old_path, OLD_VERSION) | {"source": OLD_SOURCE}
        shutil.copyfile(old_path.resolve(), side / "old-uv.bin")
        if tuple(map(int, OLD_VERSION.split("."))) >= MINIMUM_VERSION:
            raise ValueError("fixed uv fixture is not outdated")
        report["package_qualification"] = package_binding(args)
        if args.axis == "windows":
            if Path(args.installer).with_name("install.ps1").exists():
                raise ValueError(
                    "Windows actionable path is stale: install.ps1 now exists"
                )
            action = (
                "Install uv >= 0.11.0 using https://docs.astral.sh/uv/"
                "getting-started/installation/ then re-run the original Tree-sitter Analyzer install command."
            )
            report["installer"] = {
                "supported": False,
                "path": None,
                "sha256": None,
                "exit_code": None,
                "stdout_sha256": None,
                "stderr_sha256": None,
                "detected_outdated": True,
                "action": action,
            }
            report["final_uv"] = None
            report["outcome"] = "actionable"
        else:
            installer = Path(args.installer).resolve(strict=True)
            if installer.name != "install.sh" or installer.is_symlink():
                raise ValueError("native installer must be the regular install.sh")
            with tempfile.TemporaryDirectory(prefix="tsa-outdated-uv-") as temp:
                root = Path(temp)
                fixture, home = root / "fixture", root / "home"
                fixture.mkdir()
                home.mkdir()
                clean = os.environ.copy()
                clean.update(
                    {
                        "HOME": str(home),
                        "PYTHONPATH": "",
                        "PATH": str(old_path.resolve().parent)
                        + os.pathsep
                        + clean.get("PATH", ""),
                    }
                )
                completed = subprocess.run(
                    ["bash", str(installer)],
                    cwd=fixture,
                    env=clean,
                    capture_output=True,
                    check=False,
                    timeout=args.timeout,
                )
                stdout_path, stderr_path = (
                    side / "installer.stdout",
                    side / "installer.stderr",
                )
                stdout_path.write_bytes(completed.stdout)
                stderr_path.write_bytes(completed.stderr)
                text = completed.stdout.decode("utf-8", "replace")
                detected = (
                    re.search(
                        rf"uv {re.escape(OLD_VERSION)}(?:[ \t][^\n]*)? does not satisfy required uv >= 0\.11\.0",
                        text,
                    )
                    is not None
                    and "Updating uv automatically" in text
                )
                ready = re.search(
                    r"uv ready: uv ([0-9]+\.[0-9]+\.[0-9]+)(?:[^\n]*) \(([^\n]+)\)",
                    text,
                )
                if completed.returncode or not detected or ready is None:
                    raise RuntimeError(
                        f"installer did not detect/remediate old uv (exit {completed.returncode})"
                    )
                final = uv_details(Path(ready.group(2)), ready.group(1))
                shutil.copyfile(Path(final["path"]), side / "final-uv.bin")
                if tuple(map(int, final["version"].split("."))) < MINIMUM_VERSION:
                    raise ValueError("installer final uv remains outdated")
                report["installer"] = {
                    "supported": True,
                    "path": str(installer),
                    "sha256": sha256(installer),
                    "exit_code": completed.returncode,
                    "stdout_sha256": sha256(stdout_path),
                    "stderr_sha256": sha256(stderr_path),
                    "detected_outdated": detected,
                    "action": None,
                }
                report["final_uv"] = final
                report["outcome"] = "remediated"
        report["passed"] = True
    except Exception as exc:
        report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        atomic_write(output, report)
    return 0 if report["passed"] else 1


def aggregate(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    source, workflow = identity("outdated-uv-aggregate")
    failures, axes, package = [], [], None
    for expected, name in zip(AXES, args.reports, strict=True):
        path = Path(name).resolve(strict=True)
        value = json.loads(path.read_text("utf-8"))
        if value.get("axis") != expected or value.get("kind") != "outdated_uv_axis":
            failures.append(f"{expected}: report identity mismatch")
        elif value.get("source") != source:
            failures.append(f"{expected}: source identity mismatch")
        elif value.get("workflow") != workflow | {"job": "outdated-uv-axis"}:
            failures.append(f"{expected}: workflow identity mismatch")
        elif value.get("passed") is not True:
            failures.append(f"{expected}: {value.get('failure')}")
        binding = value.get("package_qualification")
        if package is None:
            package = binding
        elif binding and binding.get("aggregate_sha256") != package.get(
            "aggregate_sha256"
        ):
            failures.append(f"{expected}: package aggregate mismatch")
        axes.append(
            {
                "axis": expected,
                "report_sha256": sha256(path),
                "passed": value.get("passed") is True,
            }
        )
    trusted = (
        os.environ.get("GITHUB_EVENT_NAME") == "push"
        and os.environ.get("GITHUB_REF") == "refs/heads/develop"
        and args.trusted
    )
    value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "outdated_uv_aggregate",
        "qualification_id": "NO1-006A",
        "evidence_scope": "native_outdated_uv",
        "qualification_performed": not failures,
        "qualified": False,
        "evidence_trust": "EXTERNAL_ATTESTATION_REQUIRED"
        if trusted
        else "UNTRUSTED_CANDIDATE",
        "source_commit": source["commit"],
        "package_qualification": package,
        "axes": axes,
        "failures": failures,
        "workflow": workflow,
    }
    atomic_write(output, value)
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    axis = sub.add_parser("axis")
    axis.add_argument("--axis", choices=AXES, required=True)
    axis.add_argument("--uv-executable", required=True)
    axis.add_argument("--installer", required=True)
    axis.add_argument("--wheel", required=True)
    axis.add_argument("--package-aggregate", required=True)
    axis.add_argument("--package-report", required=True)
    axis.add_argument("--output", required=True)
    axis.add_argument("--timeout", type=float, default=180)
    agg = sub.add_parser("aggregate")
    agg.add_argument("--reports", nargs=3, required=True)
    agg.add_argument("--output", required=True)
    agg.add_argument("--trusted", action="store_true")
    args = parser.parse_args()
    return run_axis(args) if args.command == "axis" else aggregate(args)


if __name__ == "__main__":
    raise SystemExit(main())
