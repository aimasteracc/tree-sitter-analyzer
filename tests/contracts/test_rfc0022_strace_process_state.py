import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from rfc0022_strace_authority import load_policy  # noqa: E402
from rfc0022_strace_model import AuthorityError  # noqa: E402
from rfc0022_strace_parser import parse_trace_directory  # noqa: E402

POLICY, _ = load_policy(ROOT / "config/rfc0022-linux-strace-policy.json")


def _write_trace(directory: Path, pid: int, bodies: list[str], start: int = 1) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"trace.{pid}"
    lines = (
        f"1700000000.{index:06d} {body}\n"
        for index, body in enumerate(bodies, start=start)
    )
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _parse(directory: Path) -> list[dict[str, object]]:
    violations, _, _ = parse_trace_directory(directory, POLICY, Path("/project"))
    return [asdict(item) for item in violations]


def _event(**event: object) -> dict[str, object]:
    line = cast(int, event["line"])
    index = cast(int, event.pop("timestamp_index", line))
    event.setdefault("pid", 100)
    event.setdefault("flags", None)
    return {"timestamp": f"1700000000.{index:06d}", **event}


def test_exec_clears_stale_mapping_provenance(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 4</project/old>, 0) = 0x4000",
            'execve("/bin/target", ["target"], []) = 0',
            "mprotect(0x4000, 4096, PROT_READ|PROT_WRITE) = 0",
            "+++ exited with 0 +++",
        ],
    )
    with pytest.raises(
        AuthorityError, match="mapping provenance does not cover the requested range"
    ):
        _parse(trace)


def test_overlapping_mapping_ranges_cannot_hide_shared_target(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            "mmap(NULL, 4096, PROT_READ, MAP_PRIVATE, 3</project/private>, 0) = 0x1000",
            "mmap(0x1000, 4096, PROT_READ, MAP_SHARED|MAP_FIXED, 4</project/shared>, 0) = 0x1000",
            "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 5</project/adjacent>, 0) = 0x2000",
            "mprotect(0x1000, 8192, PROT_READ|PROT_WRITE) = 0",
            "+++ exited with 0 +++",
        ],
    )
    assert _parse(trace) == [
        _event(
            line=4,
            syscall="mprotect",
            operation="shared_mapping_write",
            target="/project/adjacent",
            result="0",
        ),
        _event(
            line=4,
            syscall="mprotect",
            operation="shared_mapping_write",
            target="/project/shared",
            result="0",
        ),
    ]


def test_child_inherits_parent_cwd_at_creation_edge(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            'chdir("sub") = 0',
            "clone(child_stack=NULL, flags=SIGCHLD) = 200",
            "+++ exited with 0 +++",
        ],
    )
    _write_trace(
        trace,
        200,
        [
            'unlink("gone") = -1 ENOENT (No such file or directory)',
            "+++ exited with 0 +++",
        ],
        start=3,
    )
    assert _parse(trace) == [
        _event(
            line=1,
            pid=200,
            syscall="unlink",
            timestamp_index=3,
            operation="pathname_mutation",
            target="/project/sub/gone",
            result="-1 ENOENT (No such file or directory)",
        )
    ]


def test_orphan_trace_pid_fails_closed(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(trace, 100, ["+++ exited with 0 +++"])
    _write_trace(trace, 200, ["+++ exited with 0 +++"])
    with pytest.raises(
        AuthorityError,
        match=r"trace graph must have exactly one root: \[100, 200\]",
    ):
        _parse(trace)


def test_root_exec_must_match_expected_target(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        ['execve("/bin/wrong", ["wrong"], []) = 0', "+++ exited with 0 +++"],
    )
    with pytest.raises(
        AuthorityError, match="final root exec does not match the expected target"
    ):
        parse_trace_directory(
            trace,
            POLICY,
            Path("/project"),
            expected_executable="/bin/expected",
        )


def test_root_exec_argv_must_match_expected_target(tmp_path: Path) -> None:
    trace = tmp_path / "wrong-argv"
    _write_trace(
        trace,
        100,
        [
            'execve("/bin/expected", ["/bin/other"], []) = 0',
            "+++ exited with 0 +++",
        ],
    )
    with pytest.raises(AuthorityError, match="exec argv does not match"):
        parse_trace_directory(
            trace,
            POLICY,
            Path("/project"),
            expected_executable="/bin/expected",
            expected_argv=["/bin/expected"],
        )


def test_relative_execveat_cannot_spoof_expected_target(tmp_path: Path) -> None:
    trace = tmp_path / "relative-execveat"
    _write_trace(
        trace,
        100,
        [
            'execveat(7</malicious>, "expected", ["expected"], [], 0) = 0',
            "+++ exited with 0 +++",
        ],
    )
    with pytest.raises(AuthorityError, match="final root exec path is not absolute"):
        parse_trace_directory(
            trace,
            POLICY,
            Path("/project"),
            expected_executable=os.path.realpath("expected"),
        )


@pytest.mark.parametrize(
    ("syscall", "command", "result"),
    [
        ("fcntl", "UNKNOWN_COMMAND", "0"),
        ("ioctl", "UNKNOWN_COMMAND", "0"),
        ("ioctl", "TCGETS", "0"),
    ],
)
def test_unknown_fd_commands_fail_closed(
    tmp_path: Path, syscall: str, command: str, result: str
) -> None:
    trace = tmp_path / f"{syscall}-{command}"
    _write_trace(
        trace,
        100,
        [
            'openat(AT_FDCWD</project>, "input.py", O_RDONLY) = 3</project/input.py>',
            f"{syscall}(3</project/input.py>, {command}, 0) = {result}",
            "close(3</project/input.py>) = 0",
            "+++ exited with 0 +++",
        ],
    )
    with pytest.raises(
        AuthorityError, match=f"unclassified {syscall} on filesystem fd"
    ):
        _parse(trace)


def test_vfork_child_mapping_updates_parent_shared_vm(tmp_path: Path) -> None:
    trace = tmp_path / "vfork-shared-vm"
    _write_trace(
        trace,
        100,
        [
            "mmap(NULL, 4096, PROT_READ, MAP_PRIVATE, 3</project/private>, 0) = 0x1000",
            "vfork() = 200",
            "mprotect(0x1000, 4096, PROT_READ|PROT_WRITE) = 0",
            "+++ exited with 0 +++",
        ],
    )
    _write_trace(
        trace,
        200,
        [
            "mmap(0x1000, 4096, PROT_READ, MAP_SHARED|MAP_FIXED, 4</project/db>, 0) = 0x1000",
            "+++ exited with 0 +++",
        ],
        start=2,
    )
    assert _parse(trace) == [
        _event(
            line=3,
            syscall="mprotect",
            operation="shared_mapping_write",
            target="/project/db",
            result="0",
        )
    ]


def test_unannotated_file_mapping_fails_closed(tmp_path: Path) -> None:
    trace = tmp_path / "unknown-mmap-fd"
    _write_trace(
        trace,
        100,
        [
            "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 4, 0) = 0x1000",
            "mprotect(0x1000, 4096, PROT_READ|PROT_WRITE) = 0",
            "+++ exited with 0 +++",
        ],
    )
    with pytest.raises(
        AuthorityError, match="mmap filesystem fd provenance is unknown"
    ):
        _parse(trace)


@pytest.mark.parametrize("advice", ["MADV_DONTNEED", "MADV_PAGEOUT", "MADV_REMOVE"])
def test_mapping_writeback_advice_is_a_violation(tmp_path: Path, advice: str) -> None:
    trace = tmp_path / advice
    _write_trace(
        trace,
        100,
        [
            "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 4</project/db>, 0) = 0x1000",
            f"madvise(0x1000, 4096, {advice}) = 0",
            "+++ exited with 0 +++",
        ],
    )
    assert _parse(trace) == [
        _event(
            line=2,
            syscall="madvise",
            operation="shared_mapping_writeback",
            target="/project/db",
            result="0",
            flags=advice,
        )
    ]


@pytest.mark.parametrize(
    ("advice", "target"),
    [
        ("MADV_PAGEOUT", "<memory-pageout>"),
        ("MADV_REMOVE", "<memory-remove>"),
    ],
)
def test_global_mapping_writeback_advice_cannot_hide_without_file_target(
    tmp_path: Path, advice: str, target: str
) -> None:
    trace = tmp_path / advice
    _write_trace(
        trace,
        100,
        [
            "mmap(NULL, 4096, PROT_READ|PROT_WRITE, "
            "MAP_PRIVATE|MAP_ANONYMOUS, -1, 0) = 0x1000",
            f"madvise(0x1000, 4096, {advice}) = -1 EINVAL (Invalid argument)",
            "+++ exited with 0 +++",
        ],
    )
    assert _parse(trace) == [
        _event(
            line=2,
            syscall="madvise",
            operation="global_writeback",
            target=target,
            result="-1 EINVAL (Invalid argument)",
            flags=advice,
        )
    ]


def test_global_sync_is_never_clean(tmp_path: Path) -> None:
    trace = tmp_path / "sync"
    _write_trace(trace, 100, ["sync() = 0", "+++ exited with 0 +++"])
    assert _parse(trace) == [
        _event(
            line=1,
            syscall="sync",
            operation="global_writeback",
            target="<all-filesystems>",
            result="0",
        )
    ]


@pytest.mark.parametrize("syscall", ["mq_unlink", "ptrace"])
def test_uncategorized_syscalls_fail_closed_under_trace_all(
    tmp_path: Path, syscall: str
) -> None:
    trace = tmp_path / syscall
    _write_trace(trace, 100, [f"{syscall}(0) = 0", "+++ exited with 0 +++"])
    with pytest.raises(AuthorityError, match=f"unknown traced syscall: {syscall}"):
        _parse(trace)


def test_unexpected_trace_directory_entry_fails_closed(tmp_path: Path) -> None:
    trace = tmp_path / "unexpected-entry"
    _write_trace(trace, 100, ["+++ exited with 0 +++"])
    (trace / "forged").write_text("ignored", encoding="utf-8")
    with pytest.raises(AuthorityError, match="unexpected trace directory entry"):
        _parse(trace)


def test_process_creation_with_unknown_result_fails_closed(tmp_path: Path) -> None:
    trace = tmp_path / "unknown-clone"
    _write_trace(
        trace,
        100,
        ["clone(child_stack=NULL, flags=SIGCHLD) = ?", "+++ exited with 0 +++"],
    )
    with pytest.raises(AuthorityError, match="exact child pid"):
        parse_trace_directory(trace, POLICY, Path("/project"))


# PR #1259 / discussion_r3785351127: creation entry causally precedes its child.
@pytest.mark.parametrize(
    ("syscall", "entry"),
    [
        ("clone", "child_stack=NULL, flags=SIGCHLD"),
        ("clone3", "{flags=SIGCHLD}, 88"),
    ],
)
def test_unfinished_creation_precedes_child_syscall(
    tmp_path: Path, syscall: str, entry: str
) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        101,
        [
            'openat(AT_FDCWD</project>, "child.txt", O_WRONLY|O_CREAT, 0600) = 3</project/child.txt>',
            "+++ exited with 0 +++",
        ],
        start=2,
    )
    (trace / "trace.100").write_text(
        f"1700000000.000001 {syscall}({entry} <unfinished ...>\n"
        f"1700000000.000003 <... {syscall} resumed>) = 101\n"
        "1700000000.000004 +++ exited with 0 +++\n",
        encoding="utf-8",
    )
    assert _parse(trace) == [
        _event(
            line=1,
            pid=101,
            timestamp_index=2,
            syscall="openat",
            operation="write_capable_open",
            target="/project/child.txt",
            result="3</project/child.txt>",
            flags="O_CREAT|O_WRONLY",
        )
    ]


# PR #1259 / discussion_r3785351127: resumed calls cannot predate their creator.
def test_child_entry_before_creation_fails_closed(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        ["clone(child_stack=NULL, flags=SIGCHLD) = 200", "+++ exited with 0 +++"],
        start=2,
    )
    (trace / "trace.200").write_text(
        '1700000000.000001 write(3</project/x>, "x", 1 <unfinished ...>\n'
        "1700000000.000003 <... write resumed>) = 1\n"
        "1700000000.000005 +++ exited with 0 +++\n",
        encoding="utf-8",
    )
    with pytest.raises(AuthorityError, match="child syscall predates process creation"):
        _parse(trace)


# PR #1259 / discussion_r3785351127: PID order cannot resolve equal-time peers.
def test_equal_time_unrelated_children_fail_closed(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            "clone(child_stack=NULL, flags=SIGCHLD) = 101",
            "clone(child_stack=NULL, flags=SIGCHLD) = 102",
            "+++ exited with 0 +++",
        ],
    )
    for pid, target in ((101, "a"), (102, "b")):
        _write_trace(
            trace,
            pid,
            [f'unlink("{target}") = 0', "+++ exited with 0 +++"],
            start=3,
        )
    with pytest.raises(
        AuthorityError, match="ambiguous cross-process syscall entry order"
    ):
        _parse(trace)


# PR #1259 / discussion_r3785351127: never guess within an unfinished state change.
def test_overlapping_shared_mapping_transition_fails_closed(tmp_path: Path) -> None:
    traces = tmp_path / "traces"
    _write_trace(
        traces,
        100,
        [
            "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 3</project/db>, 0) = 0x1000",
            "clone(child_stack=NULL, flags=CLONE_VM|SIGCHLD) = 200",
            "mmap(0x1000, 4096, PROT_READ, MAP_PRIVATE|MAP_FIXED, 4</project/private>, 0 <unfinished ...>",
            "--- SIGCHLD {si_signo=SIGCHLD} ---",
            "<... mmap resumed>) = 0x1000",
            "+++ exited with 0 +++",
        ],
    )
    _write_trace(
        traces,
        200,
        ["mprotect(0x1000, 4096, PROT_READ|PROT_WRITE) = 0", "+++ exited with 0 +++"],
        start=4,
    )
    with pytest.raises(AuthorityError, match="ambiguous cross-process mapping"):
        parse_trace_directory(traces, POLICY, Path("/project"))


# PR #1259 / discussion_r3785351127: one PID cannot syscall before its resume.
def test_syscall_interposed_before_pending_resume_fails_closed(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            "mmap(NULL, 4096, PROT_READ, MAP_SHARED, 3</project/db>, 0) = 0x1000",
            "mprotect(0x1000, 4096, PROT_READ|PROT_WRITE <unfinished ...>",
            "mmap(0x1000, 4096, PROT_READ, MAP_PRIVATE|MAP_FIXED, 4</project/private>, 0) = 0x1000",
            "<... mprotect resumed>) = 0",
            "+++ exited with 0 +++",
        ],
    )
    with pytest.raises(AuthorityError, match="syscall before the pending resume"):
        _parse(trace)


def test_rename_of_cwd_directory_rebases_later_targets(tmp_path: Path) -> None:
    # Codex P2 (#1259): chdir("/project/a") then rename("/project/a",
    # "/project/b") then unlink("x") — the kernel resolves the relative
    # mutation against /project/b, and the modeled cwd must follow.
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            'chdir("/project/a") = 0',
            'rename("/project/a", "/project/b") = 0',
            'unlink("x") = 0',
            "+++ exited with 0 +++",
        ],
    )
    targets = [event["target"] for event in _parse(trace)]
    assert "/project/b/x" in targets
    assert "/project/a/x" not in targets


def test_rename_of_ancestor_rebases_descendant_cwd(tmp_path: Path) -> None:
    # Codex P2 (#1259): cwd /project/a/sub, rename of the ancestor
    # /project/a -> /project/b rebases the cwd to /project/b/sub.
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            'chdir("/project/a/sub") = 0',
            'rename("/project/a", "/project/b") = 0',
            'unlink("x") = 0',
            "+++ exited with 0 +++",
        ],
    )
    targets = [event["target"] for event in _parse(trace)]
    assert "/project/b/sub/x" in targets


def test_failed_rename_keeps_cwd_provenance(tmp_path: Path) -> None:
    # Codex P2 (#1259): a failed rename must not rebase the modeled cwd.
    trace = tmp_path / "trace"
    _write_trace(
        trace,
        100,
        [
            'chdir("/project/a") = 0',
            'rename("/project/a", "/project/b") = -1 ENOENT (No such file or directory)',
            'unlink("x") = 0',
            "+++ exited with 0 +++",
        ],
    )
    targets = [event["target"] for event in _parse(trace)]
    assert "/project/a/x" in targets
