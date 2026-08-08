"""Fixture builders for native qualification contract tests."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "qualify_native_install.py"
SCHEMA = ROOT / "rfcs/schemas/no1-006a-native-attestation-v1.schema.json"
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


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def github_env(event: str = "pull_request") -> dict[str, str]:
    ref = "refs/heads/develop" if event == "push" else "refs/pull/1/merge"
    return {
        **os.environ,
        "GITHUB_EVENT_NAME": event,
        "GITHUB_REF": ref,
        "GITHUB_SHA": "b" * 40,
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_JOB": "aggregate",
        "GITHUB_WORKFLOW_REF": f"owner/repo/.github/workflows/native-install-qualification.yml@{ref}",
        "GITHUB_SERVER_URL": "https://github.com",
    }


def workflow(event: str, job: str = "native-axis") -> dict[str, str]:
    env = github_env(event)
    return {
        "event": event,
        "run_id": "123",
        "run_attempt": "1",
        "job": job,
        "workflow_ref": env["GITHUB_WORKFLOW_REF"],
        "run_url": "https://github.com/owner/repo/actions/runs/123",
    }


def source(event: str) -> dict[str, Any]:
    return {
        "repository": "owner/repo",
        "commit": "b" * 40,
        "ref": github_env(event)["GITHUB_REF"],
        "dirty": False,
    }


def make_wheel(path: Path) -> dict[str, Any]:
    metadata = b"Metadata-Version: 2.1\nName: tree-sitter-analyzer\nVersion: 1.0\n\n"
    files = {
        "tree_sitter_analyzer/__init__.py": b"",
        "tree_sitter_analyzer-1.0.dist-info/METADATA": metadata,
    }
    rows = [
        [
            name,
            "sha256="
            + __import__("base64")
            .urlsafe_b64encode(hashlib.sha256(data).digest())
            .rstrip(b"=")
            .decode(),
            str(len(data)),
        ]
        for name, data in files.items()
    ]
    rows.append(["tree_sitter_analyzer-1.0.dist-info/RECORD", "", ""])
    record = io.StringIO()
    csv.writer(record, lineterminator="\n").writerows(rows)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr("tree_sitter_analyzer-1.0.dist-info/RECORD", record.getvalue())
    return {
        "filename": path.name,
        "sha256": sha(path),
        "size": path.stat().st_size,
        "name": "tree-sitter-analyzer",
        "version": "1.0",
    }


def manifest(tmp_path: Path, event: str) -> tuple[Path, Path, dict[str, Any]]:
    wheel = tmp_path / "tree_sitter_analyzer-1.0-py3-none-any.whl"
    wheel_value = make_wheel(wheel)
    value = {
        "schema_version": "no1-006a-native-attestation-v1",
        "kind": "build_manifest",
        "source": source(event),
        "workflow": workflow(event, "build-once"),
        "wheel": wheel_value,
    }
    path = tmp_path / "wheel-manifest.json"
    path.write_text(json.dumps(value))
    return wheel, path, value


def report(
    axis: str, manifest_path: Path, manifest_value: dict[str, Any], event: str
) -> dict[str, Any]:
    system = {"linux": "Linux", "macos": "Darwin", "windows": "Windows"}[axis]
    project = f"/venv/{axis}/fixture"
    return {
        "schema_version": "no1-006a-native-attestation-v1",
        "kind": "axis",
        "qualification_id": "NO1-006A",
        "evidence_scope": "native_package_mcp_first_answer",
        "axis": axis,
        "qualification_performed": True,
        "passed": True,
        "source": source(event),
        "workflow": workflow(event),
        "runner": {
            "declared_axis": axis,
            "observed_system": system,
            "release": "1",
            "machine": "x86_64",
            "image_os": "image",
            "image_version": "1",
        },
        "wheel": manifest_value["wheel"],
        "stages": [
            {"id": stage, "passed": True}
            for stage in [
                "verify_wheel",
                "install",
                "metadata_provenance",
                "mcp_protocol",
            ]
        ],
        "failure": None,
        "build_manifest_sha256": sha(manifest_path),
        "install": {
            "exit_code": 0,
            "duration_seconds": 1.0,
            "stdout_sha256": "d" * 64,
            "stderr_sha256": "e" * 64,
            "fresh_venv": True,
            "cwd_outside_checkout": True,
            "pythonpath_cleared": True,
        },
        "metadata": {
            "name": "tree-sitter-analyzer",
            "version": "1.0",
            "location": "/venv/site-packages",
            "module_file": "/venv/site-packages/tree_sitter_analyzer/__init__.py",
            "module_origin": "/venv/site-packages/tree_sitter_analyzer/__init__.py",
            "direct_url": {
                "url": "file:///wheel.whl",
                "archive_info": {"hash": "sha256=" + manifest_value["wheel"]["sha256"]},
            },
            "direct_url_path": "/venv/site-packages/x.dist-info/direct_url.json",
            "module_recorded": True,
            "installed_record": {
                "record_path": "/venv/site-packages/x.dist-info/RECORD",
                "record_sha256": "2" * 64,
                "entry_count": 1,
                "files": [
                    {
                        "path": "tree_sitter_analyzer/__init__.py",
                        "sha256": "3" * 64,
                        "size": 1,
                    }
                ],
            },
            "all_paths_in_fresh_venv": True,
            "direct_url_sha256": manifest_value["wheel"]["sha256"],
        },
        "runtime": {
            "python": "3.10.0",
            "executable": "/venv/bin/python",
            "prefix": "/venv",
        },
        "mcp": {
            "executable": "/venv/bin/tree-sitter-analyzer-mcp",
            "protocol_version": "2025",
            "server_name": "tree-sitter-analyzer-mcp",
            "server_version": "1",
            "tools": TOOLS,
            "first_call": {
                "name": "index",
                "arguments": {"action": "status"},
                "is_error": False,
                "default_format": "toon",
                "verdict": "WARN",
                "project_root": project,
                "indexed": False,
                "total_files": 0,
                "summary": "codegraph_status: index missing or empty",
            },
            "duration_seconds": 1.0,
            "transcript_sha256": "f" * 64,
            "stderr_sha256": "0" * 64,
        },
        "dependency_manifest_sha256": "1" * 64,
    }


def aggregate(
    tmp_path: Path,
    reports: list[dict[str, Any]],
    *,
    event: str = "pull_request",
    trusted: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    wheel, manifest_path, manifest_value = manifest(tmp_path, event)
    paths = []
    for index, value in enumerate(reports):
        path = tmp_path / f"report-{index}.json"
        path.write_text(json.dumps(value))
        paths.append(str(path))
    output = tmp_path / "aggregate.json"
    command = [
        sys.executable,
        str(SCRIPT),
        "aggregate",
        "--schema",
        str(SCHEMA),
        "--wheel",
        str(wheel),
        "--wheel-manifest",
        str(manifest_path),
        "--reports",
        *paths,
        "--output",
        str(output),
    ]
    if trusted:
        command.append("--trusted")
    result = subprocess.run(
        command, capture_output=True, text=True, env=github_env(event), check=False
    )
    return result, json.loads(output.read_text())


def mutate_wheel_record(path: Path, mutation: str) -> None:
    with zipfile.ZipFile(path) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    record_name = next(name for name in contents if name.endswith(".dist-info/RECORD"))
    if mutation in {"unrecorded", "pth"}:
        contents["payload.pth" if mutation == "pth" else "unrecorded.bin"] = b"inject"
    else:
        rows = list(csv.reader(contents[record_name].decode().splitlines()))
        if mutation == "duplicate":
            rows.insert(0, rows[0])
        elif mutation == "digest":
            rows[0][1] = "sha256=" + "a" * 43
        output = io.StringIO()
        csv.writer(output, lineterminator="\n").writerows(rows)
        contents[record_name] = output.getvalue().encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)


def trusted_verifier_result(tmp_path: Path, mutation: str) -> int:
    import textwrap

    wheel, manifest_path, manifest_value = manifest(tmp_path, "push")
    trusted = tmp_path / "trusted-input"
    (tmp_path / "trusted-job").mkdir()
    for directory in (
        trusted / "build",
        trusted / "aggregate",
        *(trusted / axis for axis in ("linux", "macos", "windows")),
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (trusted / "build" / wheel.name).write_bytes(wheel.read_bytes())
    (trusted / "build" / "wheel-manifest.json").write_bytes(manifest_path.read_bytes())
    report_values = {
        axis: report(axis, manifest_path, manifest_value, "push")
        for axis in ("linux", "macos", "windows")
    }
    if mutation == "stage_false":
        report_values["linux"]["stages"][0]["passed"] = False
    elif mutation == "extra_field":
        report_values["linux"]["forged"] = True
    elif mutation == "mcp_oracle":
        report_values["linux"]["mcp"]["first_call"]["indexed"] = True
    elif mutation == "venv_provenance":
        report_values["linux"]["metadata"]["all_paths_in_fresh_venv"] = False
    elif mutation == "direct_hash":
        report_values["linux"]["metadata"]["direct_url_sha256"] = "a" * 64
    for axis, value in report_values.items():
        (trusted / axis / "report.json").write_text(json.dumps(value))
    aggregate_value = {
        "schema_version": "no1-006a-native-attestation-v1",
        "kind": "aggregate",
        "qualification_id": "NO1-006A",
        "evidence_scope": "native_package_mcp_first_answer",
        "qualification_performed": True,
        "native_axes_qualified": True,
        "qualified": False,
        "evidence_trust": "EXTERNAL_ATTESTATION_REQUIRED",
        "source_commit": "b" * 40,
        "wheel_sha256": manifest_value["wheel"]["sha256"],
        "build_manifest_sha256": sha(manifest_path),
        "wheel": manifest_value["wheel"],
        "failures": [],
        "workflow": workflow("push", "aggregate"),
        "axes": [
            {
                "axis": axis,
                "report_sha256": sha(trusted / axis / "report.json"),
                "passed": True,
            }
            for axis in ("linux", "macos", "windows")
        ],
    }
    if mutation == "aggregate_extra":
        aggregate_value["forged"] = True
    elif mutation == "axis_digest":
        aggregate_value["axes"][0]["report_sha256"] = "a" * 64
    (trusted / "aggregate" / "aggregate.json").write_text(json.dumps(aggregate_value))
    workflow_text = (
        ROOT / ".github/workflows/native-install-qualification.yml"
    ).read_text()
    code = workflow_text.split("          python - <<'PY'\n", 1)[1].split(
        "\n          PY", 1
    )[0]
    environment = github_env("push") | {"WHEEL_NAME": wheel.name}
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode


def assert_timeout_cleanup(tmp_path: Path) -> None:
    import time

    from native_qualification_lib import run

    pid_file = tmp_path / "child.pid"
    child = (
        "import pathlib,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        + f"pathlib.Path({str(pid_file)!r}).write_text(str(__import__('os').getpid()));"
        + "time.sleep(60)"
    )
    parent = (
        "import subprocess,sys,time;"
        + f"subprocess.Popen([sys.executable,'-c',{child!r}]);"
        + "time.sleep(60)"
    )
    rc, _, _, duration = run(
        [sys.executable, "-c", parent], cwd=tmp_path, env=dict(os.environ), timeout=1
    )
    child_pid = int(pid_file.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and __import__("psutil").pid_exists(child_pid):
        time.sleep(0.05)
    assert (rc, __import__("psutil").pid_exists(child_pid)) == (124, False)
    assert duration < 7


def assert_success_cleanup(tmp_path: Path) -> None:
    import time

    from native_qualification_lib import run

    pid_file = tmp_path / "normal-child.pid"
    child = f"import os,pathlib,time;pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()));time.sleep(60)"
    parent = (
        "import os,subprocess,sys,time;flags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0);"
        + f"subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=os.name!='nt',creationflags=flags if os.name=='nt' else 0);"
        + "time.sleep(.2)"
    )
    rc, _, _, duration = run(
        [sys.executable, "-c", parent], cwd=tmp_path, env=dict(os.environ), timeout=5
    )
    child_pid = int(pid_file.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and __import__("psutil").pid_exists(child_pid):
        time.sleep(0.05)
    assert (rc, __import__("psutil").pid_exists(child_pid)) == (0, False)
    assert duration < 5
