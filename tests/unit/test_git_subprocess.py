from __future__ import annotations

import io
import os
import subprocess
import time
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_epoch as epoch_module
import tree_sitter_analyzer.diff_snapshot_registry as snapshots
import tree_sitter_analyzer.frozen_git_index as frozen_index
import tree_sitter_analyzer.git_subprocess as bounded
import tree_sitter_analyzer.source_oracle_git as oracle
from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST, make_repo


def _error(call, code: str) -> None:
    with pytest.raises(oracle.SourceOracleError, match=f"^{code}$"):
        call()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


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


def test_git_output_translates_spawn_error(monkeypatch) -> None:
    monkeypatch.setattr(
        oracle.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_git_output_rejects_negative_limit() -> None:
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=-1),
        "DIFF_SNAPSHOT_CAPACITY",
    )


def test_git_output_kills_timed_out_process(monkeypatch) -> None:
    proc = _Proc(wait_error=subprocess.TimeoutExpired("git", 1))
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_TIMEOUT",
    )
    assert proc.killed is True


def test_git_output_rejects_nonzero_exit(monkeypatch) -> None:
    proc = _Proc(returncode=3)
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_git_output_rejects_oversize_stdout(monkeypatch) -> None:
    proc = _Proc(out=b"ab")
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_CAPACITY",
    )
    assert proc.killed is True


def test_git_output_translates_stream_read_error(monkeypatch) -> None:
    class Broken(io.BytesIO):
        def read(self, size=-1):
            raise OSError

    proc = _Proc()
    proc.stdout = Broken()
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_git_output_rejects_missing_stdout(monkeypatch) -> None:
    proc = _Proc()
    proc.stdout = None
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_git_output_preserves_capacity_error_when_kill_fails(monkeypatch) -> None:
    proc = _Proc(out=b"ab")
    proc.kill = lambda: (_ for _ in ()).throw(OSError())
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_CAPACITY",
    )


def test_git_output_rejects_drain_thread_past_deadline(monkeypatch) -> None:
    proc = _Proc()

    class Thread:
        def __init__(self, **kwargs):
            self.target = kwargs["target"]

        def start(self):
            pass

        def join(self, timeout=None):
            pass

        def is_alive(self):
            return True

    monkeypatch.setattr(oracle.threading, "Thread", Thread)
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_TIMEOUT",
    )
    assert proc.killed is True


def test_strip_one_record_terminator_preserves_path_newline() -> None:
    assert oracle._strip_one_record_terminator(b"repo\n\r\n") == b"repo\n"


@POSIX_SNAPSHOT_TEST
def test_git_output_timeout_kills_hostile_descendant(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3747224316.
    marker = tmp_path / "survived"
    fake_git = tmp_path / "git"
    fake_git.write_text(
        f"#!/bin/sh\n( trap '' TERM; sleep 0.3; echo survived > {marker!s} ) &\nwait\n"
    )
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])

    _error(
        lambda: oracle.git_output(
            str(tmp_path), [], deadline=time.monotonic() + 0.05, limit=4096
        ),
        "DIFF_SNAPSHOT_TIMEOUT",
    )
    time.sleep(0.4)

    assert marker.exists() is False


@POSIX_SNAPSHOT_TEST
def test_snapshot_disables_external_fsmonitor_hook(tmp_path: Path) -> None:
    # PR #1252 review thread 3747224316.
    root = _repo(tmp_path)
    marker = root / "fsmonitor-invoked"
    hook = root / "hostile-fsmonitor"
    hook.write_text(f"#!/bin/sh\necho invoked > {marker!s}\nsleep 30\n")
    hook.chmod(0o755)
    _git(root, "config", "core.fsmonitor", str(hook))
    (root / "old.py").write_text("value = 2\n")

    result = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert result["success"] is True
    assert marker.exists() is False


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_ignores_inherited_git_routing(
    tmp_path: Path, monkeypatch
) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong.git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "wrong-tree"))

    generation, _ = oracle.oracle_generation(str(tmp_path))

    assert generation[:3] == "sg_"


class _Input(io.BytesIO):
    def __init__(self, *, broken: bool = False) -> None:
        super().__init__()
        self.broken = broken

    def write(self, value: bytes) -> int:
        if self.broken:
            raise BrokenPipeError
        return super().write(value)


class _InputProcess:
    def __init__(self, *, broken_input: bool = False, timeout: bool = False) -> None:
        self.pid = 41
        self.stdin = _Input(broken=broken_input)
        self.stdout = io.BytesIO(b"result")
        self.stderr = io.BytesIO()
        self.returncode = 0
        self.timeout = timeout
        self.waits: list[float | None] = []
        self.kills = 0

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.timeout and len(self.waits) == 1:
            raise subprocess.TimeoutExpired("git", timeout)
        return 0

    def kill(self) -> None:
        self.kills += 1


def test_windows_process_group_and_taskkill_are_explicit(monkeypatch) -> None:
    calls = []
    process = _InputProcess()
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
    process = _InputProcess()
    monkeypatch.setattr(bounded, "_IS_WINDOWS", True)
    monkeypatch.setattr(
        bounded,
        "_TASKKILL",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("taskkill", 5)),
    )

    bounded._kill_group(process)

    assert process.kills == 1


def test_nonzero_windows_taskkill_falls_back_to_process_kill(monkeypatch) -> None:
    process = _InputProcess()
    completed = subprocess.CompletedProcess(["taskkill"], 1)
    monkeypatch.setattr(bounded, "_IS_WINDOWS", True)
    monkeypatch.setattr(bounded, "_TASKKILL", lambda *a, **k: completed)

    bounded._kill_group(process)

    assert process.kills == 1


def test_nonzero_exit_kills_group_and_reaps_with_exact_waits(monkeypatch) -> None:
    process = _InputProcess()
    process.returncode = 3
    killed: list[int] = []
    monkeypatch.setattr(bounded, "_remaining", lambda deadline: 0.25)
    monkeypatch.setattr(bounded, "_kill_group", lambda proc: killed.append(proc.pid))

    with pytest.raises(bounded.SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        bounded.run_git_bounded(
            ".",
            ["status"],
            deadline=1.0,
            limit=100,
            popen=lambda *a, **k: process,
        )

    assert killed == [41]
    assert process.waits == [0.25, bounded._REAP_TIMEOUT_SECONDS]


def test_reap_timeout_rekills_and_uses_only_bounded_waits(monkeypatch) -> None:
    process = _InputProcess()
    killed: list[int] = []

    def always_timeout(timeout=None):
        process.waits.append(timeout)
        raise subprocess.TimeoutExpired("git", timeout)

    process.wait = always_timeout  # type: ignore[method-assign]
    monkeypatch.setattr(bounded, "_remaining", lambda deadline: 0.25)
    monkeypatch.setattr(bounded, "_kill_group", lambda proc: killed.append(proc.pid))

    with pytest.raises(bounded.SourceOracleError, match="^DIFF_SNAPSHOT_TIMEOUT$"):
        bounded.run_git_bounded(
            ".",
            ["status"],
            deadline=1.0,
            limit=100,
            popen=lambda *a, **k: process,
        )

    assert killed == [41, 41]
    assert process.waits == [
        0.25,
        bounded._REAP_TIMEOUT_SECONDS,
        bounded._REAP_TIMEOUT_SECONDS,
    ]


@pytest.mark.parametrize("broken_input", [False, True])
def test_stdin_feed_is_closed_or_tolerates_broken_pipe(broken_input: bool) -> None:
    process = _InputProcess(broken_input=broken_input)

    output = bounded.run_git_bounded(
        ".",
        ["status"],
        deadline=time.monotonic() + 1,
        limit=100,
        input_=b"payload",
        popen=lambda *a, **k: process,
    )

    assert output == b"result"
    assert process.stdin.closed is (not broken_input)
    assert len(process.waits) == 1


def test_timeout_kills_and_reaps_process(monkeypatch) -> None:
    process = _InputProcess(timeout=True)
    killed = []
    monkeypatch.setattr(bounded, "_kill_group", lambda proc: killed.append(proc.pid))

    with pytest.raises(bounded.SourceOracleError, match="^DIFF_SNAPSHOT_TIMEOUT$"):
        bounded.run_git_bounded(
            ".",
            ["status"],
            deadline=time.monotonic() + 1,
            limit=100,
            input_=b"payload",
            popen=lambda *a, **k: process,
        )

    assert killed == [41]
    assert len(process.waits) == 2


def test_stdin_feed_tolerates_missing_child_pipe() -> None:
    process = _InputProcess()
    process.stdin = None

    output = bounded.run_git_bounded(
        ".",
        ["status"],
        deadline=time.monotonic() + 1,
        limit=100,
        input_=b"payload",
        popen=lambda *a, **k: process,
    )

    assert output == b"result"
    assert len(process.waits) == 1


def test_process_group_wrapper_rejects_platform_without_killpg(monkeypatch) -> None:
    monkeypatch.delattr(bounded.os, "killpg", raising=False)

    with pytest.raises(OSError, match="process-group termination is unavailable"):
        bounded._os_kill_process_group(41, 9)


def test_cleanup_thread_join_error_does_not_escape() -> None:
    waits: list[float | None] = []

    class BrokenJoin:
        def join(self, timeout=None):
            waits.append(timeout)
            raise RuntimeError("unstarted")

    ticks = iter([10.0, 11.0])
    original = bounded.time.monotonic
    bounded.time.monotonic = lambda: next(ticks)
    try:
        bounded._join_threads_bounded([BrokenJoin()])  # type: ignore[list-item]
    finally:
        bounded.time.monotonic = original

    assert waits == [4.0]


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


@POSIX_SNAPSHOT_TEST
def test_recursive_object_store_usage_rejects_shared_budget(tmp_path: Path) -> None:
    # PR #1252 review thread 5947: temporary objects consume the shared budget.
    objects = tmp_path / "objects" / "aa"
    objects.mkdir(parents=True)
    (objects / "object").write_bytes(b"abc")
    epoch = oracle.GitEpoch(b"head", "sha1", (), (), (), ())
    environment = epoch_module.FrozenGitEnvironment(
        str(tmp_path), epoch, 1e20, storage_byte_limit=2
    )
    environment.object_directory = str(tmp_path / "objects")

    _error(environment._refresh_object_usage, "DIFF_SNAPSHOT_CAPACITY")


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


def test_has_split_index_rejects_missing_entry_terminator() -> None:
    fixed = b"\0" * 60 + b"\0\0"
    raw = b"DIRC" + (2).to_bytes(4, "big") + (1).to_bytes(4, "big")
    raw += fixed + b"a.py" + b"\1" * 20

    with pytest.raises(oracle.SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        frozen_index.has_split_index(raw, object_format="sha1")


def test_snapshot_git_disables_system_attributes_with_explicit_env() -> None:
    # PR #1252 review thread 4850: machine attributes are outside P0.2 policy.
    proc = _Proc()
    captured: dict[str, object] = {}

    def popen(command, **kwargs):
        captured.update(kwargs)
        return proc

    bounded.run_git_bounded(
        ".",
        ["status"],
        deadline=time.monotonic() + 1,
        limit=4096,
        env={"PATH": os.environ["PATH"]},
        popen=popen,
    )

    assert captured["env"] == {
        "PATH": os.environ["PATH"],
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }


def test_git_exec_guard_rejects_invalid_limit() -> None:
    # PR #1252 review thread 4867: malformed guards fail before exec.
    from tree_sitter_analyzer import git_exec_guard

    assert git_exec_guard.main(["--fsize", "bad", "--", "git", "status"]) == 2
