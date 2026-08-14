"""Contract for the RFC-0022 P0.4 Linux write-attempt authority."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from rfc0022_strace_authority import (  # noqa: E402
    POLICY_KEYS,
    POLICY_SHA256,
    load_policy,
    run_authority,
    snapshot_root,
    strace_preflight,
)
from rfc0022_strace_authority import (  # noqa: E402
    main as authority_main,
)
from rfc0022_strace_model import AuthorityError  # noqa: E402
from rfc0022_strace_parser import parse_trace_directory  # noqa: E402

POLICY_PATH = ROOT / "config/rfc0022-linux-strace-policy.json"
POLICY, POLICY_DIGEST = load_policy(POLICY_PATH)


def _write_trace(
    directory: Path, pid: int, bodies: list[str], *, start: int = 1
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    text = "".join(
        f"1700000000.{index:06d} {body}\n"
        for index, body in enumerate(bodies, start=start)
    )
    path = directory / f"trace.{pid}"
    path.write_text(text, encoding="utf-8")
    return path


def _parse(directory: Path, cwd: Path = Path("/project")) -> list[dict[str, object]]:
    violations, _, _ = parse_trace_directory(directory, POLICY, cwd)
    return [asdict(item) for item in violations]


def _event(
    *,
    line: int,
    syscall: str,
    operation: str,
    target: str,
    result: str,
    pid: int = 100,
    flags: str | None = None,
    timestamp_index: int | None = None,
) -> dict[str, object]:
    return {
        "timestamp": f"1700000000.{timestamp_index or line:06d}",
        "pid": pid,
        "line": line,
        "syscall": syscall,
        "operation": operation,
        "target": target,
        "result": result,
        "flags": flags,
    }


def test_policy_is_exact_closed_and_digest_bound() -> None:
    assert POLICY_DIGEST == POLICY_SHA256
    assert set(POLICY) == POLICY_KEYS
    assert POLICY["schema_version"] == 1
    assert POLICY["authority_id"] == "rfc0022-linux-strace-v1"
    assert POLICY["minimum_strace_version"] == "6.8"
    assert POLICY["page_size"] == 4096
    assert POLICY["trace_arguments"] == [
        "-ff",
        "-yy",
        "-q",
        "-ttt",
        "-s",
        "65535",
        "-v",
        "--kill-on-exit",
        "-e",
        "trace=%file,%desc,%memory,%network,clone,clone3,fork,vfork,execve,execveat,"
        "exit,exit_group,io_uring_setup,io_uring_enter,io_uring_register,"
        "io_setup,io_submit,io_cancel,io_destroy,io_getevents,process_vm_writev",
    ]
    assert set(POLICY["write_open_flags"]) == {
        "O_APPEND",
        "O_CREAT",
        "O_RDWR",
        "O_TMPFILE",
        "O_TRUNC",
        "O_WRONLY",
    }
    assert POLICY["unix_path_mutators"] == ["bind"]
    assert "allowlist" not in json.dumps(POLICY).lower()


def test_policy_cannot_be_weakened_at_runtime(tmp_path: Path) -> None:
    weakened = dict(POLICY)
    weakened["write_open_flags"] = ["O_WRONLY"]
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(weakened, sort_keys=True), encoding="utf-8")
    with pytest.raises(AuthorityError, match="policy digest mismatch"):
        load_policy(path)


def test_report_cannot_overlap_raw_trace_directory(tmp_path: Path) -> None:
    trace_dir = tmp_path / "trace"
    report = trace_dir / "trace.100"
    with pytest.raises(
        AuthorityError, match="report path must be outside the raw trace directory"
    ):
        run_authority(
            policy_path=POLICY_PATH,
            trace_dir=trace_dir,
            report_path=report,
            monitor_roots=[tmp_path],
            target_cwd=tmp_path,
            target=["/bin/true"],
            timeout=1,
        )
    assert report.exists() is False


def test_preflight_fails_closed_when_strace_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(AuthorityError, match="strace is absent"):
        strace_preflight("6.8")


def test_run_setup_failure_writes_normalized_error_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    report_path = tmp_path / "report.json"
    code = authority_main(
        [
            "run",
            "--policy",
            str(POLICY_PATH),
            "--trace-dir",
            str(tmp_path / "trace"),
            "--report",
            str(report_path),
            "--monitor-root",
            str(tmp_path),
            "--target-cwd",
            str(tmp_path),
            "--",
            "/bin/true",
        ]
    )
    assert code == 2
    assert json.loads(report_path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "authority_id": "rfc0022-linux-strace-v1",
        "authority_status": "error",
        "outcome": "indeterminate",
        "errors": ["strace is absent"],
        "policy": {"path": str(POLICY_PATH.resolve())},
        "trace_files": [],
        "violations": [],
        "target": {
            "argv": ["/bin/true"],
            "expected_returncode": 0,
            "returncode": None,
        },
    }


def test_preflight_records_exact_binary_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "strace"
    executable.write_text(
        "#!/bin/sh\nprintf 'strace -- version 6.8\n'\n", encoding="utf-8"
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert strace_preflight("6.8", str(executable)) == {
        "version": "6.8",
        "executable": str(executable.resolve()),
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "package": None,
    }


def test_failed_open_and_file_fd_write_are_exact_violations(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            'openat(AT_FDCWD</project>, "denied", O_WRONLY|O_CREAT, 0600) = -1 EACCES (Permission denied)',
            'write(3</project/existing>, "x", 1) = -1 EBADF (Bad file descriptor)',
            'write(1<pipe:[42]>, "ok", 2) = 2',
            "+++ exited with 0 +++",
        ],
    )
    assert _parse(trace) == [
        _event(
            line=1,
            syscall="openat",
            operation="write_capable_open",
            target="/project/denied",
            result="-1 EACCES (Permission denied)",
            flags="O_CREAT|O_WRONLY",
        ),
        _event(
            line=2,
            syscall="write",
            operation="descriptor_write",
            target="/project/existing",
            result="-1 EBADF (Bad file descriptor)",
        ),
    ]


def test_relative_path_mutators_resolve_cwd_and_dirfd(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            'rename("old", "new") = -1 ENOENT (No such file or directory)',
            'unlinkat(4</project/sub>, "gone", 0) = 0',
            "+++ exited with 0 +++",
        ],
    )
    assert _parse(trace) == [
        _event(
            line=1,
            syscall="rename",
            operation="pathname_mutation",
            target="/project/old",
            result="-1 ENOENT (No such file or directory)",
        ),
        _event(
            line=1,
            syscall="rename",
            operation="pathname_mutation",
            target="/project/new",
            result="-1 ENOENT (No such file or directory)",
        ),
        _event(
            line=2,
            syscall="unlinkat",
            operation="pathname_mutation",
            target="/project/sub/gone",
            result="0",
        ),
    ]


def test_unix_socket_bind_is_a_path_mutation_even_when_denied(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            "bind(3<socket:[1]>, {sa_family=AF_INET, sin_port=htons(0)}, 16) = 0",
            'bind(4<socket:[2]>, {sa_family=AF_UNIX, sun_path="sock"}, 7) = -1 EACCES (Permission denied)',
            'bind(5<socket:[3]>, {sa_family=AF_UNIX, sun_path=@"abstract"}, 11) = 0',
            "+++ exited with 0 +++",
        ],
    )
    assert _parse(trace) == [
        _event(
            line=2,
            syscall="bind",
            operation="unix_socket_path_mutation",
            target="/project/sock",
            result="-1 EACCES (Permission denied)",
        )
    ]


def test_shared_mapping_transition_and_async_are_exact(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            "mmap(NULL, 4096, PROT_READ|PROT_WRITE, MAP_PRIVATE, 3</lib/libx.so>, 0) = 0x1000",
            "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 4</project/db>, 0) = 0x2000",
            "mprotect(0x2000, 4096, PROT_READ|PROT_WRITE) = 0",
            "mmap(NULL, 4096, PROT_READ|PROT_WRITE, MAP_SHARED, 5</project/out>, 0) = -1 EACCES (Permission denied)",
            "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 6</project/remove>, 0) = 0x3000",
            "madvise(0x3000, 4096, MADV_REMOVE) = -1 EACCES (Permission denied)",
            "io_uring_setup(8, {}) = -1 EPERM (Operation not permitted)",
            "+++ exited with 0 +++",
        ],
    )
    assert _parse(trace) == [
        _event(
            line=3,
            syscall="mprotect",
            operation="shared_mapping_write",
            target="/project/db",
            result="0",
        ),
        _event(
            line=4,
            syscall="mmap",
            operation="shared_writable_mapping",
            target="/project/out",
            result="-1 EACCES (Permission denied)",
            flags="PROT_READ|PROT_WRITE|MAP_SHARED",
        ),
        _event(
            line=6,
            syscall="madvise",
            operation="shared_mapping_remove",
            target="/project/remove",
            result="-1 EACCES (Permission denied)",
            flags="MADV_REMOVE",
        ),
        _event(
            line=7,
            syscall="io_uring_setup",
            operation="asynchronous_write_capability",
            target="<kernel-async>",
            result="-1 EPERM (Operation not permitted)",
        ),
    ]


def test_descendant_fd_write_and_trace_closure_are_exact(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        ["clone(child_stack=NULL, flags=SIGCHLD) = 200", "+++ exited with 0 +++"],
    )
    child_path = _write_trace(
        trace,
        200,
        ['write(7</project/inherited>, "x", 1) = 1', "+++ exited with 0 +++"],
        start=2,
    )
    violations, metadata, pids = parse_trace_directory(trace, POLICY, Path("/project"))
    assert [asdict(item) for item in violations] == [
        _event(
            line=1,
            pid=200,
            syscall="write",
            timestamp_index=2,
            operation="descriptor_write",
            target="/project/inherited",
            result="1",
        )
    ]
    assert metadata == [
        {
            "pid": 100,
            "sha256": hashlib.sha256((trace / "trace.100").read_bytes()).hexdigest(),
            "terminal": "+++ exited with 0 +++",
            "role": "root",
            "parent_pid": None,
        },
        {
            "pid": 200,
            "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest(),
            "terminal": "+++ exited with 0 +++",
            "role": "descendant",
            "parent_pid": 100,
        },
    ]
    assert pids == {100, 200}


@pytest.mark.parametrize(
    ("bodies", "message"),
    [
        (
            ["getrandom(NULL, 0, 0) = 0", "+++ exited with 0 +++"],
            "unknown traced syscall",
        ),
        (
            [
                'write(3, "x", 1) = -1 EBADF (Bad file descriptor)',
                "+++ exited with 0 +++",
            ],
            "unannotated destination fd",
        ),
        (
            ["read(3<pipe:[1]>,  <unfinished ...>", "+++ exited with 0 +++"],
            "no resumed syscall",
        ),
        (
            ['<... read resumed>"x", 1) = 1', "+++ exited with 0 +++"],
            "unmatched resume",
        ),
        (['open("x", O_RDONLY) = 3</project/x>'], "terminal marker"),
    ],
)
def test_malformed_or_unknown_trace_fails_closed(
    tmp_path: Path, bodies: list[str], message: str
) -> None:
    trace = tmp_path / "trace"
    _write_trace(trace, 100, bodies)
    with pytest.raises(AuthorityError, match=message):
        _parse(trace)


def test_missing_child_trace_fails_closed(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(trace, 100, ["vfork() = 201", "+++ exited with 0 +++"])
    with pytest.raises(AuthorityError, match=r"child trace files missing: \[201\]"):
        _parse(trace)


def test_matched_resume_and_nested_openat2_structure_parse(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            "read(3<pipe:[1]>,  <unfinished ...>",
            '<... read resumed>"x", 1) = 1',
            'openat2(AT_FDCWD</project>, "nested\\"name", {flags=O_WRONLY|O_CLOEXEC, mode=0600}, 24) = 4</project/nested"name>',
            "+++ exited with 0 +++",
        ],
    )
    assert _parse(trace) == [
        _event(
            line=3,
            syscall="openat2",
            operation="write_capable_open",
            target='/project/nested"name',
            result='4</project/nested"name>',
            flags="O_WRONLY",
        )
    ]


def test_snapshot_binds_identity_metadata_and_content(tmp_path: Path) -> None:
    path = tmp_path / "value.txt"
    path.write_bytes(b"same bytes")
    before = snapshot_root(tmp_path)
    path.write_bytes(b"changed")
    path.write_bytes(b"same bytes")
    after = snapshot_root(tmp_path)
    assert before["root"] == after["root"]
    assert before["records"][1]["sha256"] == after["records"][1]["sha256"]
    assert before != after
