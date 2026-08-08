"""Trusted-attestation forgery fixture runner."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

from _test_native_qualification_helpers import (
    ROOT,
    _rewrite_snapshot_direct,
    github_env,
    manifest,
    report,
    sha,
    workflow,
    write_trusted_axis_artifacts,
)


def trusted_verifier_result(tmp_path: Path, mutation: str) -> int:
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
    for axis, value in report_values.items():
        write_trusted_axis_artifacts(trusted / axis, value, wheel)
    wheel_name = wheel.name
    if mutation == "filename_metadata":
        wheel_name = "other_project-1.0-py3-none-any.whl"
        (trusted / "build" / wheel.name).rename(trusted / "build" / wheel_name)
        copied_manifest = json.loads(
            (trusted / "build" / "wheel-manifest.json").read_text()
        )
        copied_manifest["wheel"]["filename"] = wheel_name
        (trusted / "build" / "wheel-manifest.json").write_text(
            json.dumps(copied_manifest)
        )
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
    elif mutation == "installed_member_hash":
        report_values["linux"]["metadata"]["installed_record"]["files"][0]["sha256"] = (
            "a" * 64
        )
    elif mutation == "installed_member_size":
        report_values["linux"]["metadata"]["installed_record"]["files"][0]["size"] = 1
    elif mutation == "installed_record_digest":
        report_values["linux"]["metadata"]["installed_record"]["record_sha256"] = (
            "a" * 64
        )
    elif mutation == "installed_inventory":
        report_values["linux"]["metadata"]["installed_record"]["files"].pop()
        report_values["linux"]["metadata"]["installed_record"]["entry_count"] -= 1
    elif mutation == "side_artifact":
        (trusted / "linux" / "install.stdout").write_bytes(b"forged")
    elif mutation == "path_containment":
        report_values["linux"]["metadata"]["module_file"] = (
            "/checkout/tree_sitter_analyzer/__init__.py"
        )
        report_values["linux"]["metadata"]["module_origin"] = (
            "/checkout/tree_sitter_analyzer/__init__.py"
        )
    elif mutation in {"zip_extra", "zip_symlink"}:
        snapshot = trusted / "linux" / "installed-files.zip"
        with zipfile.ZipFile(snapshot, "a") as archive:
            info = zipfile.ZipInfo("../escape" if mutation == "zip_extra" else "link")
            if mutation == "zip_symlink":
                info.external_attr = 0o120777 << 16
            archive.writestr(info, b"forged")
        report_values["linux"]["installed_files_zip_sha256"] = sha(snapshot)
    elif mutation in {"direct_base64", "snapshot_direct"}:
        value = report_values["linux"]
        if mutation == "direct_base64":
            digest = bytes.fromhex(value["wheel"]["sha256"])
            encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
            value["metadata"]["direct_url"]["archive_info"]["hash"] = (
                "sha256=" + encoded + "!!"
            )
        forged = (
            value["metadata"]["direct_url"]
            if mutation == "direct_base64"
            else {"url": "file:///forged.whl", "archive_info": {}}
        )
        _rewrite_snapshot_direct(trusted / "linux", value, forged)
    elif mutation in {"transcript_error", "transcript_missing"}:
        transcript = trusted / "linux" / "mcp-transcript.ndjson"
        events = [json.loads(line) for line in transcript.read_text().splitlines()]
        if mutation == "transcript_error":
            events[2]["response"]["isError"] = True
        else:
            events.pop()
        transcript.write_text("".join(json.dumps(event) + "\n" for event in events))
        report_values["linux"]["mcp"]["transcript_sha256"] = sha(transcript)
    elif mutation in {"path_dotdot_posix", "path_dotdot_windows"}:
        value = report_values["linux"]
        if mutation == "path_dotdot_posix":
            escaped = (
                "/tmp/tsa-native-qualification-test-linux/venv/../outside/module.py"
            )
            value["metadata"]["module_file"] = value["metadata"]["module_origin"] = (
                escaped
            )
        else:
            root, prefix = (
                r"C:\tmp\tsa-native-qualification-test-linux",
                r"C:\tmp\tsa-native-qualification-test-linux\venv",
            )
            value["runtime"].update(
                prefix=prefix, executable=prefix + r"\Scripts\python.exe"
            )
            value["metadata"].update(
                location=prefix + r"\site-packages",
                module_file=prefix + r"\..\outside\module.py",
                module_origin=prefix + r"\..\outside\module.py",
                direct_url_path=prefix
                + r"\site-packages\pkg.dist-info\direct_url.json",
            )
            value["metadata"]["installed_record"]["record_path"] = (
                prefix + r"\site-packages\pkg.dist-info\RECORD"
            )
            value["mcp"]["executable"] = (
                prefix + r"\Scripts\tree-sitter-analyzer-mcp.exe"
            )
            value["mcp"]["first_call"]["project_root"] = root + r"\fixture"
            transcript = trusted / "linux" / "mcp-transcript.ndjson"
            events = [json.loads(line) for line in transcript.read_text().splitlines()]
            envelope = json.loads(events[2]["response"]["content"][0]["text"])
            envelope["project_root"] = value["mcp"]["first_call"]["project_root"]
            events[2]["response"]["content"][0]["text"] = json.dumps(envelope)
            transcript.write_text("".join(json.dumps(event) + "\n" for event in events))
            value["mcp"]["transcript_sha256"] = sha(transcript)
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
        ROOT / ".github/workflows/reusable-native-qualification-attestation.yml"
    ).read_text()
    code = workflow_text.split("          python - <<'PY'\n", 1)[1].split(
        "\n          PY", 1
    )[0]
    environment = github_env("push") | {"WHEEL_NAME": wheel_name}
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode
