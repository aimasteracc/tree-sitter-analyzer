"""Pinned-Linux live and workflow contracts for the RFC-0022 authority."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
POLICY_PATH = ROOT / "config/rfc0022-linux-strace-policy.json"
AUTHORITY = SCRIPTS / "rfc0022_strace_authority.py"
CONTROL = SCRIPTS / "rfc0022_strace_positive_control.py"
WORKFLOW = ROOT / ".github/workflows/rfc0022-linux-write-authority.yml"
EXPECTED_PATH = ROOT / "tests/fixtures/rfc0022_linux_expected_events.json"
EXPECTED = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
EVENT_KEYS = {
    "flags",
    "line",
    "operation",
    "pid",
    "result",
    "syscall",
    "target",
    "timestamp",
}
TRACE_FILE_KEYS = {"parent_pid", "pid", "role", "sha256", "terminal"}


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


def test_expected_live_evidence_schema_is_exact() -> None:
    assert set(EXPECTED) == {
        "controls",
        "event_fields",
        "schema_version",
        "trace_graph_fields",
    }
    assert EXPECTED["schema_version"] == 1
    assert EXPECTED["event_fields"] == [
        "role",
        "syscall",
        "operation",
        "target",
        "flags",
        "result_class",
    ]
    assert EXPECTED["trace_graph_fields"] == ["role", "parent_role"]
    assert sorted(EXPECTED["controls"]) == sorted(LIVE_CONTROLS)


def _relative_target(target: str, case: Path) -> str:
    path = Path(target.removesuffix(" (deleted)"))
    try:
        relative = path.relative_to(case)
    except ValueError:
        return str(path)
    return "." if relative == Path(".") else relative.as_posix()


def _result_class(result: str) -> str:
    if result.startswith("-1 "):
        return " ".join(result.split(maxsplit=2)[:2])
    if result == "changed":
        return "changed"
    return "success"


def _normalized_evidence(
    report: dict[str, object], case: Path, trace_dir: Path
) -> tuple[list[list[str | None]], list[list[str | None]]]:
    trace_files = report["trace_files"]
    assert isinstance(trace_files, list)
    assert all(set(item) == TRACE_FILE_KEYS for item in trace_files)
    role_by_pid = {item["pid"]: item["role"] for item in trace_files}
    graph = sorted(
        [
            [
                item["role"],
                None if item["parent_pid"] is None else role_by_pid[item["parent_pid"]],
            ]
            for item in trace_files
        ]
    )
    raw_by_pid: dict[int, list[str]] = {}
    for item in trace_files:
        assert item["terminal"] == "+++ exited with 0 +++"
        trace_path = trace_dir / f"trace.{item['pid']}"
        raw = trace_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        raw_by_pid[item["pid"]] = raw.decode("utf-8").splitlines()

    violations = report["violations"]
    assert isinstance(violations, list)
    assert all(set(event) == EVENT_KEYS for event in violations)
    native_timestamps: list[Decimal] = []
    normalized: list[list[str | None]] = []
    for event in violations:
        pid = event["pid"]
        if pid == 0:
            assert [event["timestamp"], event["line"]] == ["supplemental", 0]
            role = "authority"
        else:
            role = role_by_pid[pid]
            line_number = event["line"]
            raw_line = raw_by_pid[pid][line_number - 1]
            assert raw_line.startswith(f"{event['timestamp']} {event['syscall']}(")
            native_timestamps.append(Decimal(event["timestamp"]))
        normalized.append(
            [
                role,
                event["syscall"],
                event["operation"],
                _relative_target(event["target"], case),
                event["flags"],
                _result_class(event["result"]),
            ]
        )
    assert native_timestamps == sorted(native_timestamps)
    return normalized, graph


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
    expected = EXPECTED["controls"][control]
    normalized, graph = _normalized_evidence(report, case, artifact / "trace")

    assert result.returncode == expected["returncode"]
    assert report["authority_status"] == expected["authority_status"]
    assert report["outcome"] == expected["outcome"]
    assert report["errors"] == expected["errors"]
    assert report["cleanup_survivor_pids"] == []
    assert report["cleanup_remaining_pids"] == []
    assert report["snapshots"]["equal"] is expected["snapshots_equal"]
    assert report["target"]["expected_returncode"] == 0
    assert report["target"]["returncode"] == expected["target_returncode"]
    assert normalized == expected["events"]
    assert graph == expected["trace_graph"]


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
        if control == "timeout-detached-descendant":
            assert traces[0].is_file() is True
        else:
            assert traces[0].read_bytes()[-1:] == b"\n"
        if control not in {"nonzero-exit", "timeout-detached-descendant"}:
            assert {path.name for path in traces} == {
                f"trace.{item['pid']}" for item in report["trace_files"]
            }
