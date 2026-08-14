"""Process and mapping provenance contracts for RFC-0022 strace."""

from __future__ import annotations

import hashlib
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import rfc0022_strace_privilege as privilege  # noqa: E402
from rfc0022_strace_authority import load_policy  # noqa: E402
from rfc0022_strace_model import AuthorityError  # noqa: E402
from rfc0022_strace_parser import parse_trace_directory  # noqa: E402
from rfc0022_strace_runtime import (  # noqa: E402
    raw_trace_metadata,
    seal_trace_directory,
)

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
    flags: str | None = None,
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


def test_privilege_separation_identity_and_launcher_are_digest_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Record:
        pw_uid = 1234
        pw_gid = 1235

    directories = tuple(tmp_path / name for name in ("home", "cache"))
    for directory in directories:
        directory.mkdir()
    chowns: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(privilege.os, "geteuid", lambda: 0)
    monkeypatch.setattr(privilege.os, "getgrouplist", lambda _user, gid: [gid])
    monkeypatch.setattr(
        privilege.os, "chown", lambda path, uid, gid: chowns.append((path, uid, gid))
    )

    class FakePwd:
        @staticmethod
        def getpwnam(_user: str) -> Record:
            return Record()

    monkeypatch.setattr(privilege, "pwd", FakePwd)
    launcher = ROOT / "scripts/rfc0022_strace_target_launcher.py"
    identity = privilege.prepare_target_identity(
        "rfc0022-target", directories, launcher
    )
    assert identity == {
        "gid": 1235,
        "groups": [1235],
        "launcher": {
            "path": str(launcher.resolve()),
            "sha256": privilege.TARGET_LAUNCHER_SHA256,
        },
        "no_new_privs": True,
        "uid": 1234,
        "user": "rfc0022-target",
    }
    assert chowns == [(directory, 1234, 1235) for directory in directories]
    assert [directory.stat().st_mode & 0o777 for directory in directories] == [
        0o700,
        0o700,
    ]


def test_privilege_separation_rejects_non_root_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(privilege.os, "geteuid", lambda: 501)
    with pytest.raises(AuthorityError, match="requires root privilege separation"):
        privilege.prepare_target_identity(
            "rfc0022-target",
            (tmp_path,),
            ROOT / "scripts/rfc0022_strace_target_launcher.py",
        )


def test_target_launcher_source_locks_no_new_privileges() -> None:
    source = (ROOT / "scripts/rfc0022_strace_target_launcher.py").read_text(
        encoding="utf-8"
    )
    required = {
        "PR_SET_NO_NEW_PRIVS = 38",
        'getattr(os, "getresuid", None)',
        'getattr(os, "getresgid", None)',
        "os.getgroups()",
        "os.execv(",
    }
    assert {item for item in required if item in source} == required


def test_raw_trace_inventory_and_sealing_are_exact(tmp_path: Path) -> None:
    trace = tmp_path / "raw-inventory"
    path = _write_trace(trace, 100, ["+++ exited with 0 +++"])
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
