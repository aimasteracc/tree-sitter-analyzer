"""Adversarial contracts for content-bound outdated-uv qualification."""

from __future__ import annotations

import io
import json
import os
import signal
import sys
import tarfile
import time
import zipfile
from pathlib import Path

import jsonschema
import psutil
import pytest

from scripts import qualify_outdated_uv as qualification

sys.path.insert(0, str(Path(__file__).parent))
from _native_trusted_verifier_helpers import outdated_causal_fixture  # noqa: E402

ROOT = Path(__file__).parents[2]
SCHEMA = json.loads(
    (ROOT / "rfcs/schemas/no1-006a-outdated-uv-attestation-v3.schema.json").read_text()
)


def test_fixture_allowlist_pins_exact_official_archive_bytes() -> None:
    fixtures = qualification.allowlist()["fixtures"]
    assert fixtures["linux-0.10.9"] == {
        "axis": "linux",
        "filename": "uv-x86_64-unknown-linux-gnu.tar.gz",
        "sha256": "20d79708222611fa540b5c9ed84f352bcd3937740e51aacc0f8b15b271c57594",
        "size": 22790272,
        "url": "https://github.com/astral-sh/uv/releases/download/0.10.9/uv-x86_64-unknown-linux-gnu.tar.gz",
        "version": "0.10.9",
    }
    assert (
        fixtures["macos-arm64-0.11.0"]["sha256"]
        == "0c0f32c6a3473c5928aff96c3233715edfc79290e892f255cac93710cde7b91a"
    )
    assert (
        fixtures["windows-0.10.9"]["sha256"]
        == "f58dc40896000229db7c52b8bdd931394040ef2ad59abd1eda841f6d70b13d7a"
    )


def test_clean_environment_drops_host_uv_python_xdg_and_shell_injection(
    tmp_path: Path,
) -> None:
    environment = qualification.clean_env(tmp_path / "home", tmp_path, "/fixed", True)
    assert environment["PATH"] == "/fixed"
    assert environment["TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP"] == "1"
    assert environment["PYTHONPATH"] == environment["PYTHONHOME"] == ""
    assert environment["XDG_CONFIG_HOME"].startswith(str(tmp_path))
    assert not (
        {"BASH_ENV", "UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV"} & environment.keys()
    )


@pytest.mark.skipif(
    os.name == "nt", reason="tracked: POSIX installer process-group cleanup"
)
def test_installer_timeout_reaps_entire_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    command = [
        "/bin/bash",
        "-c",
        f"(trap '' TERM; sleep 60) & echo $! > {pid_file}; wait",
    ]
    with pytest.raises(TimeoutError, match="process tree timed out and was reaped"):
        qualification.run_tree(command, tmp_path, os.environ.copy(), 0.2)
    pid = int(pid_file.read_text())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            child = psutil.Process(pid)
            if not child.is_running() or child.status() == psutil.STATUS_ZOMBIE:
                break
        except psutil.NoSuchProcess:
            break
        time.sleep(0.05)
    else:
        os.kill(pid, signal.SIGKILL)
        raise AssertionError("installer descendant survived bounded cleanup")


def valid_windows_report() -> dict[str, object]:
    report = valid_passed_report()
    report.update(
        axis="windows",
        qualification_performed=False,
        passed=False,
        status="NOT_APPLICABLE_NO_NATIVE_INSTALLER",
        supported_uv=None,
        installer=None,
        config=None,
        mcp_causal_report=None,
        failure={"type": "NotApplicable", "message": "manual remediation"},
    )
    report["runner"].update(declared_axis="windows", observed_system="Windows")
    report["artifacts"] = {"old.archive": {"sha256": "a" * 64, "size": 0}}
    return report


def test_schema_rejects_windows_pass_and_mutable_bootstrap_claim() -> None:
    report = valid_windows_report()
    jsonschema.validate(report, SCHEMA)
    report["passed"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)
    report = valid_windows_report()
    report["automatic_mutable_bootstrap_qualified"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)


def test_windows_na_requires_exact_old_archive_artifact() -> None:
    report = valid_windows_report()
    report["artifacts"]["empty.stderr"] = {"sha256": "0" * 64, "size": 0}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)
    for field in ("old_uv", "package_qualification"):
        invalid = valid_windows_report()
        invalid[field] = {}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, SCHEMA)


def test_passed_schema_requires_every_platform_artifact() -> None:
    # PR #1242: PASSED POSIX evidence must retain every causal sidecar.
    report = valid_passed_report()
    del report["artifacts"]["installed-mcp-config.json"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)


def test_passed_schema_rejects_artifacts_outside_exact_allowlist() -> None:
    # Final gate 2026-07-17: POSIX evidence is exactly the 17 protocol files.
    report = valid_passed_report()
    report["artifacts"]["extra.bin"] = {"sha256": "a" * 64, "size": 0}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)


def test_windows_na_schema_requires_old_archive_artifact() -> None:
    # PR #1242: Windows N/A still executes and retains the old uv fixture.
    report = valid_windows_report()
    report["artifacts"] = {}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)


def test_schema_accepts_driver_windows_failed_state() -> None:
    # PR #1242: Windows exceptions retain qualification_performed=false.
    report = qualification.base_report("windows")
    report.update(
        status="FAILED",
        failure={"type": "ValueError", "message": "fixture rejected"},
    )
    report["runner"].update(declared_axis="windows", observed_system="Windows")
    jsonschema.validate(report, SCHEMA)


def test_schema_rejects_windows_failed_as_performed() -> None:
    # PR #1242: Windows has no native installer qualification to perform.
    report = qualification.base_report("windows")
    report.update(
        status="FAILED",
        qualification_performed=True,
        failure={"type": "ValueError", "message": "fixture rejected"},
    )
    report["runner"].update(declared_axis="windows", observed_system="Windows")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)


def test_windows_dot_archive_dispatches_allowlisted_zip_content(tmp_path: Path) -> None:
    archive = tmp_path / "old.archive"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("bundle/uv.exe", b"fixture")
    executable = qualification.safe_extract(
        archive, tmp_path / "output", "uv-x86_64-pc-windows-msvc.zip"
    )
    assert executable.read_bytes() == b"fixture"


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "device", "traversal"])
def test_safe_extract_rejects_unsafe_tar_members(tmp_path: Path, kind: str) -> None:
    # Incident 2026-07-15: archive extraction must fail closed without assert.
    archive = tmp_path / "old.archive"
    with tarfile.open(archive, "w:gz") as value:
        member = tarfile.TarInfo("../escape" if kind == "traversal" else "bundle/bad")
        if kind == "symlink":
            member.type, member.linkname = tarfile.SYMTYPE, "/tmp/outside"
        elif kind == "hardlink":
            member.type, member.linkname = tarfile.LNKTYPE, "bundle/uv"
        elif kind == "device":
            member.type = tarfile.CHRTYPE
        else:
            member.size = 1
        value.addfile(member, io.BytesIO(b"x") if member.isreg() else None)
    with pytest.raises(ValueError, match="unsafe"):
        qualification.safe_extract(
            archive, tmp_path / "output", "uv-x86_64-unknown-linux-gnu.tar.gz"
        )


def test_schema_rejects_impossible_failed_axis_and_aggregate() -> None:
    axis = qualification.base_report("linux")
    axis.update({"status": "FAILED", "passed": True, "failure": None})
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(axis, SCHEMA)
    aggregate = {
        "schema_version": qualification.SCHEMA_VERSION,
        "kind": "outdated_uv_aggregate",
        "qualification_id": "NO1-006A",
        "evidence_scope": "native_outdated_uv_actionable_recovery",
        "qualification_performed": True,
        "qualified": False,
        "evidence_trust": "EXTERNAL_ATTESTATION_REQUIRED",
        "source_commit": "0" * 40,
        "package_qualification": {},
        "required_axes": {
            "package": ["linux", "macos", "windows"],
            "outdated": ["linux", "macos"],
            "not_applicable": {"windows": "NOT_APPLICABLE_NO_NATIVE_INSTALLER"},
        },
        "automatic_mutable_bootstrap_qualified": False,
        "axes": [{}, {}, {}],
        "failures": ["fatal"],
        "workflow": qualification.identity("outdated-uv-aggregate")[1],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(aggregate, SCHEMA)


def test_workflow_routes_fixture_manifest_and_all_attestation_schemas() -> None:
    workflow = (ROOT / ".github/workflows/native-install-qualification.yml").read_text()
    assert workflow.count('"config/no1_uv_fixtures.json"') == 2
    assert workflow.count('"rfcs/schemas/no1-006a-*-attestation-*.schema.json"') == 2
    assert workflow.count('"install.ps1"') == 2


def test_trusted_verifier_requires_complete_windows_na_state() -> None:
    # PR #1242: trusted verification must not bless a schema-invalid N/A report.
    trusted = (
        ROOT / ".github/workflows/reusable-native-qualification-attestation.yml"
    ).read_text()
    assert 'report["failure"]=={"type":"NotApplicable"' in trusted
    assert 'report["installer"] is None and report["config"] is None' in trusted


def test_workflow_separates_read_only_verification_from_tiny_oidc_job() -> None:
    trusted = (
        ROOT / ".github/workflows/reusable-native-qualification-attestation.yml"
    ).read_text()
    read_only, tiny = trusted.split("  tiny-attestation:", 1)
    assert "id-token: write" not in read_only and "attestations: write" not in read_only
    assert tiny.count("id-token: write") == tiny.count("attestations: write") == 1
    assert "actions/checkout" not in trusted
    assert "@v" not in trusted
    assert "automatic_mutable_bootstrap_qualified" in trusted


def test_supported_uv_is_the_exact_wheel_install_tool() -> None:
    source = (ROOT / "scripts/qualify_native_install.py").read_text()
    assert 'os.environ.get("TSA_QUALIFICATION_UV")' in source
    assert '"pip", "install", "--python"' in source
    workflow = (
        ROOT / ".github/workflows/reusable-outdated-uv-qualification.yml"
    ).read_text()
    assert "setup-uv" not in workflow
    assert "--version 0.11.0" in workflow


def valid_passed_report() -> dict[str, object]:
    report = qualification.base_report("linux")
    report["runner"]["observed_system"] = "Linux"
    digest = "a" * 64
    wheel = {
        "filename": "tree_sitter_analyzer-1.0-py3-none-any.whl",
        "sha256": digest,
        "size": 1,
        "name": "tree-sitter-analyzer",
        "version": "1.0",
    }

    def executable(version: str, path: str) -> dict[str, object]:
        return {
            "version": version,
            "path": path,
            "sha256": digest,
            "size": 1,
            "version_stdout": f"uv {version}\n",
        }

    runner = dict(report["runner"])
    report.update(
        status="PASSED",
        passed=True,
        old_uv={
            "archive": {
                "filename": "uv-x86_64-unknown-linux-gnu.tar.gz",
                "url": "https://github.com/astral-sh/uv/releases/download/0.10.9/uv.tar.gz",
                "version": "0.10.9",
                "size": 1,
                "sha256": digest,
            },
            "executable": executable(
                "0.10.9", "/tmp/tsa-outdated-native-test/old/bundle/uv"
            ),
        },
        supported_uv={
            "archive": {
                "filename": "uv-x86_64-unknown-linux-gnu.tar.gz",
                "url": "https://github.com/astral-sh/uv/releases/download/0.11.0/uv.tar.gz",
                "version": "0.11.0",
                "size": 1,
                "sha256": digest,
            },
            "executable": executable(
                "0.11.0", "/tmp/tsa-outdated-native-test/supported/bundle/uv"
            ),
        },
        installer={
            "path": "/checkout/install.sh",
            "sha256": digest,
            "first_exit": 1,
            "second_exit": 0,
            "curl_invocations": 0,
            "first_path": "/tmp/tsa-outdated-native-test/old/bundle:/tmp/tsa-outdated-native-test/tools",
            "second_path": "/tmp/tsa-outdated-native-test/supported/bundle:/tmp/tsa-outdated-native-test/tools",
            "curated_tools": list(qualification.REQUIRED_COMMANDS),
        },
        config={
            "before": [],
            "after_first": [],
            "after_second": [],
            "expected_entry": {
                "command": "uvx",
                "args": [
                    "--from",
                    "tree-sitter-analyzer[mcp]",
                    "tree-sitter-analyzer-mcp",
                ],
                "env": {
                    "TREE_SITTER_PROJECT_ROOT": "/tmp/tsa-outdated-native-test/fixture"
                },
            },
            "backup_sha256": digest,
        },
        package_qualification={
            "aggregate_sha256": digest,
            "axis_report_sha256": digest,
            "build_manifest_sha256": digest,
            "wheel": wheel,
        },
        mcp_causal_report={
            "sha256": digest,
            "wheel": wheel,
            "runner": runner,
            "first_call": {
                "name": "index",
                "arguments": {"action": "status"},
                "is_error": False,
                "default_format": "toon",
                "verdict": "WARN",
                "project_root": "/tmp/project",
                "indexed": False,
                "total_files": 0,
                "summary": "codegraph_status: index missing or empty",
            },
            "install_tool": executable(
                "0.11.0", "/tmp/tsa-outdated-native-test/supported/bundle/uv"
            ),
            "install_argv": [
                "/tmp/supported/bundle/uv",
                "pip",
                "install",
                "--python",
                "/tmp/venv/bin/python",
                "--no-cache",
                "/tmp/tree_sitter_analyzer-1.0-py3-none-any.whl[mcp]",
            ],
            "install_stdout_sha256": digest,
            "install_stderr_sha256": digest,
            "dependency_manifest_sha256": digest,
        },
    )
    artifact_names = (
        "old.archive",
        "supported.archive",
        "installer.source",
        "installed-mcp-config.json",
        "first.stdout",
        "first.stderr",
        "second.stdout",
        "second.stderr",
        "mcp-driver.stdout",
        "mcp-driver.stderr",
        "mcp/report.json",
        "mcp/install.stdout",
        "mcp/install.stderr",
        "mcp/dependency-manifest.txt",
        "mcp/mcp-transcript.ndjson",
        "mcp/mcp.stderr",
        "mcp/installed-files.zip",
    )
    report["artifacts"] = {
        name: {"sha256": digest, "size": 0} for name in artifact_names
    }
    return report


def test_successful_aggregate_requires_complete_package_binding() -> None:
    # PR #1242: successful aggregate evidence must bind the wheel and manifest.
    digest = "0" * 64
    axis_package = valid_passed_report()["package_qualification"]
    package = {
        **{
            key: axis_package[key]
            for key in ("aggregate_sha256", "build_manifest_sha256", "wheel")
        },
        "axis_report_sha256": dict.fromkeys(
            qualification.AXES, axis_package["axis_report_sha256"]
        ),
    }
    aggregate = {
        "schema_version": qualification.SCHEMA_VERSION,
        "kind": "outdated_uv_aggregate",
        "qualification_id": "NO1-006A",
        "evidence_scope": "native_outdated_uv_actionable_recovery",
        "qualification_performed": True,
        "qualified": False,
        "evidence_trust": "EXTERNAL_ATTESTATION_REQUIRED",
        "source_commit": "0" * 40,
        "package_qualification": package,
        "required_axes": {
            "package": ["linux", "macos", "windows"],
            "outdated": ["linux", "macos"],
            "not_applicable": {"windows": "NOT_APPLICABLE_NO_NATIVE_INSTALLER"},
        },
        "automatic_mutable_bootstrap_qualified": False,
        "axes": [
            {
                "axis": "linux",
                "report_sha256": digest,
                "status": "PASSED",
                "passed": True,
            },
            {
                "axis": "macos",
                "report_sha256": digest,
                "status": "PASSED",
                "passed": True,
            },
            {
                "axis": "windows",
                "report_sha256": digest,
                "status": "NOT_APPLICABLE_NO_NATIVE_INSTALLER",
                "passed": False,
            },
        ],
        "failures": [],
        "workflow": qualification.identity("outdated-uv-aggregate")[1],
    }
    jsonschema.validate(aggregate, SCHEMA)
    aggregate["package_qualification"] = {}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(aggregate, SCHEMA)


def aggregate_reports(tmp_path: Path) -> tuple[list[dict[str, object]], list[Path]]:
    linux = valid_passed_report()
    macos = valid_passed_report()
    macos["axis"] = "macos"
    macos["runner"].update(declared_axis="macos", observed_system="Darwin")
    macos["mcp_causal_report"]["runner"].update(
        declared_axis="macos", observed_system="Darwin"
    )
    values = [linux, macos, valid_windows_report()]
    paths = []
    for axis_name, value in zip(qualification.AXES, values, strict=True):
        path = tmp_path / f"{axis_name}.json"
        path.write_text(json.dumps(value), "utf-8")
        paths.append(path)
    return values, paths


def run_aggregate(tmp_path: Path, paths: list[Path]) -> tuple[int, dict[str, object]]:
    from types import SimpleNamespace

    output = tmp_path / "aggregate.json"
    result = qualification.aggregate(
        SimpleNamespace(
            output=str(output),
            reports=[str(path) for path in paths],
            schema=str(
                ROOT / "rfcs/schemas/no1-006a-outdated-uv-attestation-v3.schema.json"
            ),
            trusted=False,
        )
    )
    return result, json.loads(output.read_text("utf-8"))


@pytest.mark.parametrize("schema_state", ["missing", "malformed", "invalid"])
def test_aggregate_retains_untrusted_report_when_schema_cannot_load(
    tmp_path: Path, schema_state: str
) -> None:
    # PR #1242: schema boundary failures must remain as atomic aggregate evidence.
    from types import SimpleNamespace

    schema_path = tmp_path / "schema.json"
    if schema_state == "malformed":
        schema_path.write_text("{", "utf-8")
    elif schema_state == "invalid":
        schema_path.write_text(json.dumps({"type": 7}), "utf-8")
    output = tmp_path / "aggregate.json"
    result = qualification.aggregate(
        SimpleNamespace(
            output=str(output),
            reports=["unused"] * 3,
            schema=str(schema_path),
            trusted=True,
        )
    )
    aggregate = json.loads(output.read_text("utf-8"))
    assert result == 1
    assert aggregate["evidence_trust"] == "UNTRUSTED_CANDIDATE"
    assert aggregate["qualification_performed"] is False
    assert len(aggregate["failures"]) == 1
    assert aggregate["failures"][0].startswith("schema: ")
    assert not output.with_suffix(".json.tmp").exists()


def test_aggregate_preserves_all_package_axis_report_bindings(tmp_path: Path) -> None:
    values, paths = aggregate_reports(tmp_path)
    result, aggregate = run_aggregate(tmp_path, paths)
    package = aggregate["package_qualification"]
    assert result == 0
    assert package == {
        "aggregate_sha256": "a" * 64,
        "axis_report_sha256": {
            axis_name: value["package_qualification"]["axis_report_sha256"]
            for axis_name, value in zip(qualification.AXES, values, strict=True)
        },
        "build_manifest_sha256": "a" * 64,
        "wheel": values[0]["package_qualification"]["wheel"],
    }
    jsonschema.validate(aggregate, SCHEMA)


def test_aggregate_rejects_schema_incomplete_axis_report(tmp_path: Path) -> None:
    values, paths = aggregate_reports(tmp_path)
    del values[0]["old_uv"]
    paths[0].write_text(json.dumps(values[0]), "utf-8")
    result, aggregate = run_aggregate(tmp_path, paths)
    assert result == 1
    assert aggregate["failures"][0].startswith("linux: ValidationError:")


@pytest.mark.parametrize(
    "field",
    [
        "old_uv",
        "supported_uv",
        "installer",
        "config",
        "package_qualification",
        "mcp_causal_report",
    ],
)
def test_passed_schema_rejects_empty_semantic_object(field: str) -> None:
    # Incident 2026-07-16: v2 accepted impossible PASSED reports with empty evidence.
    report = valid_passed_report()
    jsonschema.validate(report, SCHEMA)
    report[field] = {}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)


def test_passed_schema_rejects_supported_uv_below_floor() -> None:
    # Incident 2026-07-16: v2 accepted supported uv 0.0.1 below the 0.11.0 floor.
    report = valid_passed_report()
    report["supported_uv"]["executable"]["version"] = "0.0.1"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)


@pytest.mark.parametrize("location", ["runner", "mcp_causal_report"])
def test_passed_schema_rejects_cross_axis_runner(location: str) -> None:
    # Incident 2026-07-16: Linux evidence could self-identify as a macOS runner.
    report = valid_passed_report()
    target = report[location]
    if location == "mcp_causal_report":
        target = target["runner"]
    target.update(declared_axis="macos", observed_system="Darwin")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)


def trusted_helpers() -> dict[str, object]:
    import textwrap

    workflow = (
        ROOT / ".github/workflows/reusable-native-qualification-attestation.yml"
    ).read_text()
    code = workflow.split("          python - <<'PY'\n")[2].split(
        "          official={", 1
    )[0]
    code = "\n".join(
        line
        for line in code.splitlines()
        if not line.lstrip().startswith(("root=", "suffix="))
    )
    namespace: dict[str, object] = {}
    exec(textwrap.dedent(code), namespace)
    return namespace


@pytest.mark.parametrize("mutation", ["traversal", "duplicate"])
def test_trusted_archive_unpack_rejects_non_unique_or_unsafe_uv(
    tmp_path: Path, mutation: str
) -> None:
    # Incident 2026-07-16: trusted verification must recompute one safe uv member.
    archive = tmp_path / "uv.tar.gz"
    with tarfile.open(archive, "w:gz") as value:
        names = ["../uv"] if mutation == "traversal" else ["a/uv", "b/uv"]
        for name in names:
            member = tarfile.TarInfo(name)
            member.size = 1
            value.addfile(member, io.BytesIO(b"x"))
    with pytest.raises((AssertionError, ValueError)):
        trusted_helpers()["safe_uv_member"](
            archive, "uv-x86_64-unknown-linux-gnu.tar.gz"
        )


def test_trusted_archive_member_digest_binds_reported_executable(
    tmp_path: Path,
) -> None:
    # Incident 2026-07-16: candidate tool digest could previously be self-attested.
    archive = tmp_path / "uv.tar.gz"
    with tarfile.open(archive, "w:gz") as value:
        member = tarfile.TarInfo("bundle/uv")
        member.size = 1
        value.addfile(member, io.BytesIO(b"x"))
    helpers = trusted_helpers()
    observed = helpers["safe_uv_member"](archive, "uv-x86_64-unknown-linux-gnu.tar.gz")
    executable = {
        "version": "0.11.0",
        "path": "/tmp/supported/bundle/uv",
        "sha256": "0" * 64,
        "size": 1,
        "version_stdout": "uv 0.11.0\n",
    }
    with pytest.raises(AssertionError):
        helpers["verify_executable"](executable, observed, "0.11.0", "linux")


def test_trusted_config_sidecar_accepts_noncanonical_format(tmp_path: Path) -> None:
    # Run 31284682751: formatting must not substitute for observed config bytes.
    config = valid_passed_report()["config"]
    value = {"mcpServers": {"tree-sitter-analyzer": config["expected_entry"]}}
    data = json.dumps(value, separators=(",", ":")).encode()
    (tmp_path / "installed-mcp-config.json").write_bytes(data)
    after = {
        ".claude/.mcp.json": {
            "path": ".claude/.mcp.json",
            "type": "file",
            "sha256": qualification.hashlib.sha256(data).hexdigest(),
        }
    }
    assert (
        trusted_helpers()["verify_config_sidecar"](
            tmp_path,
            config,
            after,
            "linux",
            "📁 Project root: /tmp/tsa-outdated-native-test/fixture\n",
            Path("/tmp/tsa-outdated-native-test"),
        )
        is None
    )


@pytest.mark.parametrize("mutation", ["duplicate", "extra", "entry", "snapshot"])
def test_trusted_config_sidecar_rejects_forgery(tmp_path: Path, mutation: str) -> None:
    # Run 31284682751: trusted verification parses and binds the actual sidecar.
    config = valid_passed_report()["config"]
    expected = {"mcpServers": {"tree-sitter-analyzer": config["expected_entry"]}}
    if mutation == "duplicate":
        body = json.dumps(expected["mcpServers"])
        data = f'{{"mcpServers":{body},"mcpServers":{body}}}'.encode()
    else:
        forged = json.loads(json.dumps(expected))
        if mutation == "extra":
            forged["extra"] = True
        elif mutation == "entry":
            forged["mcpServers"]["tree-sitter-analyzer"]["command"] = "forged"
        data = json.dumps(forged).encode()
    digest = (
        "0" * 64
        if mutation == "snapshot"
        else qualification.hashlib.sha256(data).hexdigest()
    )
    (tmp_path / "installed-mcp-config.json").write_bytes(data)
    after = {
        ".claude/.mcp.json": {
            "path": ".claude/.mcp.json",
            "type": "file",
            "sha256": digest,
        }
    }
    with pytest.raises(AssertionError):
        trusted_helpers()["verify_config_sidecar"](
            tmp_path,
            config,
            after,
            "linux",
            "📁 Project root: /tmp/tsa-outdated-native-test/fixture\n",
            Path("/tmp/tsa-outdated-native-test"),
        )


def test_trusted_config_rejects_coordinated_command_forgery(tmp_path: Path) -> None:
    # Final gate 2026-07-17: candidate config and sidecar cannot define the oracle.
    config = json.loads(json.dumps(valid_passed_report()["config"]))
    config["expected_entry"]["command"] = "evil"
    value = {"mcpServers": {"tree-sitter-analyzer": config["expected_entry"]}}
    data = json.dumps(value).encode()
    (tmp_path / "installed-mcp-config.json").write_bytes(data)
    after = {
        ".claude/.mcp.json": {
            "path": ".claude/.mcp.json",
            "type": "file",
            "sha256": qualification.hashlib.sha256(data).hexdigest(),
        }
    }
    with pytest.raises(AssertionError):
        trusted_helpers()["verify_config_sidecar"](
            tmp_path,
            config,
            after,
            "linux",
            "📁 Project root: /tmp/tsa-outdated-native-test/fixture\n",
            Path("/tmp/tsa-outdated-native-test"),
        )


@pytest.mark.parametrize(
    "stdout",
    [
        "📁 Project root: /tmp/tsa-outdated-native-a/fixture\n"
        "📁 Project root: /tmp/tsa-outdated-native-b/fixture\n",
        "📁 Project root: /tmp/other/fixture\n",
        "📁 Project root: /tmp/tsa-outdated-native-a/fixture/../fixture\n",
        "📁 Project root: relative/tsa-outdated-native-a/fixture\n",
    ],
)
def test_trusted_stdout_rejects_ambiguous_or_unstructured_root(stdout: str) -> None:
    # Final gate 2026-07-17: the hash-bound stdout uniquely defines the root.
    with pytest.raises(AssertionError):
        trusted_helpers()["project_root_from_stdout"](
            stdout, "linux", Path("/tmp/tsa-outdated-native-a")
        )


@pytest.mark.parametrize(
    "items",
    [
        [
            {"path": "a", "type": "file", "sha256": "a" * 64},
            {"path": "a", "type": "file", "sha256": "b" * 64},
        ],
        [{"path": "a", "type": "dir", "sha256": "a" * 64}],
        [{"path": "a", "type": "file", "sha256": None}],
        [{"path": "../a", "type": "file", "sha256": "a" * 64}],
        [{"path": "a", "type": "file", "sha256": "a" * 64, "extra": True}],
    ],
)
def test_trusted_snapshots_reject_ambiguous_entries(
    items: list[dict[str, object]],
) -> None:
    # Final gate 2026-07-17: snapshot dictionaries must not erase ambiguity.
    with pytest.raises(AssertionError):
        trusted_helpers()["snapshots"](items)


def test_trusted_installer_paths_reject_unverified_first_executable() -> None:
    # PR #1242: each installer run must begin with its verified uv directory.
    report = valid_passed_report()
    report["installer"]["first_path"] = "/tmp/system:/tmp/tools"
    with pytest.raises(AssertionError):
        trusted_helpers()["verify_installer_paths"](
            report["installer"],
            report["old_uv"]["executable"],
            report["supported_uv"]["executable"],
            Path("/tmp/tsa-outdated-native-test"),
        )


def test_trusted_installer_paths_reject_non_curated_path_tail() -> None:
    # PR #1242: PATH contains exactly the shared curated command directory.
    report = valid_passed_report()
    report["installer"]["second_path"] += ":/usr/bin"
    with pytest.raises(AssertionError):
        trusted_helpers()["verify_installer_paths"](
            report["installer"],
            report["old_uv"]["executable"],
            report["supported_uv"]["executable"],
            Path("/tmp/tsa-outdated-native-test"),
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "python",
        "tool",
        "stdout",
        "dependency",
        "alternate_wheel",
        "exit_code",
        "fresh_venv",
        "cwd_outside_checkout",
        "pythonpath_cleared",
        "runtime_executable",
        "runtime_prefix",
        "metadata_location",
        "module_file",
        "direct_url_path",
        "record_path",
        "mcp_executable",
    ),
)
def test_trusted_causal_binding_rejects_install_mutation(
    tmp_path: Path, mutation: str
) -> None:
    # Incident 2026-07-16: every install cause, venv path, and sidecar is trusted.
    helpers = trusted_helpers()
    values = outdated_causal_fixture(tmp_path)
    causal, bound = values["causal"], values["bound"]
    tool, wheel, wheel_path = values["tool"], values["wheel"], values["wheel_path"]
    runner, argv, install = values["runner"], values["argv"], values["install"]
    metadata, record, mcp = values["metadata"], values["record"], values["mcp"]
    if mutation == "python":
        install["argv"] = [*argv[:4], "/tmp/other/python", *argv[5:]]
    elif mutation == "tool":
        install["tool"] = {**tool, "sha256": "0" * 64}
    elif mutation == "stdout":
        install["stdout_sha256"] = "0" * 64
    elif mutation == "dependency":
        causal["dependency_manifest_sha256"] = "0" * 64
    elif mutation == "alternate_wheel":
        alternate = f"/attacker/{wheel_path.name}[mcp]"
        install["argv"] = bound["install_argv"] = [*argv[:6], alternate]
    elif mutation in {
        "exit_code",
        "fresh_venv",
        "cwd_outside_checkout",
        "pythonpath_cleared",
    }:
        install[mutation] = 1 if mutation == "exit_code" else False
    elif mutation == "runtime_executable":
        other = "/tmp/other-venv/bin/python"
        causal["runtime"]["executable"] = other
        install["argv"] = bound["install_argv"] = [*argv[:4], other, *argv[5:]]
    elif mutation == "runtime_prefix":
        causal["runtime"]["prefix"] = "/tmp/other-venv"
    elif mutation == "metadata_location":
        metadata["location"] = "/tmp/other-venv/site-packages"
    elif mutation == "record_path":
        record["record_path"] = "/tmp/other-venv/RECORD"
    elif mutation == "mcp_executable":
        mcp["executable"] = "/tmp/other-venv/bin/tree-sitter-analyzer-mcp"
    else:
        metadata[mutation] = f"/tmp/other-venv/{mutation}"
    with pytest.raises(AssertionError):
        helpers["verify_causal_binding"](
            "linux", tmp_path, causal, bound, tool, wheel, wheel_path, runner, "b" * 64
        )


@pytest.mark.parametrize("mutation", ["old-label", "different-root", "tools"])
def test_trusted_sandbox_root_rejects_candidate_coordination(mutation: str) -> None:
    # PR #1245: executable archive layouts, not cooperating sidecars, anchor the root.
    helpers = trusted_helpers()
    report = valid_passed_report()
    member = {"member": "bundle/uv", "sha256": "a" * 64, "size": 1}
    if mutation == "old-label":
        report["old_uv"]["executable"]["path"] = (
            "/tmp/tsa-outdated-native-test/evil/bundle/uv"
        )
        with pytest.raises(AssertionError):
            helpers["executable_sandbox_root"](
                report["old_uv"]["executable"], member, "old", "linux"
            )
        return
    old_root = helpers["executable_sandbox_root"](
        report["old_uv"]["executable"], member, "old", "linux"
    )
    if mutation == "different-root":
        report["supported_uv"]["executable"]["path"] = (
            "/tmp/tsa-outdated-native-forged/supported/bundle/uv"
        )
        with pytest.raises(AssertionError):
            helpers["trusted_sandbox_root"](
                report["old_uv"]["executable"],
                member,
                "linux",
                report["supported_uv"]["executable"],
                member,
            )
        return
    report["installer"]["first_path"] = (
        "/tmp/tsa-outdated-native-test/old/bundle:/tmp/attacker/tools"
    )
    report["installer"]["second_path"] = (
        "/tmp/tsa-outdated-native-test/supported/bundle:/tmp/attacker/tools"
    )
    with pytest.raises(AssertionError):
        helpers["verify_installer_paths"](
            report["installer"],
            report["old_uv"]["executable"],
            report["supported_uv"]["executable"],
            old_root,
        )


def test_trusted_project_root_rejects_coordinated_candidate_value() -> None:
    # PR #1245: a matching stdout/config claim cannot override the executable root.
    with pytest.raises(AssertionError):
        trusted_helpers()["project_root_from_stdout"](
            "📁 Project root: /tmp/tsa-outdated-native-forged/fixture\n",
            "linux",
            Path("/tmp/tsa-outdated-native-test"),
        )


@pytest.mark.parametrize("mutation", ["backup", "before-digest", "extra-entry"])
def test_trusted_initial_snapshot_rejects_mutation(mutation: str) -> None:
    # PR #1245: backup identity is the exact complete pre-install HOME snapshot.
    digest = qualification.hashlib.sha256(b"{}\n").hexdigest()
    config = valid_passed_report()["config"]
    initial = [
        {"path": ".claude", "type": "dir", "sha256": None},
        {"path": ".claude/.mcp.json", "type": "file", "sha256": digest},
    ]
    config["before"] = json.loads(json.dumps(initial))
    config["after_first"] = json.loads(json.dumps(initial))
    config["backup_sha256"] = digest
    if mutation == "backup":
        config["backup_sha256"] = "0" * 64
    elif mutation == "before-digest":
        config["before"][1]["sha256"] = "0" * 64
    else:
        config["before"].append({"path": "extra", "type": "dir", "sha256": None})
        config["after_first"].append({"path": "extra", "type": "dir", "sha256": None})
    with pytest.raises(AssertionError):
        trusted_helpers()["verify_initial_config"](config)


@pytest.mark.parametrize(
    "data",
    [
        b'{"job":"outdated-axis","axis":"linux","status":"failed"}',
        b'{"job":"outdated-axis","axis":"linux","status":"success","extra":1}',
        b'{"job":"outdated-axis","axis":"linux","axis":"linux","status":"success"}',
        b'{"job":"outdated-axis","axis":"linux","status":"success"}\xff',
    ],
)
def test_trusted_job_result_rejects_semantic_or_encoding_mutation(
    tmp_path: Path, data: bytes
) -> None:
    # PR #1245: retained job status is strict UTF-8 JSON with one exact identity.
    result = tmp_path / "job-result.json"
    result.write_bytes(data)
    with pytest.raises((AssertionError, UnicodeDecodeError, json.JSONDecodeError)):
        trusted_helpers()["verify_job_result"](result, "linux")


def test_trusted_job_result_digest_is_content_bound(tmp_path: Path) -> None:
    # PR #1245: the receipt closure consumes the verified job-result digest.
    result = tmp_path / "job-result.json"
    data = b'{"job":"outdated-axis","axis":"windows","status":"success"}\n'
    result.write_bytes(data)
    assert (
        trusted_helpers()["verify_job_result"](result, "windows")
        == qualification.hashlib.sha256(data).hexdigest()
    )
