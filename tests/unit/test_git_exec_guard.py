from __future__ import annotations

import io
import os
import stat
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
import tree_sitter_analyzer.frozen_git_index as frozen_index
import tree_sitter_analyzer.git_subprocess as bounded
import tree_sitter_analyzer.private_temp_materialization as materialization
import tree_sitter_analyzer.secure_temp as secure_temp
import tree_sitter_analyzer.temp_cleanup as temp_cleanup
from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST
from tree_sitter_analyzer.source_oracle import SourceOracleError


class _WindowsProcess:
    def __init__(self) -> None:
        self.pid = 41
        self.kills = 0

    def kill(self) -> None:
        self.kills += 1


class _Proc:
    def __init__(self, out=b"", err=b"", returncode=0, wait_error=None):
        self.stdout = io.BytesIO(out)
        self.stderr = io.BytesIO(err)
        self.returncode = returncode
        self.wait_error = wait_error
        self.killed = False

    def wait(self, timeout=None):
        if self.wait_error and timeout is not None:
            raise self.wait_error
        return self.returncode

    def kill(self):
        self.killed = True


@POSIX_SNAPSHOT_TEST
def test_file_size_limit_uses_single_threaded_exec_guard() -> None:
    # PR #1252 review thread 4867: threaded parents must not use preexec_fn.
    proc = _Proc()
    proc.stdin = io.BytesIO()
    captured: dict[str, object] = {}

    def popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return proc

    bounded.run_git_bounded(
        ".",
        ["hash-object", "-w", "--stdin"],
        deadline=time.monotonic() + 1,
        limit=4096,
        input_=b"payload",
        popen=popen,
        file_size_limit=123,
    )

    command = captured["command"]
    assert command == [
        bounded.sys.executable,
        str(Path(bounded.__file__).with_name("git_exec_guard.py").resolve()),
        "--fsize",
        "123",
        "--",
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        command[9],
        "hash-object",
        "-w",
        "--stdin",
    ]
    assert str(command[9]).startswith("diff.orderFile=")
    assert "preexec_fn" not in captured
    assert captured["start_new_session"] is True


def test_file_size_limit_omits_preexec_on_windows(monkeypatch) -> None:
    # PR #1252 review thread 5947: Windows remains fail-closed upstream.
    proc = _Proc()
    captured: dict[str, object] = {}
    monkeypatch.setattr(bounded, "_IS_WINDOWS", True)

    def popen(*args, **kwargs):
        captured.update(kwargs)
        return proc

    bounded.run_git_bounded(
        ".", [], deadline=time.monotonic() + 1, limit=1, popen=popen, file_size_limit=1
    )

    assert "preexec_fn" not in captured


def test_git_exec_guard_rejects_invalid_limit() -> None:
    # PR #1252 review thread 4867: malformed guards fail before exec.
    from tree_sitter_analyzer import git_exec_guard

    assert git_exec_guard.main(["--fsize", "bad", "--", "git", "status"]) == 2


@pytest.mark.parametrize(
    ("soft", "hard", "requested", "expected"),
    [(75, 100, 50, 50), (25, 100, 50, 25), (25, -1, 50, 25), (-1, -1, 50, 50)],
)
def test_exec_guard_sets_bounded_rlimit(
    monkeypatch, soft: int, hard: int, requested: int, expected: int
) -> None:
    # PR #1252 review threads 4867/3108: never raise an inherited finite soft limit.
    from tree_sitter_analyzer import git_exec_guard

    calls: list[tuple[int, tuple[int, int]]] = []
    resource = types.SimpleNamespace(
        RLIMIT_FSIZE=1,
        RLIM_INFINITY=-1,
        getrlimit=lambda kind: (soft, hard),
        setrlimit=lambda kind, value: calls.append((kind, value)),
    )
    monkeypatch.setitem(sys.modules, "resource", resource)
    monkeypatch.setattr(
        git_exec_guard.os, "execvp", lambda *args: (_ for _ in ()).throw(OSError())
    )

    result = git_exec_guard.main(["--fsize", str(requested), "--", "git", "status"])

    assert result == 126
    assert calls == [(1, (expected, hard))]


def test_negative_file_size_limit_is_rejected() -> None:
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        bounded.run_git_bounded(".", [], deadline=1e20, limit=1, file_size_limit=-1)


@pytest.mark.parametrize("failure_point", ["mode", "lstat"])
def test_empty_order_file_cleans_hostile_candidate_failures(
    tmp_path: Path, monkeypatch, failure_point: str
) -> None:
    # PR #1252 Windows zero gate: failed validation must not leak descriptors.
    project = tmp_path / "project"
    project.mkdir()
    candidates = tmp_path / "candidates"
    candidates.mkdir()
    created: list[tuple[int, str]] = []
    real_mkstemp = __import__("tempfile").mkstemp

    def recording_mkstemp(*, prefix: str, dir: str):
        descriptor, path = real_mkstemp(prefix=prefix, dir=candidates)
        created.append((descriptor, path))
        return descriptor, path

    monkeypatch.setattr(bounded.tempfile, "gettempdir", lambda: str(candidates))
    monkeypatch.setattr(bounded.tempfile, "mkstemp", recording_mkstemp)
    if failure_point == "mode":
        monkeypatch.setattr(
            secure_temp,
            "set_private_mode",
            lambda *args: (_ for _ in ()).throw(RuntimeError("hostile chmod")),
        )
    else:
        monkeypatch.setattr(
            secure_temp,
            "_LSTAT",
            lambda path: (_ for _ in ()).throw(RuntimeError("hostile lstat")),
        )

    with pytest.raises(
        snapshots.SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_TEMP$"
    ):
        bounded._empty_order_file(str(project))

    assert len(created) == len({path for _, path in created})
    assert [Path(path).exists() for _, path in created] == [False] * len(created)
    for descriptor, _path in created:
        with pytest.raises(OSError):
            os.fstat(descriptor)


@pytest.mark.parametrize("failure_point", ["mode", "lstat"])
def test_private_index_cleans_hostile_candidate_failure(
    tmp_path: Path, monkeypatch, failure_point: str
) -> None:
    # PR #1252 Windows zero gate: private-index setup owns failed partials.
    project = tmp_path / "project"
    project.mkdir()
    created: list[tuple[int, str]] = []
    real_mkstemp = __import__("tempfile").mkstemp

    def recording_mkstemp(*, prefix: str, dir: str):
        descriptor, path = real_mkstemp(prefix=prefix, dir=tmp_path)
        created.append((descriptor, path))
        return descriptor, path

    if failure_point == "mode":
        monkeypatch.setattr(
            secure_temp,
            "set_private_mode",
            lambda *args: (_ for _ in ()).throw(RuntimeError("hostile chmod")),
        )
    else:
        monkeypatch.setattr(
            secure_temp,
            "_LSTAT",
            lambda path: (_ for _ in ()).throw(RuntimeError("hostile lstat")),
        )

    with pytest.raises(
        snapshots.SourceOracleError, match="^DIFF_SNAPSHOT_CAPTURE_ERROR$"
    ):
        with frozen_index.private_index_file(
            str(project), b"index", mkstemp=recording_mkstemp
        ):
            pass

    assert [Path(path).exists() for _, path in created] == [False]
    with pytest.raises(OSError):
        os.fstat(created[0][0])


def test_private_mode_uses_path_fallback_without_fchmod(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "private"
    target.write_bytes(b"")
    target.chmod(0o666)
    descriptor = os.open(target, os.O_RDWR)
    monkeypatch.delattr(secure_temp.os, "fchmod", raising=False)
    try:
        secure_temp.set_private_mode(descriptor, str(target))
    finally:
        os.close(descriptor)

    info = target.stat()
    assert stat.S_ISREG(info.st_mode)
    if os.name == "nt":
        target.unlink()
        assert (target.parent.resolve(), target.exists()) == (tmp_path.resolve(), False)
    else:
        assert stat.S_IMODE(info.st_mode) == 0o600


def test_order_file_close_failure_unlinks_partial(tmp_path: Path, monkeypatch) -> None:
    # PR #1252 Windows zero gate: caller-side close failure is cleanup-safe.
    target = tmp_path / "order"
    target.touch()
    monkeypatch.setattr(bounded, "_empty_order_file", lambda root: (123, str(target)))
    monkeypatch.setattr(
        bounded.os,
        "close",
        lambda descriptor: (_ for _ in ()).throw(RuntimeError("hostile close")),
    )

    with pytest.raises(
        snapshots.SourceOracleError, match="^DIFF_SNAPSHOT_CAPTURE_ERROR$"
    ):
        bounded.run_git_bounded(".", [], deadline=1e20, limit=1)

    assert target.exists() is False


@pytest.mark.parametrize(
    "case", ["cross-volume", "inside", "non-absolute", "inaccessible"]
)
def test_empty_order_candidate_guards_are_platform_independent(
    tmp_path: Path, monkeypatch, case: str
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    project_real = str(project.resolve())
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    monkeypatch.setattr(bounded, "_order_file_candidates", lambda: [str(candidate)])
    if case == "cross-volume":
        monkeypatch.setattr(
            bounded.os.path,
            "commonpath",
            lambda paths: (_ for _ in ()).throw(ValueError("volume")),
        )
        descriptor, path = bounded._empty_order_file(str(project))
        os.close(descriptor)
        os.unlink(path)
        assert Path(path).exists() is False
        return
    if case == "inside":
        monkeypatch.setattr(bounded.os.path, "realpath", lambda path: project_real)
    else:
        monkeypatch.setattr(
            bounded.os.path,
            "commonpath",
            lambda paths: (_ for _ in ()).throw(ValueError("volume")),
        )
        if case == "non-absolute":
            monkeypatch.setattr(bounded.os.path, "isabs", lambda path: False)
        else:
            monkeypatch.setattr(bounded.os, "access", lambda path, mode: False)

    with pytest.raises(
        snapshots.SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_TEMP$"
    ):
        bounded._empty_order_file(str(project))


def test_order_file_cleanup_retries_windows_held_delete(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3114: close first, then retry a transient held delete.
    target = tmp_path / "order"
    target.touch()
    descriptor = os.open(target, os.O_RDONLY)
    attempts = 0
    real_unlink = os.unlink

    def held_then_release(path: str) -> None:
        nonlocal attempts
        attempts += 1
        with pytest.raises(OSError):
            os.fstat(descriptor)
        if attempts < 3:
            raise PermissionError("held by Windows scanner")
        real_unlink(path)

    monkeypatch.setattr(bounded, "_IS_WINDOWS", True)
    monkeypatch.setattr(
        bounded, "_empty_order_file", lambda root: (descriptor, str(target))
    )
    monkeypatch.setattr(
        bounded, "_run_git_bounded_with_order_file", lambda *a, **k: b"ok"
    )
    monkeypatch.setattr(temp_cleanup, "_UNLINK", held_then_release)
    monkeypatch.setattr(temp_cleanup, "_SLEEP", lambda delay: None)

    assert bounded.run_git_bounded(".", [], deadline=1e20, limit=1) == b"ok"
    assert attempts == 3
    assert target.exists() is False


def test_order_file_cleanup_persistent_failure_is_stable(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "order"
    target.touch()
    descriptor = os.open(target, os.O_RDONLY)
    monkeypatch.setattr(
        bounded, "_empty_order_file", lambda root: (descriptor, str(target))
    )
    monkeypatch.setattr(
        bounded, "_run_git_bounded_with_order_file", lambda *a, **k: b"ok"
    )
    monkeypatch.setattr(
        temp_cleanup,
        "_UNLINK",
        lambda path: (_ for _ in ()).throw(PermissionError("held")),
    )
    monkeypatch.setattr(temp_cleanup, "_SLEEP", lambda delay: None)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CLEANUP_FAILED$"):
        bounded.run_git_bounded(".", [], deadline=1e20, limit=1)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--fsize", "-1", "--", "git", "status"],
        ["--fsize", "1", "--", "python", "script.py"],
    ],
)
def test_git_exec_guard_rejects_unsafe_commands(argv: list[str]) -> None:
    from tree_sitter_analyzer import git_exec_guard

    assert git_exec_guard.main(argv) == 2


def test_private_temp_rejects_nonempty_validation(tmp_path: Path) -> None:
    real_mkstemp = __import__("tempfile").mkstemp

    def nonempty_mkstemp(*, prefix: str, dir: str):
        descriptor, path = real_mkstemp(prefix=prefix, dir=dir)
        os.write(descriptor, b"x")
        return descriptor, path

    with pytest.raises(OSError, match="invalid private temporary file"):
        secure_temp.create_private_temp(
            prefix="invalid-", directory=str(tmp_path), mkstemp=nonempty_mkstemp
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("unlink_failure", [FileNotFoundError, PermissionError])
def test_private_temp_cleanup_exceptions_do_not_mask_validation(
    tmp_path: Path, monkeypatch, unlink_failure: type[OSError]
) -> None:
    target = tmp_path / "partial"
    unlinks: list[str] = []
    monkeypatch.setattr(secure_temp, "set_private_mode", lambda *args: None)
    monkeypatch.setattr(
        secure_temp,
        "_LSTAT",
        lambda path: (_ for _ in ()).throw(RuntimeError("validation")),
    )
    monkeypatch.setattr(
        secure_temp.os,
        "close",
        lambda descriptor: (_ for _ in ()).throw(OSError("close")),
    )

    def fail_unlink(path: str) -> None:
        unlinks.append(path)
        raise unlink_failure("unlink")

    with pytest.raises(RuntimeError, match="validation"):
        secure_temp.create_private_temp(
            prefix="partial-",
            directory=str(tmp_path),
            mkstemp=lambda **kwargs: (999, str(target)),
            unlink=fail_unlink,
        )

    assert unlinks == [str(target)]


def test_windows_order_file_candidates_exclude_posix_fallbacks(monkeypatch) -> None:
    portable = os.path.abspath("portable-temp")
    monkeypatch.setattr(bounded, "_IS_WINDOWS", True)
    monkeypatch.setattr(bounded.tempfile, "gettempdir", lambda: portable)
    assert bounded._order_file_candidates() == [portable]


def test_windows_process_group_and_taskkill_are_explicit(monkeypatch) -> None:
    calls = []
    process = _WindowsProcess()
    monkeypatch.setattr(bounded, "_IS_WINDOWS", True)
    monkeypatch.setattr(bounded, "_TASKKILL", lambda *a, **k: calls.append((a, k)))
    options = bounded._group_options()
    bounded._kill_group(process)

    assert options == {
        "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    }
    assert calls[0][0][0] == ["taskkill", "/PID", "41", "/T", "/F"]
    assert process.kills == 0


def test_failed_windows_taskkill_falls_back_to_process_kill(monkeypatch) -> None:
    process = _WindowsProcess()
    monkeypatch.setattr(bounded, "_IS_WINDOWS", True)
    monkeypatch.setattr(
        bounded,
        "_TASKKILL",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("taskkill", 5)),
    )
    bounded._kill_group(process)

    assert process.kills == 1


def test_nonzero_windows_taskkill_falls_back_to_process_kill(monkeypatch) -> None:
    process = _WindowsProcess()
    completed = subprocess.CompletedProcess(["taskkill"], 1)
    monkeypatch.setattr(bounded, "_IS_WINDOWS", True)
    monkeypatch.setattr(bounded, "_TASKKILL", lambda *a, **k: completed)

    bounded._kill_group(process)
    assert process.kills == 1


def test_private_write_failure_cleans_and_rolls_back(
    tmp_path: Path, monkeypatch
) -> None:
    from unittest.mock import mock_open

    target = tmp_path / "partial"
    rolled = []
    opened = mock_open()
    opened.return_value.write.return_value = 0
    monkeypatch.setattr("builtins.open", opened)
    monkeypatch.setattr(materialization, "set_private_mode", lambda *a: None)
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPTURE_ERROR$"):
        materialization.write_private(
            str(target), b"x", lambda *a: None, lambda *a: rolled.append(a)
        )
    assert rolled == [(1, 1)]
    assert target.exists() is False
