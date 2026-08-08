#!/usr/bin/env python3
"""NO1-006A native wheel-to-MCP qualification driver.

This is deliberately separate from qualify_fresh_install.py: that harness remains
an offline installer contract and can never produce native qualification evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import venv
import zipfile
from email.parser import BytesParser
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "no1-006a-native-attestation-v1"
AXES = ("linux", "macos", "windows")
TOOLS = [
    "search",
    "nav",
    "structure",
    "health",
    "edit",
    "project",
    "index",
    "viz",
    "set_project_path",
]
HEX64 = set("0123456789abcdef")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _source() -> dict[str, Any]:
    return {"repository": _env("GITHUB_REPOSITORY", "local/unknown"), "commit": _env("GITHUB_SHA", "0" * 40), "ref": _env("GITHUB_REF", "local"), "dirty": False}  # fmt: skip  # pragma: allowlist secret


def _workflow() -> dict[str, Any]:
    server = _env("GITHUB_SERVER_URL", "https://github.com")
    repo = _env("GITHUB_REPOSITORY", "local/unknown")
    run_id = _env("GITHUB_RUN_ID", "0")
    return {"event": _env("GITHUB_EVENT_NAME", "local"), "run_id": run_id, "run_attempt": _env("GITHUB_RUN_ATTEMPT", "0"), "job": _env("GITHUB_JOB", "local"), "workflow_ref": _env("GITHUB_WORKFLOW_REF", "local"), "run_url": f"{server}/{repo}/actions/runs/{run_id}"}  # fmt: skip  # pragma: allowlist secret


def _wheel_metadata(wheel: Path) -> tuple[str, str]:
    with zipfile.ZipFile(wheel) as archive:
        names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(names) != 1:
            raise ValueError("wheel must contain exactly one METADATA file")
        metadata = BytesParser().parsebytes(archive.read(names[0]))
    return str(metadata["Name"]), str(metadata["Version"])


def build_manifest(args: argparse.Namespace) -> int:
    wheel = Path(args.wheel).resolve(strict=True)
    if not wheel.is_file() or wheel.suffix != ".whl" or wheel.is_symlink():
        raise ValueError("--wheel must be one regular, non-symlink wheel")
    name, version = _wheel_metadata(wheel)
    source = _source()
    if args.commit:
        source["commit"] = args.commit
    manifest = {"schema_version": SCHEMA_VERSION, "kind": "build_manifest", "source": source, "workflow": _workflow(), "wheel": {"filename": wheel.name, "sha256": _sha(wheel), "size": wheel.stat().st_size, "name": name, "version": version}}  # fmt: skip  # pragma: allowlist secret
    _write(Path(args.output), manifest)
    return 0


def _kill(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        import signal

        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _run(
    argv: list[str], *, cwd: Path, env: dict[str, str], timeout: int
) -> tuple[int, bytes, bytes, float]:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    started = time.monotonic()
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=flags,
        start_new_session=os.name != "nt",
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(proc)
        out, err = proc.communicate()
        return 124, out, err, time.monotonic() - started
    return proc.returncode, out, err, time.monotonic() - started


def _venv_paths(root: Path) -> tuple[Path, Path]:
    scripts = root / ("Scripts" if os.name == "nt" else "bin")
    return scripts / ("python.exe" if os.name == "nt" else "python"), scripts / (
        "tree-sitter-analyzer-mcp.exe"
        if os.name == "nt"
        else "tree-sitter-analyzer-mcp"
    )


def axis(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    wheel = Path(args.wheel).resolve(strict=True)
    manifest_path = Path(args.wheel_manifest).resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "axis",
        "qualification_id": "NO1-006A",
        "evidence_scope": "native_package_mcp_first_answer",
        "axis": args.axis,
        "qualification_performed": True,
        "passed": False,
        "source": manifest.get("source", _source()),
        "workflow": _workflow(),
        "runner": {
            "declared_axis": args.axis,
            "observed_system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "image_os": _env("ImageOS", "unknown"),
            "image_version": _env("ImageVersion", "unknown"),
        },
        "wheel": manifest.get("wheel", {}),
        "stages": [],
        "failure": None,
    }
    side = output.parent
    side.mkdir(parents=True, exist_ok=True)
    current_stage = "preflight"
    try:
        expected_system = {"linux": "Linux", "macos": "Darwin", "windows": "Windows"}[
            args.axis
        ]
        if platform.system() != expected_system:
            raise ValueError(
                f"declared axis {args.axis} does not match {platform.system()}"
            )
        if (
            manifest.get("source", {}).get("dirty") is not False
            or manifest.get("source", {}).get("commit")
            != _env("GITHUB_SHA", manifest.get("source", {}).get("commit", ""))
            or manifest.get("source", {}).get("repository")
            != _env(
                "GITHUB_REPOSITORY", manifest.get("source", {}).get("repository", "")
            )
        ):
            raise ValueError("build manifest source provenance does not match this run")
        if (
            _sha(wheel) != manifest["wheel"]["sha256"]
            or wheel.name != manifest["wheel"]["filename"]
        ):
            raise ValueError("downloaded wheel does not match build manifest")
        report["build_manifest_sha256"] = _sha(manifest_path)
        report["stages"].append({"id": "verify_wheel", "passed": True})
        with tempfile.TemporaryDirectory(prefix="tsa-native-qualification-") as tmp:
            root = Path(tmp)
            envroot = root / "venv"
            project = root / "fixture"
            project.mkdir()
            (project / "sample.py").write_text(
                "def answer():\n    return 42\n", encoding="utf-8"
            )
            current_stage = "install"
            venv.EnvBuilder(with_pip=True, clear=True, symlinks=os.name != "nt").create(
                envroot
            )
            python, executable = _venv_paths(envroot)
            clean_env = {
                k: v
                for k, v in os.environ.items()
                if k not in {"PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME"}
            }
            clean_env.update(
                {
                    "PYTHONPATH": "",
                    "VIRTUAL_ENV": str(envroot),
                    "PATH": str(python.parent) + os.pathsep + clean_env.get("PATH", ""),
                }
            )
            rc, install_out, install_err, duration = _run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--no-cache-dir",
                    f"{wheel}[mcp]",
                ],
                cwd=project,
                env=clean_env,
                timeout=args.install_timeout,
            )
            (side / "install.stdout").write_bytes(install_out)
            (side / "install.stderr").write_bytes(install_err)
            if rc != 0:
                raise RuntimeError(f"pip install failed with exit {rc}")
            report["install"] = {
                "exit_code": rc,
                "duration_seconds": round(duration, 3),
                "stdout_sha256": _sha(side / "install.stdout"),
                "stderr_sha256": _sha(side / "install.stderr"),
                "fresh_venv": True,
                "cwd_outside_checkout": True,
                "pythonpath_cleared": True,
            }
            report["stages"].append({"id": "install", "passed": True})
            current_stage = "metadata_provenance"
            if not executable.is_file() or not str(executable).startswith(str(envroot)):
                raise ValueError("installed MCP executable provenance failed")
            current_stage = "mcp_protocol"
            helper = root / "official_mcp_probe.py"
            helper.write_bytes(
                Path(__file__).with_name("native_mcp_probe.py").read_bytes()
            )
            transcript = side / "mcp-transcript.ndjson"
            rc, probe_out, probe_err, duration = _run(
                [
                    str(python),
                    str(helper),
                    str(executable),
                    str(project),
                    str(transcript),
                ],
                cwd=project,
                env=clean_env,
                timeout=args.mcp_timeout,
            )
            (side / "mcp.stderr").write_bytes(probe_err)
            if rc != 0:
                raise RuntimeError(
                    f"official MCP client probe failed with exit {rc}: {probe_err[-1000:].decode('utf-8', 'replace')}"
                )
            observed = json.loads(probe_out.decode("utf-8"))
            location = Path(observed["metadata"]["location"]).resolve()
            module_file = Path(observed["metadata"]["module_file"]).resolve()
            if (
                observed["metadata"]["name"].lower().replace("_", "-")
                != "tree-sitter-analyzer"
                or observed["metadata"]["version"] != manifest["wheel"]["version"]
            ):
                raise ValueError("installed metadata does not match wheel")
            checkout = Path.cwd().resolve()
            if checkout in location.parents or checkout in module_file.parents:
                raise ValueError("installed package leaked from checkout")
            freeze_rc, freeze_out, freeze_err, _ = _run(
                [str(python), "-m", "pip", "freeze", "--all"],
                cwd=project,
                env=clean_env,
                timeout=60,
            )
            if freeze_rc != 0:
                message = freeze_err.decode("utf-8", "replace")
                raise RuntimeError(f"pip freeze failed: {message}")
            (side / "dependency-manifest.txt").write_bytes(freeze_out)
            report.update(observed)
            report["metadata"] = {
                **observed["metadata"],
                "distribution_outside_checkout": True,
                "executable_in_fresh_venv": True,
            }
            report["mcp"].update(
                {
                    "duration_seconds": round(duration, 3),
                    "transcript_sha256": _sha(transcript),
                    "stderr_sha256": _sha(side / "mcp.stderr"),
                }
            )
            report["dependency_manifest_sha256"] = _sha(
                side / "dependency-manifest.txt"
            )
            report["stages"].append({"id": "metadata_provenance", "passed": True})
            report["stages"].append({"id": "mcp_protocol", "passed": True})
            report["passed"] = True
    except Exception as exc:
        report["failure"] = {
            "stage": current_stage,
            "type": type(exc).__name__,
            "message": str(exc)[:2000],
        }
    _write(output, report)
    return 0 if report["passed"] else 1


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def aggregate(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    reports = []
    failures = []
    schema = json.loads(
        Path(args.schema).resolve(strict=True).read_text(encoding="utf-8")
    )
    try:
        import jsonschema

        validator = jsonschema.validators.validator_for(schema)(schema)
        validator.check_schema(schema)
    except Exception as exc:
        print(f"schema unavailable or invalid: {exc}", file=sys.stderr)
        return 2
    for raw in args.reports:
        path = Path(raw).resolve()
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            validator.validate(value)
            value["_artifact_sha256"] = _sha(path)
            reports.append(value)
        except Exception as exc:
            failures.append(f"{path.name}: {exc}")
    axes = [r.get("axis") for r in reports]
    if sorted(axes) != sorted(AXES):
        failures.append(f"expected exactly {list(AXES)}, got {axes}")
    commits = {r.get("source", {}).get("commit") for r in reports}
    wheels = {r.get("wheel", {}).get("sha256") for r in reports}
    repositories = {r.get("source", {}).get("repository") for r in reports}
    run_ids = {r.get("workflow", {}).get("run_id") for r in reports}
    manifests = {r.get("build_manifest_sha256") for r in reports}
    if len(commits) != 1:
        failures.append("source commit mismatch")
    if len(wheels) != 1 or not wheels or not _valid_sha(next(iter(wheels))):
        failures.append("wheel digest mismatch or malformed")
    if len(repositories) != 1 or len(run_ids) != 1:
        failures.append("workflow provenance mismatch")
    if len(manifests) != 1 or not manifests or not _valid_sha(next(iter(manifests))):
        failures.append("build manifest digest mismatch or malformed")
    for report in reports:
        axis_name = report.get("axis")
        expected_system = {
            "linux": "Linux",
            "macos": "Darwin",
            "windows": "Windows",
        }.get(axis_name)
        if (
            report.get("schema_version") != SCHEMA_VERSION
            or report.get("kind") != "axis"
            or report.get("evidence_scope") != "native_package_mcp_first_answer"
            or report.get("passed") is not True
        ):
            failures.append(f"{axis_name}: invalid or failed report")
        if (
            report.get("runner", {}).get("declared_axis") != axis_name
            or report.get("runner", {}).get("observed_system") != expected_system
        ):
            failures.append(f"{axis_name}: runner provenance mismatch")
        if (
            report.get("mcp", {}).get("tools") != TOOLS
            or report.get("mcp", {}).get("first_call", {}).get("default_format")
            != "toon"
        ):
            failures.append(f"{report.get('axis')}: MCP oracle mismatch")
    trusted = (
        args.trusted
        and _env("GITHUB_EVENT_NAME") == "push"
        and _env("GITHUB_REF") == "refs/heads/develop"
    )
    if args.trusted and not trusted:
        failures.append("trusted aggregation is restricted to develop pushes")
    aggregate_value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aggregate",
        "qualification_id": "NO1-006A",
        "evidence_scope": "native_package_mcp_first_answer",
        "qualification_performed": len(reports) == 3,
        "native_axes_qualified": not failures,
        "qualified": not failures and trusted,
        "evidence_trust": "ATTESTATION_ELIGIBLE" if trusted else "UNTRUSTED_CANDIDATE",
        "source_commit": next(iter(commits)) if len(commits) == 1 else None,
        "wheel_sha256": next(iter(wheels)) if len(wheels) == 1 else None,
        "axes": sorted(
            [
                {
                    "axis": r.get("axis"),
                    "report_sha256": r.get("_artifact_sha256"),
                    "passed": r.get("passed") is True,
                }
                for r in reports
            ],
            key=lambda x: str(x["axis"]),
        ),
        "failures": failures,
        "workflow": _workflow(),
    }
    try:
        validator.validate(aggregate_value)
    except Exception as exc:
        failures.append(f"aggregate schema validation failed: {exc}")
        aggregate_value["failures"] = failures
        aggregate_value["native_axes_qualified"] = False
        aggregate_value["qualified"] = False
    _write(output, aggregate_value)
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-manifest")
    for name in ("--wheel", "--output"):
        build.add_argument(name, required=True)
    build.add_argument("--commit")
    build.set_defaults(func=build_manifest)
    native = sub.add_parser("axis")
    for name in ("--wheel", "--wheel-manifest", "--output"):
        native.add_argument(name, required=True)
    native.add_argument("--axis", choices=AXES, required=True)
    native.add_argument("--install-timeout", type=int, default=300)
    native.add_argument("--mcp-timeout", type=int, default=90)
    native.set_defaults(func=axis)
    combined = sub.add_parser("aggregate")
    for name in ("--schema", "--output"):
        combined.add_argument(name, required=True)
    combined.add_argument("--reports", nargs="+", required=True)
    combined.add_argument("--trusted", action="store_true")
    combined.set_defaults(func=aggregate)
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"qualification error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
