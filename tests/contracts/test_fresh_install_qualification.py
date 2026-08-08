"""Contracts for NO1-006A offline installer evidence."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parents[2]


def _run(*arguments: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    completed = subprocess.run(
        [sys.executable, str(REPO / "scripts/qualify_fresh_install.py"), *arguments],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return completed, json.loads(completed.stdout)


def test_axis_all_fails_closed_when_axes_are_pending() -> None:
    completed, report = _run("--axis", "all")
    assert completed.returncode == 1
    assert report["qualification_performed"] is False
    assert report["native_axes_qualified"] is False
    assert "qualified_axes" not in report
    assert [axis["qualified"] for axis in report["axes"]] == [False, False, False]
    assert [axis["native_evidence"] for axis in report["axes"]] == [False, False, False]


def test_local_contract_only_is_explicitly_not_qualification() -> None:
    completed, report = _run("--local-contract-only")
    expected = 1 if platform.system() == "Windows" else 0
    assert completed.returncode == expected
    assert report["evidence_scope"] == "offline_installer_contract"
    assert report["package_evidence"] == "none"
    assert report["mcp_protocol_evidence"] == "none"
    host_axis = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(
        platform.system(), "unsupported"
    )
    assert [axis["axis"] for axis in report["axes"]] == [host_axis]
    assert report["pending_axes"] == []
    current = report["axes"][0]
    assert current["qualification"] == "not_performed"
    assert current["qualified"] is False


def test_offline_contract_covers_independent_failure_boundaries() -> None:
    completed, report = _run("--local-contract-only")
    if platform.system() == "Windows":
        assert completed.returncode == 1
        return
    assert completed.returncode == 0
    host = next(axis for axis in report["axes"] if axis["status"] == "passed")
    assert host["scenario_type"] == "offline_installer_contract"
    assert [scenario["id"] for scenario in host["scenarios"]] == [
        "disable_unverified_bootstrap",
        "missing_uv_bootstraps",
        "outdated_uv_bootstraps",
        "installer_body_failure",
        "curl_missing",
        "download_tls_failure",
        "post_bootstrap_uv_missing",
        "post_bootstrap_uv_non_executable",
        "post_bootstrap_uv_too_old",
        "post_bootstrap_uv_malformed",
        "post_bootstrap_path_prefers_new_uv",
        "json_parse_error_skips_and_continues",
        "python3_missing_fails_closed",
        "config_root_non_object_fails_closed",
        "mcp_servers_non_object_fails_closed",
        "tsa_entry_non_object_fails_closed",
        "no_agent_config_skips_cleanly",
        "merge_write_permission_failure_fails_closed",
    ]
    assert [scenario["status"] for scenario in host["scenarios"]] == ["passed"] * 18
    assert [scenario["installer_exit"] for scenario in host["scenarios"]] == [
        1,
        0,
        0,
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        0,
        0,
        1,
        1,
        1,
        1,
        0,
        1,
    ]


def test_scenario_settings_and_execution_fingerprints_are_unique() -> None:
    completed, report = _run("--local-contract-only")
    if platform.system() == "Windows":
        assert completed.returncode == 1
        return
    assert completed.returncode == 0
    scenarios = report["axes"][0]["scenarios"]
    settings_fingerprints = [item["settings_fingerprint"] for item in scenarios]
    execution_fingerprints = [item["execution_fingerprint"] for item in scenarios]
    assert len(settings_fingerprints) == 18
    assert len(set(settings_fingerprints)) == 18
    assert len(execution_fingerprints) == 18
    assert len(set(execution_fingerprints)) == 18


def test_local_contract_only_rejects_axis_combination() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/qualify_fresh_install.py"),
            "--local-contract-only",
            "--axis",
            "all",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 2
    assert "--local-contract-only cannot be combined with --axis" in completed.stderr
    assert completed.stdout == ""


def test_ambiguous_contract_only_flag_is_rejected() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/qualify_fresh_install.py"),
            "--contract-only",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 2
    assert "unrecognized arguments: --contract-only" in completed.stderr
    assert completed.stdout == ""


def test_artifact_records_untrusted_provenance_and_unverified_bootstrap() -> None:
    completed, report = _run("--local-contract-only")
    if platform.system() == "Windows":
        assert completed.returncode == 1
    else:
        assert completed.returncode == 0
    expected_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    expected_dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    assert report["source"] == {
        "git": {"commit": expected_commit, "dirty": expected_dirty},
        "install_sh_sha256": hashlib.sha256(
            (REPO / "install.sh").read_bytes()
        ).hexdigest(),
        "harness_sha256": hashlib.sha256(
            (REPO / "scripts/qualify_fresh_install.py").read_bytes()
        ).hexdigest(),
    }
    assert report["evidence_trust"] == "UNTRUSTED_SELF_REPORTED"
    assert report["host"]["os"] == platform.system()
    assert report["host"]["os_version"] == platform.version()
    assert report["host"]["architecture"] == platform.machine()
    assert report["host"]["python"] == platform.python_version()
    assert report["bootstrap"] == {
        "attestation": "none",
        "execution": "default_unverified_with_secure_opt_out",
        "integrity": "none",
        "trust": "UNVERIFIED",
        "url": "https://astral.sh/uv/install.sh",
    }


def test_readme_discloses_default_unverified_bootstrap() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "mutable and **not content-bound**" in readme


def test_readme_documents_secure_bootstrap_opt_out() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP=1 bash" in readme


def test_installer_uses_disable_bootstrap_contract() -> None:
    installer = (REPO / "install.sh").read_text(encoding="utf-8")
    assert "TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP" in installer


def test_installer_retires_allow_bootstrap_contract() -> None:
    installer = (REPO / "install.sh").read_text(encoding="utf-8")
    assert "TSA_ALLOW_UNVERIFIED_UV_BOOTSTRAP" not in installer


def test_harness_contains_no_mock_uvx_first_answer() -> None:
    source = (REPO / "scripts/qualify_fresh_install.py").read_text(encoding="utf-8")
    assert "uvx-template" not in source
    assert "FIRST_ANSWER" not in source
