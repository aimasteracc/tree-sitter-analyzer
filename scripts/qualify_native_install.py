#!/usr/bin/env python3
"""NO1-006A native wheel-to-MCP qualification driver."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any

from native_qualification_lib import (
    PROJECT,
    STAGES,
    atomic_write,
    identity,
    run,
    sha256,
    stage_error,
    validate_installed_provenance,
    validate_stage_semantics,
    wheel_metadata,
)

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


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def source() -> dict[str, Any]:
    return {
        "repository": env("GITHUB_REPOSITORY", "local/unknown"),
        "commit": env("GITHUB_SHA", "0" * 40),
        "ref": env("GITHUB_REF", "local"),
        "dirty": False,
    }


def workflow() -> dict[str, Any]:
    server, repo, run_id = (
        env("GITHUB_SERVER_URL", "https://github.com"),
        env("GITHUB_REPOSITORY", "local/unknown"),
        env("GITHUB_RUN_ID", "0"),
    )
    return {
        "event": env("GITHUB_EVENT_NAME", "local"),
        "run_id": run_id,
        "run_attempt": env("GITHUB_RUN_ATTEMPT", "0"),
        "job": env("GITHUB_JOB", "local"),
        "workflow_ref": env("GITHUB_WORKFLOW_REF", "local"),
        "run_url": f"{server}/{repo}/actions/runs/{run_id}",
    }


def build_manifest(args: argparse.Namespace) -> int:
    wheel = Path(args.wheel).resolve(strict=True)
    built_source = source()
    if args.commit:
        built_source["commit"] = args.commit
    value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "build_manifest",
        "source": built_source,
        "workflow": workflow(),
        "wheel": wheel_metadata(wheel),
    }
    atomic_write(Path(args.output), value)
    return 0


def empty_axis(axis_name: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "axis",
        "qualification_id": "NO1-006A",
        "evidence_scope": "native_package_mcp_first_answer",
        "axis": axis_name,
        "qualification_performed": True,
        "passed": False,
        "source": source(),
        "workflow": workflow(),
        "runner": {
            "declared_axis": axis_name,
            "observed_system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "image_os": env("ImageOS", "unknown"),
            "image_version": env("ImageVersion", "unknown"),
        },
        "wheel": {
            "filename": "unknown.whl",
            "sha256": "0" * 64,
            "size": 1,
            "name": PROJECT,
            "version": "unknown",
        },
        "stages": [],
        "failure": None,
    }


def venv_paths(root: Path) -> tuple[Path, Path]:
    scripts = root / ("Scripts" if os.name == "nt" else "bin")
    return scripts / ("python.exe" if os.name == "nt" else "python"), scripts / (
        "tree-sitter-analyzer-mcp.exe"
        if os.name == "nt"
        else "tree-sitter-analyzer-mcp"
    )


def axis(args: argparse.Namespace) -> int:
    output, report = Path(args.output).resolve(), empty_axis(args.axis)
    current_stage = STAGES[0]
    try:
        wheel = Path(args.wheel).resolve(strict=True)
        manifest_path = Path(args.wheel_manifest).resolve(strict=True)
        manifest = json.loads(manifest_path.read_text("utf-8"))
        if (
            manifest.get("kind") != "build_manifest"
            or manifest.get("schema_version") != SCHEMA_VERSION
        ):
            raise ValueError("invalid build manifest kind or schema version")
        report["source"], report["wheel"] = manifest["source"], manifest["wheel"]
        expected_system = {"linux": "Linux", "macos": "Darwin", "windows": "Windows"}[
            args.axis
        ]
        if platform.system() != expected_system:
            raise ValueError(
                f"declared axis {args.axis} does not match {platform.system()}"
            )
        current = {"source": source(), "workflow": workflow()}
        if identity(manifest) != identity(current):
            raise ValueError(
                "build manifest is not bound to this event/ref/SHA/repository/run"
            )
        observed_wheel = wheel_metadata(wheel)
        if observed_wheel != manifest.get("wheel"):
            raise ValueError(
                "wheel bytes, size, filename, or archive metadata differ from manifest"
            )
        report["build_manifest_sha256"] = sha256(manifest_path)
        report["stages"].append({"id": current_stage, "passed": True})
        with tempfile.TemporaryDirectory(prefix="tsa-native-qualification-") as tmp:
            root, project = Path(tmp), Path(tmp) / "fixture"
            envroot = root / "venv"
            project.mkdir()
            (project / "sample.py").write_text(
                "def answer():\n    return 42\n", "utf-8"
            )
            current_stage = STAGES[1]
            venv.EnvBuilder(with_pip=True, clear=True, symlinks=os.name != "nt").create(
                envroot
            )
            python, console = venv_paths(envroot)
            clean_env = {
                k: v
                for k, v in os.environ.items()
                if k
                not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PYTHONNOUSERSITE"}
            }
            clean_env.update(
                {
                    "PYTHONPATH": "",
                    "PYTHONNOUSERSITE": "1",
                    "VIRTUAL_ENV": str(envroot),
                    "PATH": str(python.parent) + os.pathsep + clean_env.get("PATH", ""),
                }
            )
            rc, out, err, duration = run(
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
            side = output.parent
            side.mkdir(parents=True, exist_ok=True)
            (side / "install.stdout").write_bytes(out)
            (side / "install.stderr").write_bytes(err)
            report["install"] = {
                "exit_code": rc,
                "duration_seconds": round(duration, 3),
                "stdout_sha256": sha256(side / "install.stdout"),
                "stderr_sha256": sha256(side / "install.stderr"),
                "fresh_venv": True,
                "cwd_outside_checkout": True,
                "pythonpath_cleared": True,
            }
            if rc != 0:
                raise RuntimeError(f"pip install failed with exit {rc}")
            report["stages"].append({"id": current_stage, "passed": True})
            current_stage = STAGES[2]
            helper = root / "official_mcp_probe.py"
            helper.write_bytes(
                Path(__file__).with_name("native_mcp_probe.py").read_bytes()
            )
            rc, meta_out, meta_err, _ = run(
                [str(python), str(helper), "--metadata-only"],
                cwd=project,
                env=clean_env,
                timeout=30,
            )
            if rc != 0:
                raise RuntimeError(
                    f"installed provenance probe failed with exit {rc}: {meta_err[-1000:].decode('utf-8', 'replace')}"
                )
            provenance = json.loads(meta_out.decode("utf-8"))
            metadata, runtime = provenance["metadata"], provenance["runtime"]
            report["metadata"] = validate_installed_provenance(
                metadata, runtime, envroot, observed_wheel
            )
            report["runtime"] = runtime
            freeze_rc, freeze_out, freeze_err, _ = run(
                [str(python), "-m", "pip", "freeze", "--all"],
                cwd=project,
                env=clean_env,
                timeout=60,
            )
            if freeze_rc != 0:
                raise RuntimeError(
                    f"pip freeze failed: {freeze_err.decode('utf-8', 'replace')}"
                )
            (side / "dependency-manifest.txt").write_bytes(freeze_out)
            report["dependency_manifest_sha256"] = sha256(
                side / "dependency-manifest.txt"
            )
            report["stages"].append({"id": current_stage, "passed": True})
            current_stage = STAGES[3]
            transcript = side / "mcp-transcript.ndjson"
            rc, probe_out, probe_err, mcp_duration = run(
                [str(python), str(helper), str(console), str(project), str(transcript)],
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
            if observed["metadata"] != metadata or observed["runtime"] != runtime:
                raise ValueError("MCP process provenance differs from metadata probe")
            mcp = observed["mcp"]
            if (
                not Path(mcp["executable"])
                .absolute()
                .is_relative_to(envroot.absolute())
            ):
                raise ValueError(
                    "distribution/module/runtime/console provenance escaped fresh venv"
                )
            report["mcp"] = {
                **mcp,
                "duration_seconds": round(mcp_duration, 3),
                "transcript_sha256": sha256(transcript),
                "stderr_sha256": sha256(side / "mcp.stderr"),
            }
            report["stages"].append({"id": current_stage, "passed": True})
            report["passed"], report["failure"] = True, None
    except Exception as exc:
        stage_error(report, current_stage, exc)
    finally:
        atomic_write(output, report)
    return 0 if report["passed"] else 1


def load_validator(schema_path: Path) -> Any:
    import jsonschema

    schema = json.loads(schema_path.resolve(strict=True).read_text("utf-8"))
    validator = jsonschema.validators.validator_for(schema)(schema)
    validator.check_schema(schema)
    return validator


def aggregate(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    reports: list[dict[str, Any]] = []
    failures: list[str] = []
    try:
        validator = load_validator(Path(args.schema))
        manifest_path, wheel_path = (
            Path(args.wheel_manifest).resolve(strict=True),
            Path(args.wheel).resolve(strict=True),
        )
        manifest = json.loads(manifest_path.read_text("utf-8"))
        validator.validate(manifest)
        if manifest.get("kind") != "build_manifest" or wheel_metadata(
            wheel_path
        ) != manifest.get("wheel"):
            raise ValueError("aggregate wheel does not exactly match build manifest")
        current = {"source": source(), "workflow": workflow()}
        if identity(manifest) != identity(current):
            raise ValueError("build manifest is not bound to current aggregate run")
        manifest_digest = sha256(manifest_path)
    except Exception as exc:
        failures.append(f"aggregate input: {type(exc).__name__}: {exc}")
        manifest, manifest_digest = {}, ""
    if "validator" in locals():
        for raw in args.reports:
            path = Path(raw).resolve()
            try:
                value = json.loads(path.read_text("utf-8"))
                validator.validate(value)
                value["_artifact_sha256"] = sha256(path)
                reports.append(value)
            except Exception as exc:
                failures.append(f"{path.name}: {type(exc).__name__}: {exc}")
    axes = [item.get("axis") for item in reports]
    if sorted(axes) != sorted(AXES):
        failures.append(f"expected exactly {list(AXES)}, got {axes}")
    current_identity = identity({"source": source(), "workflow": workflow()})
    for report in reports:
        axis_name = report.get("axis")
        if identity(report) != current_identity:
            failures.append(
                f"{axis_name}: report event/ref/SHA/repository/run identity mismatch"
            )
        if report.get("build_manifest_sha256") != manifest_digest or report.get(
            "wheel"
        ) != manifest.get("wheel"):
            failures.append(f"{axis_name}: manifest or wheel identity mismatch")
        stage_failure = validate_stage_semantics(report)
        if stage_failure:
            failures.append(f"{axis_name}: {stage_failure}")
        expected_system = {
            "linux": "Linux",
            "macos": "Darwin",
            "windows": "Windows",
        }.get(axis_name)
        if (
            report.get("passed") is not True
            or report.get("runner", {}).get("observed_system") != expected_system
        ):
            failures.append(f"{axis_name}: failed report or runner mismatch")
        first = report.get("mcp", {}).get("first_call", {})
        if report.get("mcp", {}).get("tools") != TOOLS or first != {
            "name": "index",
            "arguments": {"action": "status"},
            "is_error": False,
            "default_format": "toon",
            "verdict": "WARN",
            "project_root": first.get("project_root"),
            "indexed": False,
            "total_files": 0,
            "summary": "codegraph_status: index missing or empty",
        }:
            failures.append(f"{axis_name}: MCP fixture status oracle mismatch")
    trusted_run = (
        args.trusted
        and env("GITHUB_EVENT_NAME") == "push"
        and env("GITHUB_REF") == "refs/heads/develop"
    )
    if args.trusted and not trusted_run:
        failures.append("trusted aggregation is restricted to develop pushes")
    if trusted_run and any(
        report.get("workflow", {}).get("event") != "push"
        or report.get("source", {}).get("ref") != "refs/heads/develop"
        for report in reports
    ):
        failures.append("trusted aggregation refuses candidate/PR reports")
    axes_valid = not failures and trusted_run
    value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aggregate",
        "qualification_id": "NO1-006A",
        "evidence_scope": "native_package_mcp_first_answer",
        "qualification_performed": len(reports) == 3,
        "native_axes_qualified": axes_valid,
        "qualified": False,
        "evidence_trust": (
            "EXTERNAL_ATTESTATION_REQUIRED" if axes_valid else "UNTRUSTED_CANDIDATE"
        ),
        "source_commit": manifest.get("source", {}).get("commit"),
        "wheel_sha256": manifest.get("wheel", {}).get("sha256"),
        "build_manifest_sha256": manifest_digest or None,
        "wheel": manifest.get("wheel"),
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
        "workflow": workflow(),
    }
    try:
        validator.validate(value)
    except Exception as exc:
        failures.append(f"aggregate schema validation failed: {exc}")
        value.update(
            {
                "failures": failures,
                "native_axes_qualified": False,
                "qualified": False,
                "evidence_trust": "UNTRUSTED_CANDIDATE",
            }
        )
    atomic_write(output, value)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-manifest")
    build.add_argument("--wheel", required=True)
    build.add_argument("--output", required=True)
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
    for name in ("--schema", "--wheel", "--wheel-manifest", "--output"):
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
