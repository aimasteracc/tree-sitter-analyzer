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


def workflow(event: str, job: str = "native") -> dict[str, str]:
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
    rows = [[name, "", str(len(data))] for name, data in files.items()]
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
        "workflow": workflow(event, "build"),
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
                "archive_info": {"hash": "sha256=" + "a" * 64},
            },
            "direct_url_path": "/venv/site-packages/x.dist-info/direct_url.json",
            "module_recorded": True,
            "all_paths_in_fresh_venv": True,
            "direct_url_sha256": "a" * 64,
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
