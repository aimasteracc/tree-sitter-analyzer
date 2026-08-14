"""Pinned-Linux live and workflow contracts for the RFC-0022 authority."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
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
LAUNCHER = SCRIPTS / "rfc0022_strace_target_launcher.py"
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
RAW_TRACE_KEYS = {"pid", "sha256", "size", "terminal"}
PROCESS_EDGE = re.compile(r"^\d+\.\d+ (?:clone|clone3|fork|vfork)\(.*\)\s+= (\d+)$")
TERMINAL = re.compile(r"\+\+\+ (?:exited with \d+|killed by .+) \+\+\+")


def test_launcher_source_locks_native_boundary_controls() -> None:
    source = AUTHORITY.read_text(encoding="utf-8")
    required = {
        '"-ff"',
        '"-yy"',
        "trace_dir.chmod(0o700)",
        "prepare_target_identity(",
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
    assert "RFC0022_TARGET_USER: rfc0022-target" in text
    assert text.count('"tests/fixtures/rfc0022_linux_expected_events.json"') == 2
    assert "sudo useradd --system --user-group --no-create-home" in text
    assert 'run: sudo chmod -R a+rX "$RFC0022_AUTHORITY_ARTIFACT_DIR"' in text
    assert (
        "uv run pytest tests/contracts/test_rfc0022_strace_authority.py "
        "tests/contracts/test_rfc0022_strace_controls.py "
        "tests/contracts/test_rfc0022_strace_process_state.py "
        "tests/contracts/test_rfc0022_strace_authority_live.py "
        "-q -n 0 --reruns=0 --timeout=120"
    ) in " ".join(text.split())
    assert text.count("if: always()") == 3
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
    if control == "trace-tamper-denied":
        target.extend(["--absolute-target", str(artifact / "trace" / "forged")])
    return [
        "sudo",
        "-n",
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
    "trace-tamper-denied",
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
    assert all(
        set(expected)
        == {
            "authority_status",
            "cleanup_survivor_count",
            "errors",
            "events",
            "outcome",
            "returncode",
            "snapshots_equal",
            "target_returncode",
            "trace_graph",
        }
        for expected in EXPECTED["controls"].values()
    )


def test_raw_event_binding_rejects_unrelated_trace_line() -> None:
    event = {
        "flags": "O_CREAT|O_WRONLY",
        "result": "3</case/native-created.txt>",
        "syscall": "openat",
        "target": "/case/native-created.txt",
        "timestamp": "1700000000.000001",
    }
    unrelated = (
        '1700000000.000001 openat(AT_FDCWD</case>, "unrelated.txt", O_RDONLY) '
        "= 3</case/unrelated.txt>"
    )
    with pytest.raises(AssertionError):
        _assert_event_raw_binding(event, unrelated)


def _relative_target(target: str, case: Path, trace_dir: Path) -> str:
    path = Path(target.removesuffix(" (deleted)"))
    try:
        trace_relative = path.relative_to(trace_dir)
    except ValueError:
        pass
    else:
        name = trace_relative.as_posix()
        if re.fullmatch(r"trace\.\d+", name):
            name = "trace.<pid>"
        return f"<trace-dir>/{name}"
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


def _raw_trace_lines(
    report: dict[str, object], trace_dir: Path
) -> dict[int, list[str]]:
    assert stat.S_IMODE(trace_dir.stat().st_mode) == 0o555
    assert trace_dir.stat().st_uid == 0
    inventory = report["raw_trace_files"]
    assert isinstance(inventory, list)
    assert all(set(item) == RAW_TRACE_KEYS for item in inventory)
    assert {path.name for path in trace_dir.iterdir()} == {
        f"trace.{item['pid']}" for item in inventory
    }
    raw_by_pid: dict[int, list[str]] = {}
    for item in inventory:
        path = trace_dir / f"trace.{item['pid']}"
        assert stat.S_IMODE(path.stat().st_mode) == 0o444
        assert path.stat().st_uid == 0
        raw = path.read_bytes()
        assert len(raw) == item["size"]
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        lines = raw.decode("utf-8").splitlines()
        body = lines[-1].partition(" ")[2] if lines else ""
        terminal = body if TERMINAL.fullmatch(body) else None
        assert item["terminal"] == terminal
        raw_by_pid[item["pid"]] = lines
    return raw_by_pid


def _assert_event_raw_binding(event: dict[str, object], raw_line: str) -> None:
    assert raw_line.startswith(f"{event['timestamp']} {event['syscall']}(")
    assert raw_line.endswith(f" = {event['result']}")
    target = str(event["target"]).removesuffix(" (deleted)")
    assert json.dumps(target) in raw_line or f"<{target}>" in raw_line
    flags = event["flags"]
    if flags is not None:
        assert all(token in raw_line for token in str(flags).split("|"))


def _raw_process_graph(raw_by_pid: dict[int, list[str]]) -> list[list[str | None]]:
    parents: dict[int, int] = {}
    for parent_pid, lines in raw_by_pid.items():
        for line in lines:
            match = PROCESS_EDGE.fullmatch(line)
            if match is not None and int(match.group(1)) in raw_by_pid:
                child_pid = int(match.group(1))
                assert child_pid not in parents
                parents[child_pid] = parent_pid
    roots = set(raw_by_pid) - set(parents)
    assert len(roots) == 1
    root = next(iter(roots))
    assert set(parents.values()) <= set(raw_by_pid)
    roles = {pid: "root" if pid == root else "descendant" for pid in raw_by_pid}
    return sorted(
        [
            [roles[pid], None if pid == root else roles[parents[pid]]]
            for pid in raw_by_pid
        ]
    )


def _assert_final_target_exec(
    report: dict[str, object], raw_by_pid: dict[int, list[str]]
) -> int:
    graph_parents: set[int] = set()
    for lines in raw_by_pid.values():
        for line in lines:
            match = PROCESS_EDGE.fullmatch(line)
            if match is not None and int(match.group(1)) in raw_by_pid:
                graph_parents.add(int(match.group(1)))
    root_pid = next(iter(set(raw_by_pid) - graph_parents))
    invocation = report["invocation"]
    target_index = len(invocation) - 1 - invocation[::-1].index("--")
    target = invocation[target_index + 1]
    successful_execs = [
        line
        for line in raw_by_pid[root_pid]
        if re.match(r"^\d+\.\d+ execve(?:at)?\(", line) and line.endswith(" = 0")
    ]
    assert len(successful_execs) == 2
    assert json.dumps(target) in successful_execs[-1]
    return root_pid


def _normalized_evidence(
    report: dict[str, object], case: Path, trace_dir: Path
) -> tuple[list[list[str | None]], list[list[str | None]], dict[int, list[str]]]:
    raw_by_pid = _raw_trace_lines(report, trace_dir)
    raw_graph = _raw_process_graph(raw_by_pid)
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
    assert graph == raw_graph
    for item in trace_files:
        assert item["terminal"] == "+++ exited with 0 +++"
        raw = (trace_dir / f"trace.{item['pid']}").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    violations = report["violations"]
    assert isinstance(violations, list)
    assert all(set(event) == EVENT_KEYS for event in violations)
    native_timestamps: list[Decimal] = []
    normalized: list[list[str | None]] = []
    for event in violations:
        pid = event["pid"]
        if pid == 0:
            assert event["timestamp"] == "supplemental"
            assert event["line"] == report["monitor_roots"].index(event["target"]) + 1
            role = "authority"
        else:
            role = role_by_pid[pid]
            raw_line = raw_by_pid[pid][event["line"] - 1]
            _assert_event_raw_binding(event, raw_line)
            native_timestamps.append(Decimal(event["timestamp"]))
        normalized.append(
            [
                role,
                event["syscall"],
                event["operation"],
                _relative_target(event["target"], case, trace_dir),
                event["flags"],
                _result_class(event["result"]),
            ]
        )
    assert native_timestamps == sorted(native_timestamps)
    return normalized, graph, raw_by_pid


@pytest.mark.parametrize("control", LIVE_CONTROLS)
def test_live_pinned_linux_authority_controls(control: str) -> None:
    if os.environ.get("RFC0022_RUN_LIVE_STRACE") != "1":
        pytest.skip(
            "tracked: RFC-0022 P0.4 live authority runs only in its pinned Linux job"
        )
    artifact_root = Path(os.environ["RFC0022_AUTHORITY_ARTIFACT_DIR"])
    artifact = artifact_root / control
    shutil.rmtree(artifact, ignore_errors=True)
    artifact.mkdir(parents=True)
    case = Path(os.environ["RFC0022_AUTHORITY_CASE_DIR"]) / control
    shutil.rmtree(case, ignore_errors=True)
    case.mkdir(mode=0o777)
    case.chmod(0o777)
    fixture = case / "fixture.txt"
    fixture.write_bytes(b"fixture\n")
    fixture.chmod(0o666)
    result = subprocess.run(
        _live_command(case, artifact, control),
        check=False,
        capture_output=True,
        text=True,
        timeout=40,
    )
    report = json.loads((artifact / "report.json").read_text(encoding="utf-8"))
    expected = EXPECTED["controls"][control]
    trace_dir = artifact / "trace"
    if report["trace_files"]:
        normalized, graph, raw_by_pid = _normalized_evidence(report, case, trace_dir)
        root_pid = _assert_final_target_exec(report, raw_by_pid)
    else:
        raw_by_pid = _raw_trace_lines(report, trace_dir)
        graph = _raw_process_graph(raw_by_pid)
        root_pid = _assert_final_target_exec(report, raw_by_pid)
        normalized = []
        assert report["violations"] == []

    identity = report["target_identity"]
    assert set(identity) == {"gid", "groups", "launcher", "no_new_privs", "uid", "user"}
    assert identity["user"] == os.environ["RFC0022_TARGET_USER"]
    assert 0 not in {identity["uid"], identity["gid"], *identity["groups"]}
    assert identity["no_new_privs"] is True
    assert identity["launcher"] == {
        "path": str(LAUNCHER.resolve()),
        "sha256": hashlib.sha256(LAUNCHER.read_bytes()).hexdigest(),
    }
    assert report["invocation"][1:3] == ["-u", identity["user"]]

    expected_survivors = expected["cleanup_survivor_count"]
    assert len(report["cleanup_survivor_pids"]) == expected_survivors
    if control == "timeout-detached-descendant":
        descendants = sorted(set(raw_by_pid) - {root_pid})
        assert report["cleanup_survivor_pids"] == descendants
        assert len(descendants) == 1
        child_lines = raw_by_pid[descendants[0]]
        assert any(
            json.dumps("import time; time.sleep(300)") in line and line.endswith(" = 0")
            for line in child_lines
        )
        assert child_lines[-1].startswith(tuple("0123456789"))
        assert " pselect6(" in child_lines[-1]
        assert " = " not in child_lines[-1]
        root_terminal = next(
            item["terminal"]
            for item in report["raw_trace_files"]
            if item["pid"] == root_pid
        )
        child_terminal = next(
            item["terminal"]
            for item in report["raw_trace_files"]
            if item["pid"] == descendants[0]
        )
        assert [root_terminal, child_terminal] == ["+++ exited with 0 +++", None]
    elif control == "nonzero-exit":
        assert report["cleanup_survivor_pids"] == []
        assert len(raw_by_pid) == 1
        terminal = report["raw_trace_files"][0]["terminal"]
        assert terminal == "+++ exited with 1 +++"
    else:
        assert report["cleanup_survivor_pids"] == []

    assert result.returncode == expected["returncode"]
    assert report["authority_status"] == expected["authority_status"]
    assert report["outcome"] == expected["outcome"]
    assert report["errors"] == expected["errors"]
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
        report_path = artifact / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        traces = sorted((artifact / "trace").iterdir())
        inventory = report["raw_trace_files"]
        assert {path.name for path in traces} == {
            f"trace.{item['pid']}" for item in inventory
        }
        assert len(traces) == len(EXPECTED["controls"][control]["trace_graph"])
        for item in inventory:
            raw = (artifact / "trace" / f"trace.{item['pid']}").read_bytes()
            assert len(raw) == item["size"]
            assert hashlib.sha256(raw).hexdigest() == item["sha256"]
            if item["terminal"] is not None:
                assert raw[-1:] == b"\n"
        assert not list(artifact.glob(".report.json.*.tmp"))
