"""Contracts for the NO1-006A native package qualification subsystem."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "qualify_native_install.py"
SCHEMA_PATH = ROOT / "rfcs" / "schemas" / "no1-006a-native-attestation-v1.schema.json"
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


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _workflow() -> dict[str, str]:
    return {
        "event": "pull_request",
        "run_id": "123",
        "run_attempt": "1",
        "job": "native",
        "workflow_ref": "owner/repo/.github/workflows/native-install-qualification.yml@refs/pull/1/merge",
        "run_url": "https://github.com/owner/repo/actions/runs/123",
    }


def _report(axis: str, wheel_sha: str | None = None) -> dict[str, object]:
    digest = wheel_sha or "a" * 64
    system = {"linux": "Linux", "macos": "Darwin", "windows": "Windows"}[axis]
    return {
        "schema_version": "no1-006a-native-attestation-v1",
        "kind": "axis",
        "qualification_id": "NO1-006A",
        "evidence_scope": "native_package_mcp_first_answer",
        "axis": axis,
        "qualification_performed": True,
        "passed": True,
        "source": {
            "repository": "owner/repo",
            "commit": "b" * 40,
            "ref": "refs/pull/1/merge",
            "dirty": False,
        },
        "workflow": _workflow(),
        "runner": {
            "declared_axis": axis,
            "observed_system": system,
            "release": "1",
            "machine": "x86_64",
            "image_os": "image",
            "image_version": "1",
        },
        "wheel": {
            "filename": "tree_sitter_analyzer-1-py3-none-any.whl",
            "sha256": digest,
            "size": 10,
            "name": "tree-sitter-analyzer",
            "version": "1",
        },
        "stages": [
            {"id": "verify_wheel", "passed": True},
            {"id": "install", "passed": True},
            {"id": "metadata_provenance", "passed": True},
            {"id": "mcp_protocol", "passed": True},
        ],
        "failure": None,
        "build_manifest_sha256": "c" * 64,
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
            "version": "1",
            "location": "/venv/site-packages",
            "module_file": "/venv/site-packages/tree_sitter_analyzer/__init__.py",
            "distribution_outside_checkout": True,
            "executable_in_fresh_venv": True,
        },
        "runtime": {"python": "3.10.0", "executable": "/venv/bin/python"},
        "mcp": {
            "executable": "/venv/bin/tree-sitter-analyzer-mcp",
            "protocol_version": "2025-06-18",
            "server_name": "tree-sitter-analyzer-mcp",
            "server_version": "1",
            "tools": TOOLS,
            "first_call": {
                "name": "index",
                "arguments": {"action": "status"},
                "is_error": False,
                "default_format": "toon",
                "verdict": "WARN",
            },
            "duration_seconds": 1.0,
            "transcript_sha256": "f" * 64,
            "stderr_sha256": "0" * 64,
        },
        "dependency_manifest_sha256": "1" * 64,
    }


def _aggregate(
    tmp_path: Path, reports: list[dict[str, object]], *, trusted: bool = False
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    paths = []
    for report in reports:
        path = tmp_path / f"{report['axis']}.json"
        path.write_text(json.dumps(report))
        paths.append(str(path))
    output = tmp_path / "aggregate.json"
    command = [
        sys.executable,
        str(SCRIPT),
        "aggregate",
        "--schema",
        str(SCHEMA_PATH),
        "--reports",
        *paths,
        "--output",
        str(output),
    ]
    if trusted:
        command.append("--trusted")
    env = {
        **os.environ,
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_REF": "refs/pull/1/merge",
    }
    result = subprocess.run(
        command, capture_output=True, text=True, env=env, check=False
    )
    return result, json.loads(output.read_text())


def test_schema_rejects_unknown_trust_boundary_field() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    report = _report("linux")
    report["self_attested"] = True
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(report))
    assert [error.validator for error in errors] == ["oneOf"]


def test_aggregate_accepts_exact_three_axis_candidate(tmp_path: Path) -> None:
    result, aggregate = _aggregate(
        tmp_path, [_report(axis) for axis in ("linux", "macos", "windows")]
    )
    assert result.returncode == 0
    assert aggregate["native_axes_qualified"] is True
    assert aggregate["qualified"] is False
    assert aggregate["evidence_trust"] == "UNTRUSTED_CANDIDATE"
    assert [item["axis"] for item in aggregate["axes"]] == ["linux", "macos", "windows"]


def test_aggregate_rejects_wheel_digest_drift(tmp_path: Path) -> None:
    result, aggregate = _aggregate(
        tmp_path, [_report("linux"), _report("macos"), _report("windows", "2" * 64)]
    )
    assert result.returncode == 1
    assert aggregate["failures"] == ["wheel digest mismatch or malformed"]
    assert aggregate["native_axes_qualified"] is False


def test_pull_request_cannot_request_trusted_aggregation(tmp_path: Path) -> None:
    result, aggregate = _aggregate(
        tmp_path,
        [_report(axis) for axis in ("linux", "macos", "windows")],
        trusted=True,
    )
    assert result.returncode == 1
    assert aggregate["qualified"] is False
    assert aggregate["failures"] == [
        "trusted aggregation is restricted to develop pushes"
    ]


def test_probe_uses_official_mcp_client_and_preserves_toon_default() -> None:
    probe = (ROOT / "scripts" / "native_mcp_probe.py").read_text()
    assert "from mcp import ClientSession, StdioServerParameters" in probe
    assert "from mcp.client.stdio import stdio_client" in probe
    assert 'call_tool("index", {"action": "status"})' in probe
    assert 'envelope["format"] == "toon"' in probe


def test_workflow_pins_native_floor_axes_and_develop_only_attestation() -> None:
    workflow = (ROOT / ".github/workflows/native-install-qualification.yml").read_text()
    assert workflow.count("runner: ubuntu-24.04") == 1
    assert workflow.count("runner: macos-14") == 1
    assert workflow.count("runner: windows-2022") == 1
    assert workflow.count('python-version: "3.10"') == 3
    assert workflow.count("actions/attest-build-provenance@v3") == 2
    assert (
        workflow.count(
            "github.event_name == 'push' && github.ref == 'refs/heads/develop'"
        )
        == 3
    )
