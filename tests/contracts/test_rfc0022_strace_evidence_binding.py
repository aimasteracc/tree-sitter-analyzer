"""Independent raw-line binding checks for RFC-0022 live evidence."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from rfc0022_strace_authority import load_policy  # noqa: E402
from rfc0022_strace_model import AuthorityError  # noqa: E402
from rfc0022_strace_parser import parse_trace_directory  # noqa: E402
from rfc0022_strace_runtime import (  # noqa: E402
    raw_trace_metadata,
    seal_trace_directory,
)

POLICY, _ = load_policy(ROOT / "config/rfc0022-linux-strace-policy.json")


def _write_trace(directory: Path, bodies: list[str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "trace.100"
    lines = (f"1700000000.{index:06d} {body}\n" for index, body in enumerate(bodies, 1))
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _assert_mapping_target_binding(
    target: str, raw_line: str, prior_lines: list[str]
) -> None:
    request = re.search(r" (?:madvise|mprotect|msync)\((0x[0-9a-f]+), (\d+),", raw_line)
    if request is None:
        raise AssertionError("mapping event lacks an exact address range")
    start = int(request.group(1), 16)
    end = start + int(request.group(2))
    for line in reversed(prior_lines):
        if re.search(r" execve(?:at)?\(.+\) = 0$", line):
            break
        if " mremap(" in line:
            raise AssertionError("mapping history contains unmodeled mremap")
        removal = re.search(r" munmap\((0x[0-9a-f]+), (\d+)\) = 0$", line)
        if removal is not None:
            base = int(removal.group(1), 16)
            limit = base + int(removal.group(2))
            if start < limit and base < end:
                raise AssertionError("mapping was removed before the event")
        mapping = re.search(r" mmap(?:2)?\([^,]+, (\d+), .+\) = (0x[0-9a-f]+)$", line)
        if mapping is None:
            continue
        base = int(mapping.group(2), 16)
        limit = base + int(mapping.group(1))
        if start < limit and base < end:
            assert base <= start and end <= limit
            assert f"<{target}>" in line
            return
    raise AssertionError("mapping event lacks live file provenance")


def logical_raw_line(raw_line: str, prior_lines: list[str]) -> str:
    resumed = re.match(
        r"^(\d+\.\d+) <\.\.\. ([A-Za-z_][A-Za-z0-9_]*) resumed>(.*)$",
        raw_line,
    )
    if resumed is None:
        return raw_line
    timestamp, syscall, suffix = resumed.groups()
    unfinished_pattern = re.compile(
        r"^\d+\.\d+ ([A-Za-z_][A-Za-z0-9_]*)\((.*)<unfinished \.\.\.>$"
    )
    resumed_pattern = re.compile(
        r"^\d+\.\d+ <\.\.\. ([A-Za-z_][A-Za-z0-9_]*) resumed>.*$"
    )
    pending: tuple[str, str] | None = None
    for line in prior_lines:
        unfinished = unfinished_pattern.fullmatch(line)
        prior_resume = resumed_pattern.fullmatch(line)
        if unfinished is not None:
            if pending is not None:
                raise AssertionError("raw trace has nested unfinished syscalls")
            pending = (unfinished.group(1), unfinished.group(2))
        elif prior_resume is not None:
            if pending is None or pending[0] != prior_resume.group(1):
                raise AssertionError("raw trace has an unmatched prior resume")
            pending = None
        elif pending is not None and not re.match(r"^\d+\.\d+ --- .+ ---$", line):
            raise AssertionError("raw trace has a syscall before the pending resume")
    if pending is None or pending[0] != syscall:
        raise AssertionError("resumed event lacks one exact unfinished entry")
    return f"{timestamp} {syscall}({pending[1]}{suffix}"


def assert_event_raw_binding(
    event: dict[str, object], raw_line: str, prior_lines: list[str] | None = None
) -> None:
    prior = [] if prior_lines is None else prior_lines
    logical_line = logical_raw_line(raw_line, prior)
    assert logical_line.startswith(f"{event['timestamp']} {event['syscall']}(")
    assert logical_line.endswith(f" = {event['result']}")
    target = str(event["target"]).removesuffix(" (deleted)")
    direct_target = json.dumps(target) in logical_line or f"<{target}>" in logical_line
    if direct_target is False:
        if prior_lines is None:
            raise AssertionError("address-based event lacks mapping history")
        _assert_mapping_target_binding(target, logical_line, prior)
    flags = event["flags"]
    if flags is not None:
        assert all(token in logical_line for token in str(flags).split("|"))
    if event["syscall"] == "msync":
        assert ", MS_SYNC)" in logical_line
    if event["syscall"] == "mprotect":
        assert "PROT_WRITE" in logical_line


def test_raw_event_binding_reconstructs_resumed_syscall() -> None:
    event = {
        "timestamp": "1.200000",
        "pid": 100,
        "line": 2,
        "syscall": "write",
        "operation": "descriptor_write",
        "target": "/project/a,b",
        "result": "1",
        "flags": None,
    }
    assert_event_raw_binding(
        event,
        "1.200000 <... write resumed>) = 1",
        ['1.100000 write(3</project/a,b>, "x", 1 <unfinished ...>'],
    )
    prior = [
        '1.000000 write(3</first>, "a", 1 <unfinished ...>',
        "1.100000 <... write resumed>) = 1",
        '1.200000 write(3</second>, "b", 1 <unfinished ...>',
    ]
    assert logical_raw_line("1.300000 <... write resumed>) = 1", prior) == (
        '1.300000 write(3</second>, "b", 1 ) = 1'
    )


# PR #1259 / discussion_r3785351127: raw evidence cannot interpose a syscall.
def test_raw_resume_rejects_interposed_syscall() -> None:
    prior = [
        '1.000000 write(3</first>, "a", 1 <unfinished ...>',
        "1.100000 close(4</second>) = 0",
    ]
    with pytest.raises(AssertionError, match="syscall before the pending resume"):
        logical_raw_line("1.200000 <... write resumed>) = 1", prior)


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
        assert_event_raw_binding(event, unrelated)


def _msync_event() -> dict[str, object]:
    return {
        "flags": None,
        "result": "0",
        "syscall": "msync",
        "target": "/case/fixture.txt",
        "timestamp": "1700000000.000002",
    }


def test_msync_binding_uses_prior_exact_mmap_interval() -> None:
    mapping = (
        "1700000000.000001 mmap(NULL, 4096, PROT_READ|PROT_WRITE, MAP_SHARED, "
        "3</case/fixture.txt>, 0) = 0x7f000000"
    )
    raw = "1700000000.000002 msync(0x7f000800, 8, MS_SYNC) = 0"
    assert_event_raw_binding(_msync_event(), raw, [mapping])


@pytest.mark.parametrize(
    ("mapping", "raw"),
    [
        (
            "1700000000.000001 mmap(NULL, 4096, PROT_READ|PROT_WRITE, "
            "MAP_SHARED, 3</case/unrelated.txt>, 0) = 0x7f000000",
            "1700000000.000002 msync(0x7f000800, 8, MS_SYNC) = 0",
        ),
        (
            "1700000000.000001 mmap(NULL, 4096, PROT_READ|PROT_WRITE, "
            "MAP_SHARED, 3</case/fixture.txt>, 0) = 0x7f000000",
            "1700000000.000002 msync(0x7f002000, 8, MS_SYNC) = 0",
        ),
        (
            "1700000000.000001 mmap(NULL, 4096, PROT_READ|PROT_WRITE, "
            "MAP_SHARED, 3</case/fixture.txt>, 0) = 0x7f000000",
            "1700000000.000002 msync(0x7f000800, 8, MS_ASYNC) = 0",
        ),
    ],
)
def test_msync_binding_rejects_wrong_provenance(mapping: str, raw: str) -> None:
    with pytest.raises(AssertionError):
        assert_event_raw_binding(_msync_event(), raw, [mapping])


def test_msync_binding_rejects_mapping_removed_before_event() -> None:
    mapping = (
        "1700000000.000001 mmap(NULL, 4096, PROT_READ|PROT_WRITE, MAP_SHARED, "
        "3</case/fixture.txt>, 0) = 0x7f000000"
    )
    removal = "1700000000.000002 munmap(0x7f000000, 4096) = 0"
    raw = "1700000000.000003 msync(0x7f000800, 8, MS_SYNC) = 0"
    event = {**_msync_event(), "timestamp": "1700000000.000003"}
    with pytest.raises(AssertionError, match="removed"):
        assert_event_raw_binding(event, raw, [mapping, removal])


def successful_exec_lines(lines: list[str]) -> list[str]:
    successful: list[str] = []
    for index, line in enumerate(lines):
        logical = logical_raw_line(line, lines[:index])
        if re.match(r"^\d+\.\d+ execve(?:at)?\(", logical) and logical.endswith(" = 0"):
            successful.append(logical)
    return successful


def raw_exec_record(line: str) -> tuple[str, list[str]]:
    match = re.match(r'^\d+\.\d+ execve\(("(?:\\.|[^"\\])*")\s*,', line) or re.match(
        r'^\d+\.\d+ execveat\([^,]+, ("(?:\\.|[^"\\])*")\s*,',
        line,
    )
    if match is None:
        raise AssertionError("successful exec line lacks an exact executable")
    executable = ast.literal_eval(match.group(1))
    assert isinstance(executable, str)
    start = line.find("[", match.end())
    if start < 0:
        raise AssertionError("successful exec line lacks an exact argv")
    quoted = False
    escaped = False
    for index in range(start + 1, len(line)):
        char = line[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "]":
            argv = ast.literal_eval(line[start : index + 1])
            assert isinstance(argv, list)
            assert all(isinstance(item, str) for item in argv)
            return executable, argv
    raise AssertionError("successful exec line has truncated argv")


def test_raw_exec_binding_uses_executable_and_exact_argv() -> None:
    line = (
        '1700000000.000001 execve("/bin/unrelated", ["/bin/expected"], ["LANG=C"]) = 0'
    )
    assert raw_exec_record(line) == ("/bin/unrelated", ["/bin/expected"])


def assert_policy_evidence(report: dict[str, object], policy_path: Path) -> None:
    evidence = report["policy"]
    assert set(evidence) == {"minimum_strace_version", "path", "sha256", "strace"}
    assert evidence["path"] == str(policy_path.resolve())
    assert evidence["sha256"] == hashlib.sha256(policy_path.read_bytes()).hexdigest()
    assert evidence["minimum_strace_version"] == "6.8"
    strace = evidence["strace"]
    assert set(strace) == {"executable", "package", "sha256", "version"}
    executable = Path("/usr/bin/strace")
    assert strace["executable"] == os.path.realpath(executable)
    assert strace["sha256"] == hashlib.sha256(executable.read_bytes()).hexdigest()
    assert re.fullmatch(r"strace=\S+", strace["package"])
    assert strace["version"] == "6.8"


def load_started_preflight(artifact_root: Path) -> dict[str, object]:
    top_files = sorted(path.name for path in artifact_root.iterdir() if path.is_file())
    assert top_files == ["job-result.json", "preflight.json", "source.json"]
    assert json.loads((artifact_root / "job-result.json").read_text()) == {
        "status": "started"
    }
    assert json.loads((artifact_root / "source.json").read_text()) == {
        "qualified_sha": os.environ["RFC0022_QUALIFIED_SHA"]
    }
    preflight = json.loads((artifact_root / "preflight.json").read_text())
    assert preflight["authority_id"] == "rfc0022-linux-strace-v1"
    assert preflight["status"] == "available"
    return preflight


def result_class(result: str) -> str:
    if result.startswith("-1 "):
        return " ".join(result.split(maxsplit=2)[:2])
    if result == "changed":
        return "changed"
    return "success"


# PR #1259 / discussion_r3785351127: independent evidence accepts resumed final exec.
def test_successful_exec_reconstructs_unfinished_resume() -> None:
    lines = [
        '1.000000 execve("/usr/bin/tool", ["tool", "arg"], 0x0 <unfinished ...>',
        "1.100000 <... execve resumed>) = 0",
    ]
    logical = '1.100000 execve("/usr/bin/tool", ["tool", "arg"], 0x0 ) = 0'
    assert successful_exec_lines(lines) == [logical]
    assert raw_exec_record(logical) == ("/usr/bin/tool", ["tool", "arg"])


@pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: RFC-0022 Linux authority needs POSIX ownership and modes",
)
def test_raw_trace_inventory_and_sealing_are_exact(tmp_path: Path) -> None:
    trace = tmp_path / "raw-inventory"
    trace.mkdir()
    path = trace / "trace.100"
    path.write_text("1700000000.000001 +++ exited with 0 +++\n", encoding="utf-8")
    trace.chmod(0o700)
    raw = path.read_bytes()
    assert raw_trace_metadata(trace, expected_uid=trace.stat().st_uid) == [
        {
            "pid": 100,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
            "terminal": "+++ exited with 0 +++",
        }
    ]
    seal_trace_directory(trace)
    assert trace.stat().st_mode & 0o777 == 0o555
    assert path.stat().st_mode & 0o777 == 0o444


# Existing exact fcntl/ioctl classification belongs with raw FD evidence.
def test_safe_fd_metadata_commands_are_explicit_and_non_mutating(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "safe-fd-commands"
    _write_trace(
        trace,
        [
            'openat(AT_FDCWD</project>, "input.py", O_RDONLY) = 3</project/input.py>',
            "ioctl(3</project/input.py>, TCGETS, 0x1234) = -1 ENOTTY (Inappropriate ioctl for device)",
            "ioctl(3</project/input.py>, TIOCGWINSZ, 0x1234) = -1 ENOTTY (Inappropriate ioctl for device)",
            "ioctl(3</project/input.py>, FIOCLEX) = 0",
            "fcntl(3</project/input.py>, F_GETFD) = 0",
            "fcntl(3</project/input.py>, F_SETFD, FD_CLOEXEC) = 0",
            "close(3</project/input.py>) = 0",
            "+++ exited with 0 +++",
        ],
    )
    violations, _, _ = parse_trace_directory(trace, POLICY, Path("/project"))
    assert violations == []


# PR #1259 causal-evidence regression: empty child evidence cannot predate creation.
def test_terminal_only_child_before_creation_fails_closed(tmp_path: Path) -> None:
    traces = tmp_path / "terminal-before-creation"
    traces.mkdir()
    (traces / "trace.100").write_text(
        "1700000000.000005 clone(child_stack=NULL, flags=SIGCHLD) = 200\n"
        "1700000000.000006 +++ exited with 0 +++\n",
        encoding="utf-8",
    )
    (traces / "trace.200").write_text(
        "1700000000.000001 +++ exited with 0 +++\n", encoding="utf-8"
    )
    with pytest.raises(AuthorityError, match="child trace predates process creation"):
        parse_trace_directory(traces, POLICY, Path("/project"))


# PR #1259 causal-evidence regression: equal-time child creation is a valid boundary.
def test_terminal_only_child_at_creation_boundary_is_accepted(tmp_path: Path) -> None:
    traces = tmp_path / "terminal-at-creation"
    traces.mkdir()
    (traces / "trace.100").write_text(
        "1700000000.000001 clone(child_stack=NULL, flags=SIGCHLD) = 200\n"
        "1700000000.000002 +++ exited with 0 +++\n",
        encoding="utf-8",
    )
    (traces / "trace.200").write_text(
        "1700000000.000001 +++ exited with 0 +++\n", encoding="utf-8"
    )
    violations, metadata, pids = parse_trace_directory(traces, POLICY, Path("/project"))
    assert violations == []
    assert [(item["pid"], item["role"], item["parent_pid"]) for item in metadata] == [
        (100, "root", None),
        (200, "descendant", 100),
    ]
    assert pids == {100, 200}


# PR #1259 causal-evidence regression: PID aliases cannot overwrite early evidence.
def test_noncanonical_trace_pid_alias_fails_closed(tmp_path: Path) -> None:
    traces = tmp_path / "pid-alias"
    traces.mkdir()
    bodies = {
        "trace.100": (
            "1700000000.000005 clone(child_stack=NULL, flags=SIGCHLD) = 200\n"
            "1700000000.000009 +++ exited with 0 +++\n"
        ),
        "trace.0200": "1700000000.000001 +++ exited with 0 +++\n",
        "trace.200": "1700000000.000006 +++ exited with 0 +++\n",
    }
    for name, body in bodies.items():
        (traces / name).write_text(body, encoding="utf-8")
    with pytest.raises(
        AuthorityError, match="unexpected trace directory entry: trace.0200"
    ):
        parse_trace_directory(traces, POLICY, Path("/project"))


# PR #1259 evidence regression: raw manifests use canonical positive PID names.
def test_raw_inventory_rejects_noncanonical_trace_pid(tmp_path: Path) -> None:
    traces = tmp_path / "raw-pid-alias"
    traces.mkdir(mode=0o700)
    (traces / "trace.0200").write_text(
        "1700000000.000001 +++ exited with 0 +++\n", encoding="utf-8"
    )
    with pytest.raises(OSError, match="unexpected raw trace entry: trace.0200"):
        raw_trace_metadata(traces, expected_uid=traces.stat().st_uid)


# PR #1259 / discussion_r3785903822: exec preserves a CLONE_FS cwd space.
def test_clone_fs_cwd_sharing_survives_exec(tmp_path: Path) -> None:
    traces = tmp_path / "clone-fs-exec"
    traces.mkdir()
    (traces / "trace.100").write_text(
        "1700000000.000001 clone(child_stack=NULL, flags=CLONE_FS|SIGCHLD) = 200\n"
        '1700000000.000005 unlink("marker") = -1 ENOENT (No such file or directory)\n'
        "1700000000.000006 +++ exited with 0 +++\n",
        encoding="utf-8",
    )
    (traces / "trace.200").write_text(
        '1700000000.000002 execve("/bin/tool", ["tool"], []) = 0\n'
        '1700000000.000003 chdir("/shared-after-exec") = 0\n'
        "1700000000.000004 +++ exited with 0 +++\n",
        encoding="utf-8",
    )
    violations, _, _ = parse_trace_directory(traces, POLICY, Path("/project"))
    assert len(violations) == 1
    assert violations[0].target == "/shared-after-exec/marker"


# PR #1259 / discussion_r3785903832: blocked safe calls do not consume map provenance.
@pytest.mark.parametrize(
    ("entry", "resume"),
    [
        (
            "futex(0x2000, FUTEX_WAIT_PRIVATE, 0, NULL",
            "futex resumed>) = -1 EAGAIN (Resource temporarily unavailable)",
        ),
        ('read(3<pipe:[42]>, "x", 1', "read resumed>) = 1"),
        ("wait4(300, 0x2000, 0, NULL", "wait4 resumed>) = 300"),
        ("waitid(P_PID, 300, 0x2000, WEXITED, NULL", "waitid resumed>) = 0"),
    ],
)
def test_state_independent_overlap_does_not_make_mapping_ambiguous(
    tmp_path: Path, entry: str, resume: str
) -> None:
    traces = tmp_path / "independent-overlap"
    traces.mkdir()
    (traces / "trace.100").write_text(
        "1700000000.000001 clone(child_stack=NULL, flags=CLONE_VM|SIGCHLD) = 200\n"
        "1700000000.000002 mmap(NULL, 4096, PROT_READ, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0 <unfinished ...>\n"
        "1700000000.000004 <... mmap resumed>) = 0x1000\n"
        "1700000000.000006 +++ exited with 0 +++\n",
        encoding="utf-8",
    )
    (traces / "trace.200").write_text(
        f"1700000000.000003 {entry} <unfinished ...>\n"
        f"1700000000.000005 <... {resume}\n"
        "1700000000.000006 +++ exited with 0 +++\n",
        encoding="utf-8",
    )
    violations, _, _ = parse_trace_directory(traces, POLICY, Path("/project"))
    assert violations == []
