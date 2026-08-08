"""Contracts for NO1-006A offline installer evidence."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import qualify_fresh_install as qualification

REPO = Path(__file__).parents[2]


def _wait_for_process_exit(pid: int) -> bool:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


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


def test_harness_clears_inherited_bootstrap_opt_out() -> None:
    # PR #1233: hardened parent environments must not rewrite ordinary fixtures.
    completed = subprocess.CompletedProcess([], 0, "", "")
    with (
        patch.dict(os.environ, {"TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP": "1"}),
        patch.object(qualification.subprocess, "run", return_value=completed) as run,
    ):
        _, root, _ = qualification._run(REPO, None, "valid")
    try:
        assert "TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP" not in run.call_args.kwargs["env"]
    finally:
        qualification._remove_fixture(root)


def test_harness_preserves_explicit_bootstrap_opt_out() -> None:
    completed = subprocess.CompletedProcess([], 0, "", "")
    with patch.object(qualification.subprocess, "run", return_value=completed) as run:
        _, root, _ = qualification._run(REPO, None, "valid", disable_bootstrap=True)
    try:
        assert run.call_args.kwargs["env"]["TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP"] == "1"
    finally:
        qualification._remove_fixture(root)


def test_run_removes_fixture_when_installer_times_out(tmp_path: Path) -> None:
    # PR #1233: subprocess timeouts must not leak tsa-installer-contract fixtures.
    fixture_root = tmp_path / "tsa-installer-contract-timeout"
    fixture_root.mkdir()
    with (
        patch.object(qualification.tempfile, "mkdtemp", return_value=str(fixture_root)),
        patch.object(
            qualification.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["/bin/bash", "install.sh"], 30),
        ),
    ):
        try:
            qualification._run(REPO, None, "valid")
        except subprocess.TimeoutExpired:
            pass
        else:
            raise AssertionError("expected installer timeout")
    assert fixture_root.exists() is False


@pytest.mark.parametrize(
    ("probe_signal", "expected_status"),
    ((signal.SIGHUP, 129), (signal.SIGINT, 130), (signal.SIGTERM, 143)),
)
@pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: install.sh signal contract is for macOS/Linux shell installs",
)
def test_installer_signal_terminates_probe_group_and_removes_temp(
    tmp_path: Path, probe_signal: signal.Signals, expected_status: int
) -> None:
    # PR #1233: installer-only signals must clean the isolated uv probe group.
    root = tmp_path / f"probe-signal-{probe_signal.name.lower()}"
    root.mkdir()
    fixture = qualification._prepare_fixture(root, "uv 0.11.0", "valid")
    child_pid_file = root / "uv-child.pid"
    probe_tmp = root / "probe-tmp"
    probe_tmp.mkdir()
    fixture |= {
        "UV_CHILD_PID_FILE": str(child_pid_file),
        "TMPDIR": str(probe_tmp),
    }
    qualification._write_executable(
        root / "mock-bin" / "uv",
        "#!/bin/sh\ntrap '' HUP INT TERM\nsleep 60 &\n"
        'echo "$!" > "$UV_CHILD_PID_FILE"\nwait\n',
    )
    process = subprocess.Popen(
        ["/bin/bash", str(REPO / "install.sh")],
        cwd=root,
        env=os.environ | fixture,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if child_pid_file.exists() and list(probe_tmp.glob("tsa-uv-version.*")):
                break
            time.sleep(0.05)
        assert (
            child_pid_file.exists(),
            len(list(probe_tmp.glob("tsa-uv-version.*"))),
        ) == (True, 1)
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        os.kill(process.pid, probe_signal)
        process.communicate(timeout=10)
        assert (
            process.returncode,
            _wait_for_process_exit(child_pid),
            list(probe_tmp.glob("tsa-uv-version.*")),
        ) == (expected_status, True, [])
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


@pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: install.sh timeout contract is for macOS/Linux shell installs",
)
def test_installer_times_out_hanging_existing_uv(tmp_path: Path) -> None:
    # PR #1233: an existing uv shim must not block installation indefinitely.
    root = tmp_path / "existing-uv-timeout"
    root.mkdir()
    fixture = qualification._prepare_fixture(root, "uv 0.11.0", "valid")
    child_pid_file = root / "uv-child.pid"
    fixture["UV_CHILD_PID_FILE"] = str(child_pid_file)
    qualification._write_executable(
        root / "mock-bin" / "uv",
        '#!/bin/sh\nsleep 60 &\necho "$!" > "$UV_CHILD_PID_FILE"\nwait\n',
    )
    execution_env = {
        key: value
        for key, value in os.environ.items()
        if key != "TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP"
    } | fixture
    completed = subprocess.run(
        ["/bin/bash", str(REPO / "install.sh")],
        cwd=root,
        env=execution_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert (completed.returncode, "Timed out after 5 seconds" in completed.stdout) == (
        1,
        True,
    )
    assert "Replace or repair uv" in completed.stdout
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    assert _wait_for_process_exit(child_pid) is True


@pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: install.sh timeout contract is for macOS/Linux shell installs",
)
def test_installer_times_out_hanging_post_bootstrap_uv(tmp_path: Path) -> None:
    # PR #1233: bootstrap validation must fail closed when the installed uv hangs.
    root = tmp_path / "bootstrap-uv-timeout"
    root.mkdir()
    fixture = qualification._prepare_fixture(root, None, "valid")
    child_pid_file = root / "uv-child.pid"
    fixture["UV_CHILD_PID_FILE"] = str(child_pid_file)
    qualification._write_executable(
        root / "mock-bin" / "curl",
        r"""#!/bin/sh
out=''
while [ "$#" -gt 0 ]; do
  if [ "$1" = '-o' ]; then out=$2; shift 2; else shift; fi
done
cat > "$out" <<'INSTALLER'
#!/bin/sh
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/uv" <<'UV'
#!/bin/sh
sleep 60 &
echo "$!" > "$UV_CHILD_PID_FILE"
wait
UV
chmod 755 "$HOME/.local/bin/uv"
INSTALLER
""",
    )
    execution_env = {
        key: value
        for key, value in os.environ.items()
        if key != "TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP"
    } | fixture
    completed = subprocess.run(
        ["/bin/bash", str(REPO / "install.sh")],
        cwd=root,
        env=execution_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert (
        completed.returncode,
        "Timed out after 5 seconds" in completed.stdout,
        "after bootstrap" in completed.stdout,
    ) == (1, True, True)
    assert "Install uv manually" in completed.stdout
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    assert _wait_for_process_exit(child_pid) is True


@pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: install.sh version contract is for macOS/Linux shell installs",
)
def test_installer_accepts_huge_supported_uv_without_bootstrap(tmp_path: Path) -> None:
    # PR #1233: semver comparison must not overflow native shell integers.
    root = tmp_path / "huge-uv-version"
    root.mkdir()
    huge_version = f"uv {'9' * 200}.0.0"
    fixture = qualification._prepare_fixture(root, huge_version, "valid")
    fixture["TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP"] = "1"
    completed = subprocess.run(
        ["/bin/bash", str(REPO / "install.sh")],
        cwd=root,
        env=os.environ | fixture,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0
    assert f"✅ {huge_version}:" in completed.stdout
    assert (root / "curl.log").exists() is False


@pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: install.sh fixture PATH is for macOS/Linux shell installs",
)
def test_missing_uv_fixture_path_is_hermetic(tmp_path: Path) -> None:
    # PR #1233: a host /usr/bin/uv must not rewrite the missing-uv scenario.
    root = tmp_path / "hermetic-path"
    root.mkdir()
    fixture = qualification._prepare_fixture(root, None, "valid")
    path_entries = fixture["PATH"].split(os.pathsep)
    assert path_entries == [str(root / "mock-bin"), str(root / "tool-bin")]
    assert shutil.which("uv", path=fixture["PATH"]) is None
