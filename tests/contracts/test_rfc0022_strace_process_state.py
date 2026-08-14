"""Process and mapping provenance contracts for RFC-0022 strace."""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from rfc0022_strace_authority import load_policy  # noqa: E402
from rfc0022_strace_model import AuthorityError  # noqa: E402
from rfc0022_strace_parser import parse_trace_directory  # noqa: E402

POLICY, _ = load_policy(ROOT / "config/rfc0022-linux-strace-policy.json")


def _write_trace(
    directory: Path, pid: int, bodies: list[str], *, start: int = 1
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"trace.{pid}"
    path.write_text(
        "".join(
            f"1700000000.{index:06d} {body}\n"
            for index, body in enumerate(bodies, start=start)
        ),
        encoding="utf-8",
    )
    return path


def _parse(directory: Path) -> list[dict[str, object]]:
    violations, _, _ = parse_trace_directory(directory, POLICY, Path("/project"))
    return [asdict(item) for item in violations]


def _event(
    *,
    line: int,
    syscall: str,
    operation: str,
    target: str,
    result: str,
    pid: int = 100,
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
        "flags": None,
    }


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
        AuthorityError, match="root trace lacks the expected successful target exec"
    ):
        parse_trace_directory(
            trace,
            POLICY,
            Path("/project"),
            expected_executable="/bin/expected",
        )


def test_safe_fd_metadata_commands_are_explicit_and_non_mutating(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "safe-fd-commands"
    _write_trace(
        trace,
        100,
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
    assert _parse(trace) == []


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
