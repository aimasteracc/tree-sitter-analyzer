"""Pinned-Linux live and workflow contracts for the RFC-0022 authority."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
POLICY_PATH = ROOT / "config/rfc0022-linux-strace-policy.json"
AUTHORITY = SCRIPTS / "rfc0022_strace_authority.py"
CONTROL = SCRIPTS / "rfc0022_strace_positive_control.py"
WORKFLOW = ROOT / ".github/workflows/rfc0022-linux-write-authority.yml"


def test_launcher_source_locks_native_boundary_controls() -> None:
    source = AUTHORITY.read_text(encoding="utf-8")
    required = {
        '"-ff"',
        '"-yy"',
        '"--kill-on-exit"',
        "close_fds=True",
        "start_new_session=True",
        '"PYTHONDONTWRITEBYTECODE": "1"',
        '"PYTHONNOUSERSITE": "1"',
        '"XDG_CACHE_HOME"',
        '"TMPDIR"',
        "os.killpg(process.pid, signal.SIGKILL)",
        "surviving traced descendants",
    }
    assert {item for item in required if item in source} == required


def test_workflow_is_pinned_serial_blocking_and_artifact_preserving() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-24.04" in text
    assert "timeout-minutes: 20" in text
    assert "permissions:\n  contents: read" in text
    assert text.count('version: "0.12.3"') == 1
    assert "uv sync --frozen --all-extras" in text
    assert "minimum_strace_version" not in text
    assert 'RFC0022_RUN_LIVE_STRACE: "1"' in text
    assert (
        "uv run pytest tests/contracts/test_rfc0022_strace_authority.py "
        "tests/contracts/test_rfc0022_strace_controls.py "
        "tests/contracts/test_rfc0022_strace_process_state.py "
        "tests/contracts/test_rfc0022_strace_authority_live.py "
        "-q -n 0 --reruns=0 --timeout=120"
    ) in " ".join(text.split())
    assert text.count("if: always()") == 2
    assert "if-no-files-found: error" in text
    assert "continue-on-error" not in text
    assert "|| true" not in text
    uses = [line.strip() for line in text.splitlines() if "uses:" in line]
    assert uses == [
        "- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
        "- uses: astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78 # v7.6.0",
        "- uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0",
        "uses: actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f # v6.0.0",
    ]


def _live_command(case: Path, artifact: Path, control: str) -> list[str]:
    target = (
        ["/bin/false"]
        if control == "nonzero-exit"
        else [sys.executable, str(CONTROL), control, "--root", str(case)]
    )
    if control == "absolute-write":
        target.extend(["--absolute-target", str(case / "absolute-created.txt")])
    if control == "permission-denied":
        target.extend(["--absolute-target", "/sys/rfc0022-authority-denied"])
    return [
        sys.executable,
        str(AUTHORITY),
        "run",
        "--policy",
        str(POLICY_PATH),
        "--trace-dir",
        str(artifact / "trace"),
        "--report",
        str(artifact / "report.json"),
        "--monitor-root",
        str(case),
        "--target-cwd",
        str(case),
        "--timeout",
        "2" if control == "timeout-detached-descendant" else "20",
        "--",
        *target,
    ]


LIVE_CONTROLS = [
    "absolute-write",
    "clean",
    "create-unlink",
    "descendant-create-unlink",
    "inherited-fd",
    "mkdir-rmdir",
    "nonzero-exit",
    "permission-denied",
    "rename-restore",
    "shared-writable-mmap",
    "sqlite-sidecar",
    "timeout-detached-descendant",
    "truncate-restore",
    "write-then-delete",
]


@pytest.mark.parametrize("control", LIVE_CONTROLS)
def test_live_pinned_linux_authority_controls(tmp_path: Path, control: str) -> None:
    if os.environ.get("RFC0022_RUN_LIVE_STRACE") != "1":
        pytest.skip(
            "tracked: RFC-0022 P0.4 live authority runs only in its pinned Linux job"
        )
    artifact_root = Path(os.environ["RFC0022_AUTHORITY_ARTIFACT_DIR"])
    artifact = artifact_root / control
    shutil.rmtree(artifact, ignore_errors=True)
    artifact.mkdir(parents=True)
    case = tmp_path / control
    case.mkdir()
    (case / "fixture.txt").write_bytes(b"fixture\n")
    result = subprocess.run(
        _live_command(case, artifact, control),
        check=False,
        capture_output=True,
        text=True,
        timeout=40,
    )
    report = json.loads((artifact / "report.json").read_text(encoding="utf-8"))
    if control == "nonzero-exit":
        assert result.returncode == 2
        assert report["authority_status"] == "error"
        assert report["outcome"] == "indeterminate"
        assert report["cleanup_remaining_pids"] == []
        assert report["errors"] == ["target return code mismatch: expected 0, got 1"]
        return
    if control == "timeout-detached-descendant":
        assert result.returncode == 2
        assert report["authority_status"] == "error"
        assert report["outcome"] == "indeterminate"
        assert report["cleanup_remaining_pids"] == []
        assert report["errors"] == ["strace target timed out"]
        return
    assert report["errors"] == []
    assert report["cleanup_remaining_pids"] == []
    assert report["authority_status"] == "healthy"
    if control == "clean":
        assert result.returncode == 0
        assert report["outcome"] == "clean"
        assert report["violations"] == []
    else:
        assert result.returncode == 1
        assert report["outcome"] == "violation"
        assert report["violations"] != []
        assert all(
            set(event)
            == {
                "flags",
                "line",
                "operation",
                "pid",
                "result",
                "syscall",
                "target",
                "timestamp",
            }
            for event in report["violations"]
        )


def test_live_artifact_manifest_is_complete() -> None:
    if os.environ.get("RFC0022_RUN_LIVE_STRACE") != "1":
        pytest.skip(
            "tracked: RFC-0022 P0.4 live artifact manifest runs in the pinned job"
        )
    artifact_root = Path(os.environ["RFC0022_AUTHORITY_ARTIFACT_DIR"])
    assert sorted(
        path.name for path in artifact_root.iterdir() if path.is_dir()
    ) == sorted(LIVE_CONTROLS)
    for control in LIVE_CONTROLS:
        artifact = artifact_root / control
        report = json.loads((artifact / "report.json").read_text(encoding="utf-8"))
        traces = sorted((artifact / "trace").glob("trace.*"))
        assert traces[0].read_bytes()[-1:] == b"\n"
        if control not in {"nonzero-exit", "timeout-detached-descendant"}:
            assert {path.name for path in traces} == {
                f"trace.{item['pid']}" for item in report["trace_files"]
            }
