"""Adversarial contracts for content-bound outdated-uv qualification."""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

import jsonschema
import pytest

from scripts import qualify_outdated_uv as qualification

ROOT = Path(__file__).parents[2]
SCHEMA = json.loads(
    (ROOT / "rfcs/schemas/no1-006a-outdated-uv-attestation-v2.schema.json").read_text()
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
    command = ["/bin/bash", "-c", f"sleep 60 & echo $! > {pid_file}; wait"]
    with pytest.raises(TimeoutError, match="process tree timed out and was reaped"):
        qualification.run_tree(command, tmp_path, os.environ.copy(), 0.2)
    pid = int(pid_file.read_text())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        os.kill(pid, signal.SIGKILL)
        raise AssertionError("installer descendant survived bounded cleanup")


def test_schema_rejects_windows_pass_and_mutable_bootstrap_claim() -> None:
    report = qualification.base_report("windows")
    jsonschema.validate(report, SCHEMA)
    report["passed"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)
    report = qualification.base_report("windows")
    report["automatic_mutable_bootstrap_qualified"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, SCHEMA)


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
