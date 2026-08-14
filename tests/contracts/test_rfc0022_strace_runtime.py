"""Race-free process cleanup contracts for RFC-0022 Linux authority."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import rfc0022_strace_runtime as runtime  # noqa: E402
from rfc0022_strace_model import AuthorityError  # noqa: E402


def test_cleanup_workflow_dependencies_are_complete() -> None:
    workflow = (
        ROOT / ".github/workflows/rfc0022-linux-write-authority.yml"
    ).read_text()
    assert workflow.count("tests/contracts/test_rfc0022_strace_runtime.py") == 3


# PR #1259 / discussion_r3786037047: cleanup must bind one process lifetime.
def test_pidfd_cleanup_support_is_probed_without_numeric_signaling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[int, int, None, int]] = []
    closed: list[int] = []
    monkeypatch.setattr(runtime.os, "getpid", lambda: 50)
    monkeypatch.setattr(runtime.os, "pidfd_open", lambda pid, flags: 77, raising=False)
    monkeypatch.setattr(
        runtime.signal,
        "pidfd_send_signal",
        lambda fd, sig, info, flags: sent.append((fd, sig, info, flags)),
        raising=False,
    )
    monkeypatch.setattr(runtime.os, "close", closed.append)
    runtime.require_pidfd_support()
    assert sent == [(77, 0, None, 0)]
    assert closed == [77]


def test_cleanup_capture_binds_token_and_thread_group_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = tmp_path / "proc"
    trace = tmp_path / "trace"
    trace.mkdir()
    for pid, tgid, environment, tracer in (
        (101, 101, b"RFC0022_AUTHORITY_TOKEN=secret\0", 0),
        (102, 102, b"PATH=/bin\0", 42),
        (202, 102, b"PATH=/bin\0", 42),
    ):
        entry = proc / str(pid)
        entry.mkdir(parents=True)
        (entry / "environ").write_bytes(environment)
        (entry / "status").write_bytes(
            f"Tgid:\t{tgid}\nTracerPid:\t{tracer}\n".encode()
        )
    (trace / "trace.202").write_text("", encoding="ascii")
    monkeypatch.setattr(runtime.os, "getpid", lambda: 999)
    monkeypatch.setattr(
        runtime, "_proc_entries", lambda root: [root / "101", root / "102"]
    )
    monkeypatch.setattr(
        runtime.os, "pidfd_open", lambda pid, flags: pid + 1000, raising=False
    )
    monkeypatch.setattr(runtime, "_identity_alive", lambda identity: True)
    closed: list[int] = []
    monkeypatch.setattr(runtime.os, "close", closed.append)
    identities = runtime.capture_cleanup_identities(
        "secret", trace, tracer_pid=42, proc_root=proc
    )
    assert [(item.pid, item.pidfd) for item in identities] == [(101, 1101), (102, 1102)]
    assert closed == [1102]
    runtime.close_process_identities(identities)
    assert closed == [1102, 1101, 1102]


def test_historical_trace_pid_without_live_membership_is_not_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = tmp_path / "proc"
    entry = proc / "123"
    entry.mkdir(parents=True)
    (entry / "environ").write_bytes(b"PATH=/bin\0")
    trace = tmp_path / "trace"
    trace.mkdir()
    (trace / "trace.123").write_text("historical", encoding="ascii")
    monkeypatch.setattr(runtime.os, "getpid", lambda: 999)
    monkeypatch.setattr(runtime.os, "pidfd_open", lambda pid, flags: 55, raising=False)
    monkeypatch.setattr(runtime, "_identity_alive", lambda identity: True)
    closed: list[int] = []
    monkeypatch.setattr(runtime.os, "close", closed.append)
    assert runtime.capture_cleanup_identities("secret", trace, proc_root=proc) == []
    assert closed == [55]


def test_exited_pidfd_is_not_retained_after_token_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = tmp_path / "proc"
    entry = proc / "123"
    entry.mkdir(parents=True)
    (entry / "environ").write_bytes(b"RFC0022_AUTHORITY_TOKEN=secret\0")
    monkeypatch.setattr(runtime.os, "getpid", lambda: 999)
    monkeypatch.setattr(runtime.os, "pidfd_open", lambda pid, flags: 55, raising=False)
    monkeypatch.setattr(runtime, "_identity_alive", lambda identity: False)
    closed: list[int] = []
    monkeypatch.setattr(runtime.os, "close", closed.append)
    assert runtime.capture_cleanup_identities("secret", proc_root=proc) == []
    assert closed == [55]


def test_pidfd_signal_handles_exit_without_falling_back_to_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[int, int, None, int]] = []

    def send(fd: int, sig: int, info: None, flags: int) -> None:
        sent.append((fd, sig, info, flags))
        if fd == 11:
            raise ProcessLookupError

    monkeypatch.setattr(runtime.signal, "pidfd_send_signal", send, raising=False)
    monkeypatch.setattr(runtime, "_identity_alive", lambda identity: False)
    closed: list[int] = []
    monkeypatch.setattr(runtime.os, "close", closed.append)
    cleaned, remaining = runtime._kill_identities(
        [runtime.ProcessIdentity(101, 11), runtime.ProcessIdentity(102, 12)]
    )
    assert (cleaned, remaining) == ([101, 102], [])
    assert sent == [
        (11, runtime.LINUX_SIGKILL, None, 0),
        (12, runtime.LINUX_SIGKILL, None, 0),
    ]
    assert closed == [11, 12]
    assert "os.kill(" not in (ROOT / "scripts/rfc0022_strace_runtime.py").read_text()


def test_pidfd_signal_error_fails_closed_and_closes_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny(_fd: int, _sig: int, _info: None, _flags: int) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(runtime.signal, "pidfd_send_signal", deny, raising=False)
    monkeypatch.setattr(runtime, "_identity_alive", lambda identity: False)
    closed: list[int] = []
    monkeypatch.setattr(runtime.os, "close", closed.append)
    with pytest.raises(AuthorityError, match="pidfd signal failed for 101"):
        runtime._kill_identities([runtime.ProcessIdentity(101, 11)])
    assert closed == [11]


def test_missing_pidfd_api_fails_closed_before_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(runtime.os, "pidfd_open", raising=False)
    monkeypatch.delattr(runtime.signal, "pidfd_send_signal", raising=False)
    with pytest.raises(AuthorityError, match="pidfd cleanup support is unavailable"):
        runtime.require_pidfd_support()


def test_cleanup_discovery_failure_closes_prior_stable_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = tmp_path / "proc"
    for pid in (101, 102):
        entry = proc / str(pid)
        entry.mkdir(parents=True)
        (entry / "environ").write_bytes(b"RFC0022_AUTHORITY_TOKEN=secret\0")
    monkeypatch.setattr(runtime.os, "getpid", lambda: 999)
    monkeypatch.setattr(
        runtime, "_proc_entries", lambda root: [root / "101", root / "102"]
    )

    def open_pidfd(pid: int, _flags: int) -> int:
        if pid == 102:
            raise OSError("exhausted")
        return 11

    monkeypatch.setattr(runtime.os, "pidfd_open", open_pidfd, raising=False)
    monkeypatch.setattr(runtime, "_identity_alive", lambda identity: True)
    closed: list[int] = []
    monkeypatch.setattr(runtime.os, "close", closed.append)
    with pytest.raises(AuthorityError, match="unable to open cleanup pidfd for 102"):
        runtime.capture_cleanup_identities("secret", proc_root=proc)
    assert closed == [11]


def test_precaptured_identity_is_signaled_before_a_rescan_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[int] = []
    monkeypatch.setattr(
        runtime.signal,
        "pidfd_send_signal",
        lambda fd, sig, info, flags: sent.append(fd),
        raising=False,
    )
    monkeypatch.setattr(runtime, "_identity_alive", lambda identity: False)
    monkeypatch.setattr(
        runtime,
        "capture_cleanup_identities",
        lambda token: (_ for _ in ()).throw(AuthorityError("scan failed")),
    )
    closed: list[int] = []
    monkeypatch.setattr(runtime.os, "close", closed.append)
    with pytest.raises(AuthorityError, match="scan failed"):
        runtime.cleanup_candidates("secret", [runtime.ProcessIdentity(101, 11)])
    assert sent == [11]
    assert closed == [11]


def test_distinct_pidfds_for_reused_pid_are_each_signaled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[int] = []
    monkeypatch.setattr(
        runtime.signal,
        "pidfd_send_signal",
        lambda fd, sig, info, flags: sent.append(fd),
        raising=False,
    )
    monkeypatch.setattr(runtime, "_identity_alive", lambda identity: False)
    closed: list[int] = []
    monkeypatch.setattr(runtime.os, "close", closed.append)
    cleaned, remaining = runtime._kill_identities(
        [runtime.ProcessIdentity(101, 11), runtime.ProcessIdentity(101, 12)]
    )
    assert (cleaned, remaining) == ([101], [])
    assert sent == [11, 12]
    assert closed == [11, 12]


def test_cleanup_rescans_until_no_token_parent_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scans = iter([[runtime.ProcessIdentity(102, 12)], []])
    monkeypatch.setattr(
        runtime, "capture_cleanup_identities", lambda token: next(scans)
    )
    sent: list[int] = []
    monkeypatch.setattr(
        runtime.signal,
        "pidfd_send_signal",
        lambda fd, sig, info, flags: sent.append(fd),
        raising=False,
    )
    monkeypatch.setattr(runtime, "_identity_alive", lambda identity: False)
    monkeypatch.setattr(runtime.os, "close", lambda fd: None)
    assert runtime.cleanup_candidates("secret", [runtime.ProcessIdentity(101, 11)]) == (
        [101, 102],
        [],
    )
    assert sent == [11, 12]


def test_final_rescan_replaces_historical_remaining_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kills = iter([([101], [101]), ([101], [])])
    captures = iter([[runtime.ProcessIdentity(101, 12)], []])
    monkeypatch.setattr(runtime, "_kill_identities", lambda items, timeout: next(kills))
    monkeypatch.setattr(
        runtime, "capture_cleanup_identities", lambda token: next(captures)
    )
    assert runtime.cleanup_candidates(
        "secret", [runtime.ProcessIdentity(101, 11)], timeout=0.0
    ) == ([101], [])


def test_tracer_pid_is_excluded_from_token_survivors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = tmp_path / "proc"
    entry = proc / "42"
    entry.mkdir(parents=True)
    (entry / "environ").write_bytes(b"RFC0022_AUTHORITY_TOKEN=secret\0")
    monkeypatch.setattr(runtime.os, "getpid", lambda: 999)
    monkeypatch.setattr(
        runtime.os,
        "pidfd_open",
        lambda pid, flags: (_ for _ in ()).throw(AssertionError("tracer opened")),
        raising=False,
    )
    assert (
        runtime.capture_cleanup_identities(
            "secret", proc_root=proc, exclude_pids=frozenset({42})
        )
        == []
    )


def test_ambiguous_proc_status_membership_fails_closed(tmp_path: Path) -> None:
    entry = tmp_path / "123"
    entry.mkdir()
    (entry / "status").write_bytes(
        b"Name:\tx\nTgid:\t123\nTgid:\t999\nTracerPid:\t42\n"
    )
    with pytest.raises(AuthorityError, match="ambiguous cleanup status for 123"):
        runtime._status_membership(tmp_path, 123)


def test_post_final_observation_reports_third_generation_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kills = iter([([101], []), ([102], [])])
    captures = iter(
        [[runtime.ProcessIdentity(102, 12)], [runtime.ProcessIdentity(103, 13)]]
    )
    monkeypatch.setattr(runtime, "_kill_identities", lambda items, timeout: next(kills))
    monkeypatch.setattr(
        runtime, "capture_cleanup_identities", lambda token: next(captures)
    )
    sent: list[int] = []
    monkeypatch.setattr(
        runtime.signal,
        "pidfd_send_signal",
        lambda fd, sig, info, flags: sent.append(fd),
        raising=False,
    )
    monkeypatch.setattr(runtime.os, "close", lambda fd: None)
    assert runtime.cleanup_candidates(
        "secret", [runtime.ProcessIdentity(101, 11)], timeout=0.0
    ) == ([101, 102, 103], [103])
    assert sent == [13]


def test_trace_discovery_reopens_dead_same_pid_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = tmp_path / "proc"
    entry = proc / "101"
    entry.mkdir(parents=True)
    (entry / "environ").write_bytes(b"RFC0022_AUTHORITY_TOKEN=secret\0")
    (entry / "status").write_bytes(b"Tgid:\t101\nTracerPid:\t42\n")
    trace = tmp_path / "trace"
    trace.mkdir()
    (trace / "trace.101").write_text("", encoding="ascii")
    fds = iter([11, 12])
    monkeypatch.setattr(runtime.os, "getpid", lambda: 999)
    monkeypatch.setattr(
        runtime.os, "pidfd_open", lambda pid, flags: next(fds), raising=False
    )
    alive = iter([True, False, True])
    monkeypatch.setattr(runtime, "_identity_alive", lambda identity: next(alive))
    closed: list[int] = []
    monkeypatch.setattr(runtime.os, "close", closed.append)
    identities = runtime.capture_cleanup_identities(
        "secret", trace, tracer_pid=42, proc_root=proc
    )
    assert identities == [runtime.ProcessIdentity(101, 12)]
    assert closed == [11]
    runtime.close_process_identities(identities)
    assert closed == [11, 12]


def test_authority_binds_tracees_before_killing_unreaped_tracer() -> None:
    source = (ROOT / "scripts/rfc0022_strace_authority.py").read_text()
    capture = "cleanup_identities = capture_cleanup_identities("
    kill = "os.killpg(process.pid, signal.SIGKILL)"
    first_capture = source.index(capture)
    first_kill = source.index(kill)
    second_capture = source.index(capture, first_capture + 1)
    second_kill = source.index(kill, first_kill + 1)
    assert first_capture < first_kill < second_capture < second_kill
    assert source.count("exclude_pids=frozenset({process.pid})") == 2
    assert "signal_cleanup_identities" not in source
    control = (ROOT / "scripts/rfc0022_strace_positive_control.py").read_text()
    assert 'environment.pop("RFC0022_AUTHORITY_TOKEN", None)' in control
