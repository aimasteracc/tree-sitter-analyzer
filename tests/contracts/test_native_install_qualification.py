"""Contracts for the NO1-006A native package qualification subsystem."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from _native_trusted_verifier_helpers import trusted_verifier_result  # noqa: E402
from _test_native_qualification_helpers import (  # noqa: E402
    ROOT,
    SCHEMA,
    SCRIPT,
    aggregate,
    assert_success_cleanup,
    assert_timeout_cleanup,
    github_env,
    manifest,
    mutate_wheel_record,
    pid_is_live,
    report,
)


def reports(tmp_path: Path, event: str = "pull_request") -> list[dict[str, object]]:
    _, manifest_path, value = manifest(tmp_path, event)
    return [
        report(axis, manifest_path, value, event)
        for axis in ("linux", "macos", "windows")
    ]


def test_schema_rejects_unknown_trust_boundary_field(tmp_path: Path) -> None:
    value = reports(tmp_path)[0]
    value["self_attested"] = True
    errors = list(
        jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).iter_errors(
            value
        )
    )
    assert [error.validator for error in errors] == ["oneOf"]


def test_candidate_never_claims_native_axes_qualified(tmp_path: Path) -> None:
    result, value = aggregate(tmp_path, reports(tmp_path))
    assert result.returncode == 0
    assert (
        value["native_axes_qualified"],
        value["qualified"],
        value["evidence_trust"],
    ) == (False, False, "UNTRUSTED_CANDIDATE")


def test_trusted_develop_run_requires_external_attestation(tmp_path: Path) -> None:
    result, value = aggregate(
        tmp_path, reports(tmp_path, "push"), event="push", trusted=True
    )
    assert result.returncode == 0
    assert (
        value["native_axes_qualified"],
        value["qualified"],
        value["evidence_trust"],
    ) == (True, False, "EXTERNAL_ATTESTATION_REQUIRED")


def test_push_environment_cannot_promote_pr_reports(tmp_path: Path) -> None:
    result, value = aggregate(tmp_path, reports(tmp_path), event="push", trusted=True)
    assert result.returncode == 1
    assert (
        "linux: report event/ref/SHA/repository/run identity mismatch"
        in value["failures"]
    )
    assert "trusted aggregation refuses candidate/PR reports" in value["failures"]


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("missing", "expected exactly ['linux', 'macos', 'windows']"),
        ("duplicate", "expected exactly ['linux', 'macos', 'windows']"),
        ("attempt", "report event/ref/SHA/repository/run identity mismatch"),
        ("wheel", "manifest or wheel identity mismatch"),
    ],
)
def test_aggregate_rejects_incomplete_or_mixed_identity(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    values = reports(tmp_path)
    if mutation == "missing":
        values.pop()
    elif mutation == "duplicate":
        values[2]["axis"] = "linux"
    elif mutation == "attempt":
        values[1]["workflow"]["run_attempt"] = "2"
    else:
        values[1]["wheel"]["size"] = 999
    result, value = aggregate(tmp_path, values)
    assert result.returncode == 1
    assert any(expected in failure for failure in value["failures"])


def test_aggregate_rejects_unordered_success_stages(tmp_path: Path) -> None:
    values = reports(tmp_path)
    values[0]["stages"][0], values[0]["stages"][1] = (
        values[0]["stages"][1],
        values[0]["stages"][0],
    )
    result, value = aggregate(tmp_path, values)
    assert result.returncode == 1
    assert value["failures"][0].startswith("report-0.json: ValidationError:")


def test_schema_rejects_success_without_exact_four_stages(tmp_path: Path) -> None:
    value = reports(tmp_path)[0]
    value["stages"].pop()
    errors = list(
        jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).iter_errors(
            value
        )
    )
    assert [error.validator for error in errors] == ["oneOf"]


def test_axis_missing_manifest_atomically_writes_strict_failed_report(
    tmp_path: Path,
) -> None:
    output = tmp_path / "evidence" / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "axis",
            "--axis",
            "linux",
            "--wheel",
            str(tmp_path / "missing.whl"),
            "--wheel-manifest",
            str(tmp_path / "missing.json"),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=github_env(),
        check=False,
    )
    value = json.loads(output.read_text())
    assert result.returncode == 1
    assert (value["passed"], value["stages"], value["failure"]["stage"]) == (
        False,
        [],
        "verify_wheel",
    )
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(value)
    assert not output.with_name("report.json.tmp").exists()


def test_aggregate_revalidates_actual_wheel_archive(tmp_path: Path) -> None:
    values = reports(tmp_path)
    wheel, manifest_path, _ = manifest(tmp_path, "pull_request")
    wheel.write_bytes(wheel.read_bytes() + b"tamper")
    paths = []
    for index, value in enumerate(values):
        path = tmp_path / f"r{index}.json"
        path.write_text(json.dumps(value))
        paths.append(str(path))
    output = tmp_path / "aggregate.json"
    result = subprocess.run(
        [
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
        ],
        env=github_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert (
        "aggregate wheel does not exactly match build manifest"
        in json.loads(output.read_text())["failures"][0]
    )


def test_axis_invalid_manifest_json_atomically_writes_failed_report(
    tmp_path: Path,
) -> None:
    wheel, manifest_path, _ = manifest(tmp_path, "pull_request")
    manifest_path.write_text("not-json")
    output = tmp_path / "report.json"
    axis_name = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}[
        __import__("platform").system()
    ]
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "axis",
            "--axis",
            axis_name,
            "--wheel",
            str(wheel),
            "--wheel-manifest",
            str(manifest_path),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=github_env(),
        check=False,
    )
    value = json.loads(output.read_text())
    assert (result.returncode, value["failure"]["stage"], value["stages"]) == (
        1,
        "verify_wheel",
        [],
    )


def test_provenance_validator_rejects_module_outside_fresh_venv(tmp_path: Path) -> None:
    from native_qualification_lib import validate_installed_provenance

    envroot = tmp_path / "venv"
    site = envroot / "site"
    site.mkdir(parents=True)
    outside = tmp_path / "global.py"
    outside.write_text("fixture")
    direct = site / "direct_url.json"
    direct.write_text("{}")
    python = envroot / "python"
    python.write_text("")
    metadata = {
        "location": str(site),
        "module_file": str(outside),
        "module_origin": str(outside),
        "direct_url_path": str(direct),
        "module_recorded": True,
        "installed_record": {
            "record_path": str(direct),
            "record_sha256": "0" * 64,
            "entry_count": 0,
            "files": [],
        },
        "name": "tree-sitter-analyzer",
        "version": "1.0",
        "direct_url": {"archive_info": {"hash": "sha256=" + "a" * 64}},
    }
    runtime = {"prefix": str(envroot), "executable": str(python)}
    with pytest.raises(ValueError, match="escaped fresh venv"):
        validate_installed_provenance(
            metadata, runtime, envroot, {"version": "1.0", "sha256": "a" * 64}
        )


def test_probe_binds_observed_fixture_status_and_not_fake_notification() -> None:
    probe = (ROOT / "scripts" / "native_mcp_probe.py").read_text()
    assert '"indexed: false" in toon and "total_files: 0" in toon' in probe
    assert '"codegraph_status: index missing or empty" in toon' in probe
    assert "notifications/initialized" not in probe


def test_probe_requires_fresh_venv_direct_url_and_record_provenance() -> None:
    harness = (
        SCRIPT.read_text()
        + (ROOT / "scripts" / "native_qualification_lib.py").read_text()
        + (ROOT / "scripts" / "native_provenance.py").read_text()
    )
    assert (
        "distribution/module/runtime/console provenance escaped fresh venv" in harness
    )
    assert "direct_url does not identify the exact wheel" in harness
    assert "module origin is not the wheel RECORD module" in harness


@pytest.mark.parametrize("field", ["hash", "hashes"])
def test_direct_url_rejects_noncanonical_base64(field: str) -> None:
    # PR #1239: permissive decoders accepted invalid suffixes in provenance.
    import base64

    from native_qualification_lib import direct_url_hash

    encoded = (
        base64.urlsafe_b64encode(bytes.fromhex("ab" * 32)).rstrip(b"=").decode() + "!!"
    )
    archive = (
        {"hash": "sha256=" + encoded}
        if field == "hash"
        else {"hashes": {"sha256": encoded}}
    )
    assert direct_url_hash({"url": "file:///wheel.whl", "archive_info": archive}) == ""


def test_live_process_scan_keeps_running_identity() -> None:
    import psutil
    from native_qualification_lib import _live_processes

    process = psutil.Process()
    assert _live_processes({process.pid: process}) == [process]


def test_timeout_runner_has_no_unbounded_communicate() -> None:
    helper = (ROOT / "scripts" / "native_qualification_lib.py").read_text()
    assert "proc.communicate(timeout=3)" in helper
    assert "timeout=grace" in helper
    assert "os.killpg(proc.pid, signal.SIGKILL)" in helper
    assert "proc.communicate()" not in helper


def test_workflow_is_path_routed_and_write_permissions_are_isolated() -> None:
    workflows = ROOT / ".github/workflows"
    workflow = (workflows / "native-install-qualification.yml").read_text()
    prefix, caller = workflow.split("  trusted-attestation:", 1)
    trusted = (workflows / "reusable-native-qualification-attestation.yml").read_text()
    assert "id-token: write" not in prefix and "attestations: write" not in prefix
    assert caller.count("id-token: write") == 1
    assert caller.count("attestations: write") == 1
    assert (
        "actions/checkout" not in trusted and "qualify_native_install.py" not in trusted
    )
    assert "Independently verify downloaded evidence identities" in trusted
    assert "exact(report," in trusted and 'identity(report, "native-axis")' in trusted
    assert "installed_record" in trusted and "RECORD self-entry" not in trusted
    assert "independent-verification.ok') != ''" in trusted


def test_workflow_all_jobs_create_and_upload_strict_job_results() -> None:
    workflow = (ROOT / ".github/workflows/native-install-qualification.yml").read_text()
    assert workflow.count("job-result.json") == 6
    assert workflow.count("if-no-files-found: error") == 3
    assert "continue-on-error: true" in workflow
    assert "--wheel-manifest downloaded/build/wheel-manifest.json" in workflow


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX process-group behavior only; Windows taskkill is separately bounded",
)
def test_timeout_runner_kills_sigterm_ignoring_descendant(tmp_path: Path) -> None:
    assert_timeout_cleanup(tmp_path)


def test_successful_runner_cleans_detached_descendant(tmp_path: Path) -> None:
    # Final review 2026-07-01: successful leaders must not leak background children.
    assert_success_cleanup(tmp_path)


def _assert_late_spawn_cleanup(tmp_path: Path, iterations: int) -> None:
    import time

    from native_qualification_lib import run

    observed: list[tuple[int, bool, bool]] = []
    for iteration in range(iterations):
        ready = tmp_path / f"late-child-{iteration}.ready"
        child_pid_path = tmp_path / f"late-child-{iteration}.pid"
        grandchild_pid_path = tmp_path / f"late-grandchild-{iteration}.pid"
        grandchild = "import time;time.sleep(60)"
        child = (
            "import os,pathlib,signal,subprocess,sys,time;"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
            f"pathlib.Path({str(child_pid_path)!r}).write_text(str(os.getpid()));"
            f"pathlib.Path({str(ready)!r}).write_text('ready');time.sleep(0.25);"
            f"p=subprocess.Popen([sys.executable,'-c',{grandchild!r}],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);"
            f"pathlib.Path({str(grandchild_pid_path)!r}).write_text(str(p.pid));"
            "time.sleep(60)"
        )
        parent = (
            "import pathlib,subprocess,sys,time;"
            f"subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);"
            f"p=pathlib.Path({str(ready)!r});deadline=time.monotonic()+2;"
            "exec('while not p.exists() and time.monotonic()<deadline:\\n time.sleep(0.005)')"
        )
        rc, _, _, _ = run(
            [sys.executable, "-c", parent],
            cwd=tmp_path,
            env=dict(os.environ),
            timeout=5,
        )
        child_pid, grandchild_pid = (
            int(child_pid_path.read_text()),
            int(grandchild_pid_path.read_text()),
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and (
            pid_is_live(child_pid) or pid_is_live(grandchild_pid)
        ):
            time.sleep(0.01)
        observed.append((rc, pid_is_live(child_pid), pid_is_live(grandchild_pid)))
    assert observed == [(0, False, False)] * iterations


@pytest.mark.skipif(
    os.name == "nt",
    reason="Incident 2026-07-02 uses POSIX SIGTERM-ignore semantics",
)
def test_runner_cleans_grace_period_detached_grandchild(tmp_path: Path) -> None:
    # Incident 2026-07-02: a one-shot token scan leaked this late grandchild.
    _assert_late_spawn_cleanup(tmp_path, 1)


@pytest.mark.skipif(
    os.name == "nt",
    reason="Incident 2026-07-02 uses POSIX SIGTERM-ignore semantics",
)
def test_runner_late_detached_grandchild_cleanup_stress(tmp_path: Path) -> None:
    # Incident 2026-07-02: repeated spawning exercises cleanup rescan stability.
    _assert_late_spawn_cleanup(tmp_path, 10)


def test_runner_reports_cleanup_nonquiescence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import native_qualification_lib

    monkeypatch.setattr(
        native_qualification_lib,
        "_cleanup_token_processes",
        lambda *args, **kwargs: False,
    )
    rc, _, err, _ = native_qualification_lib.run(
        [sys.executable, "-c", "pass"],
        cwd=tmp_path,
        env=dict(os.environ),
        timeout=5,
    )
    assert (rc, err) == (
        125,
        b"\nnative qualification process cleanup did not reach quiescence",
    )


@pytest.mark.parametrize("mutation", ["unrecorded", "duplicate", "digest", "pth"])
def test_wheel_record_rejects_non_exact_or_injected_archive(
    tmp_path: Path, mutation: str
) -> None:
    # Final review 2026-07-01: RECORD is an exact cryptographic archive inventory.
    from native_qualification_lib import wheel_metadata

    wheel, _, _ = manifest(tmp_path, "pull_request")
    mutate_wheel_record(wheel, mutation)
    with pytest.raises(ValueError, match="RECORD|injection"):
        wheel_metadata(wheel)


@pytest.mark.parametrize(
    "mutation",
    [
        "valid",
        "stage_false",
        "extra_field",
        "mcp_oracle",
        "venv_provenance",
        "direct_hash",
        "direct_base64",
        "snapshot_direct",
        "transcript_error",
        "transcript_missing",
        "path_dotdot_posix",
        "path_dotdot_windows",
        "aggregate_extra",
        "axis_digest",
        "installed_member_hash",
        "installed_member_size",
        "installed_record_digest",
        "installed_inventory",
        "side_artifact",
        "path_containment",
        "zip_extra",
        "zip_symlink",
        "filename_metadata",
    ],
)
def test_trusted_inline_verifier_rejects_candidate_forgery(
    tmp_path: Path, mutation: str
) -> None:
    # Final workflow review 2026-07-01: candidate JSON cannot weaken trusted semantics.
    assert trusted_verifier_result(tmp_path, mutation) == (
        0 if mutation == "valid" else 1
    )
