"""Fixture builders for native qualification contract tests."""

from __future__ import annotations

import base64
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

import psutil

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
    root = f"/tmp/tsa-native-qualification-test-{axis}"
    project = f"{root}/fixture"
    prefix = f"{root}/venv"
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
            "tool": None,
            "argv": [
                f"{prefix}/bin/python",
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--no-cache-dir",
                "wheel.whl[mcp]",
            ],
        },
        "metadata": {
            "name": "tree-sitter-analyzer",
            "version": "1.0",
            "location": f"{prefix}/site-packages",
            "module_file": f"{prefix}/site-packages/tree_sitter_analyzer/__init__.py",
            "module_origin": f"{prefix}/site-packages/tree_sitter_analyzer/__init__.py",
            "direct_url": {
                "url": "file:///wheel.whl",
                "archive_info": {"hash": "sha256=" + manifest_value["wheel"]["sha256"]},
            },
            "direct_url_path": f"{prefix}/site-packages/tree_sitter_analyzer-1.0.dist-info/direct_url.json",
            "module_recorded": True,
            "installed_record": {
                "record_path": f"{prefix}/site-packages/tree_sitter_analyzer-1.0.dist-info/RECORD",
                "record_sha256": hashlib.sha256(b"").hexdigest(),
                "entry_count": 1,
                "files": [
                    {
                        "path": "tree_sitter_analyzer/__init__.py",
                        "sha256": hashlib.sha256(b"").hexdigest(),
                        "size": 0,
                    }
                ],
            },
            "all_paths_in_fresh_venv": True,
            "direct_url_sha256": manifest_value["wheel"]["sha256"],
        },
        "runtime": {
            "python": "3.10.0",
            "executable": f"{prefix}/bin/python",
            "prefix": prefix,
        },
        "mcp": {
            "executable": f"{prefix}/bin/tree-sitter-analyzer-mcp",
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
        "installed_files_zip_sha256": "4" * 64,
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


def write_trusted_axis_artifacts(
    directory: Path, value: dict[str, Any], wheel: Path
) -> None:
    """Create byte-real evidence for the no-candidate-exec verifier fixture."""
    with zipfile.ZipFile(wheel) as archive:
        record_name = next(n for n in archive.namelist() if n.endswith("/RECORD"))
        rows = list(csv.reader(archive.read(record_name).decode().splitlines()))
        contents = [archive.read(row[0]) for row in rows]
    direct_name = str(Path(record_name).parent / "direct_url.json")
    direct_data = json.dumps(value["metadata"]["direct_url"], sort_keys=True).encode()
    direct_digest = (
        base64.urlsafe_b64encode(hashlib.sha256(direct_data).digest())
        .rstrip(b"=")
        .decode()
    )
    rows.append([direct_name, "sha256=" + direct_digest, str(len(direct_data))])
    contents.append(direct_data)
    output = io.StringIO()
    csv.writer(output, lineterminator="\n").writerows(rows)
    record_bytes = output.getvalue().encode()
    contents[[row[0] for row in rows].index(record_name)] = record_bytes
    files = []
    for row, data in zip(rows, contents, strict=True):
        files.append(
            {
                "path": row[0],
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        )
    installed = value["metadata"]["installed_record"]
    installed.update(
        record_sha256=hashlib.sha256(record_bytes).hexdigest(),
        entry_count=len(files),
        files=files,
    )
    first = value["mcp"]["first_call"]
    envelope = {
        "format": first["default_format"],
        "verdict": first["verdict"],
        "project_root": first["project_root"],
        "indexed": first["indexed"],
        "total_files": first["total_files"],
        "summary_line": first["summary"],
        "agent_summary": {"summary_line": first["summary"]},
    }
    events = [
        {
            "sequence": 1,
            "method": "initialize",
            "response": {
                "protocolVersion": value["mcp"]["protocol_version"],
                "serverInfo": {
                    "name": value["mcp"]["server_name"],
                    "title": None,
                    "version": value["mcp"]["server_version"],
                    "websiteUrl": None,
                    "icons": None,
                    "description": None,
                },
            },
        },
        {"sequence": 2, "method": "tools/list", "response": {"names": TOOLS}},
        {
            "sequence": 3,
            "method": "tools/call",
            "request": {"name": "index", "arguments": {"action": "status"}},
            "response": {
                "_meta": None,
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(envelope),
                        "annotations": None,
                        "_meta": None,
                    }
                ],
                "structuredContent": None,
                "isError": False,
                "resultType": "complete",
            },
        },
    ]
    side_bytes = {
        "install.stdout": b"installed\n",
        "install.stderr": b"",
        "dependency-manifest.txt": b"tree-sitter-analyzer==1.0\n",
        "mcp-transcript.ndjson": b"".join(
            (json.dumps(event) + "\n").encode() for event in events
        ),
        "mcp.stderr": b"",
    }
    for name, data in side_bytes.items():
        (directory / name).write_bytes(data)
    value["install"]["stdout_sha256"] = sha(directory / "install.stdout")
    value["install"]["stderr_sha256"] = sha(directory / "install.stderr")
    value["dependency_manifest_sha256"] = sha(directory / "dependency-manifest.txt")
    value["mcp"]["transcript_sha256"] = sha(directory / "mcp-transcript.ndjson")
    value["mcp"]["stderr_sha256"] = sha(directory / "mcp.stderr")
    with zipfile.ZipFile(directory / "installed-files.zip", "w") as snapshot:
        snapshot.writestr("installed-record.csv", record_bytes)
        for index, data in enumerate(contents):
            snapshot.writestr(f"files/{index:06d}", data)
    value["installed_files_zip_sha256"] = sha(directory / "installed-files.zip")
    (directory / "job-result.json").write_text('{"status":"success"}')


def _rewrite_snapshot_direct(
    directory: Path, value: dict[str, Any], direct: dict[str, Any]
) -> None:
    snapshot = directory / "installed-files.zip"
    with zipfile.ZipFile(snapshot) as archive:
        names, blobs = (
            archive.namelist(),
            {name: archive.read(name) for name in archive.namelist()},
        )
    rows = list(csv.reader(blobs["installed-record.csv"].decode().splitlines()))
    index = next(
        i for i, row in enumerate(rows) if Path(row[0]).name == "direct_url.json"
    )
    data = json.dumps(direct, sort_keys=True).encode()
    encoded = (
        base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    )
    rows[index][1:] = ["sha256=" + encoded, str(len(data))]
    output = io.StringIO()
    csv.writer(output, lineterminator="\n").writerows(rows)
    blobs["installed-record.csv"], blobs[f"files/{index:06d}"] = (
        output.getvalue().encode(),
        data,
    )
    with zipfile.ZipFile(snapshot, "w") as archive:
        for name in names:
            archive.writestr(name, blobs[name])
    record = value["metadata"]["installed_record"]
    record["record_sha256"] = hashlib.sha256(blobs["installed-record.csv"]).hexdigest()
    record["files"][index].update(
        sha256=hashlib.sha256(data).hexdigest(), size=len(data)
    )
    value["installed_files_zip_sha256"] = sha(snapshot)


def pid_is_live(pid: int) -> bool:
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


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
    while time.monotonic() < deadline and pid_is_live(child_pid):
        time.sleep(0.05)
    assert (rc, pid_is_live(child_pid)) == (124, False)
    assert duration < 7


def assert_success_cleanup(tmp_path: Path) -> None:
    import time

    from native_qualification_lib import run

    pid_file = tmp_path / "normal-child.pid"
    child = "import time;time.sleep(60)"
    parent = (
        "import os,pathlib,subprocess,sys;flags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0);"
        + f"p=subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=os.name!='nt',creationflags=flags if os.name=='nt' else 0);"
        + f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid))"
    )
    rc, _, _, duration = run(
        [sys.executable, "-c", parent], cwd=tmp_path, env=dict(os.environ), timeout=5
    )
    child_pid = int(pid_file.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and pid_is_live(child_pid):
        time.sleep(0.05)
    assert (rc, pid_is_live(child_pid)) == (0, False)
    assert duration < 5
