import io
import os
import stat
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import tree_sitter_analyzer.source_oracle as oracle


def _error(call, code: str) -> None:
    with pytest.raises(oracle.SourceOracleError, match=f"^{code}$"):
        call()


@pytest.mark.parametrize("value", ["", "/absolute", "../escape", "a/../b", "bad\0name"])
def test_normalize_repo_path_rejects_unsafe_paths(value: str) -> None:
    _error(lambda: oracle.normalize_repo_path(value), "DIFF_SNAPSHOT_INVALID_PATH")


def test_remaining_rejects_expired_deadline(monkeypatch) -> None:
    monkeypatch.setattr(oracle.time, "monotonic", lambda: 10.0)
    _error(lambda: oracle._remaining(10.0), "DIFF_SNAPSHOT_TIMEOUT")


def test_canonical_root_translates_stat_error(monkeypatch) -> None:
    monkeypatch.setattr(
        oracle, "_stat", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(lambda: oracle.canonical_root("missing"), "DIFF_SNAPSHOT_ROOT_INVALID")


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


def test_safe_workspace_path_translates_leaf_lstat_error(
    tmp_path: Path, monkeypatch
) -> None:
    real_stat = oracle._stat

    def fail_leaf_lstat(path, *args, **kwargs):
        if kwargs.get("dir_fd") is not None:
            raise PermissionError("injected leaf lstat failure")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(oracle, "_stat", fail_leaf_lstat)
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "tracked.py", deadline=time.monotonic() + 1, limit=10
        ),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )


def test_safe_workspace_path_translates_symlink_readlink_error(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "tracked.py").symlink_to("target.py")
    monkeypatch.setattr(
        oracle,
        "_readlink",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            PermissionError("injected readlink failure")
        ),
    )
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "tracked.py", deadline=time.monotonic() + 1, limit=10
        ),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )


def test_safe_workspace_path_rejects_unsupported_platform(monkeypatch) -> None:
    monkeypatch.setattr(oracle, "_supports_nofollow", lambda: False)
    _error(
        lambda: oracle.safe_workspace_path(
            ".", "a", deadline=time.monotonic() + 1, limit=1
        ),
        "DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED",
    )


@pytest.mark.skipif(
    os.name != "nt",
    reason="tracked: RFC-0022 P0.2 Windows fail-closed workspace contract",
)
def test_safe_workspace_path_windows_fails_before_opening_files(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252: Windows must fail closed before attempting a workspace descriptor.
    opened: list[tuple[object, ...]] = []
    monkeypatch.setattr(oracle, "_open", lambda *args, **kwargs: opened.append(args))

    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "a", deadline=time.monotonic() + 1, limit=1
        ),
        "DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED",
    )

    assert opened == []


def test_safe_workspace_path_translates_open_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        oracle, "_open", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "x", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )


def test_safe_workspace_path_translates_read_error(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "x"
    target.write_bytes(b"x")
    monkeypatch.setattr(
        oracle, "_read", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "x", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )


def test_oracle_generation_translates_index_lstat_error(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        oracle,
        "canonical_root",
        lambda root: (str(tmp_path), oracle.RootIdentity(str(tmp_path), 1, 2)),
    )
    monkeypatch.setattr(
        oracle,
        "git_output",
        lambda root, args, **k: b".git\n" if "--git-dir" in args else b"head",
    )
    monkeypatch.setattr(
        oracle, "_stat", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_GIT_ERROR")


def test_oracle_generation_rejects_nonregular_index(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        oracle,
        "canonical_root",
        lambda root: (str(tmp_path), oracle.RootIdentity(str(tmp_path), 1, 2)),
    )
    monkeypatch.setattr(
        oracle,
        "git_output",
        lambda root, args, **k: b".git\n" if "--git-dir" in args else b"head",
    )
    monkeypatch.setattr(
        oracle, "_stat", lambda *a, **k: SimpleNamespace(st_mode=stat.S_IFDIR)
    )
    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_GIT_ERROR")


def test_capture_consistent_reports_generation_change(monkeypatch) -> None:
    values = iter([("before", None), ("after", None)])
    monkeypatch.setattr(oracle, "oracle_generation", lambda root: next(values))
    generation, value = oracle.capture_consistent(".", lambda: 7)
    assert generation is None
    assert value == 7


def test_source_generation_returns_oracle_value(monkeypatch) -> None:
    monkeypatch.setattr(
        oracle, "oracle_generation", lambda root, mode: ("sg_test", None)
    )
    assert oracle.source_generation(".", "staged") == "sg_test"


def test_normalize_repo_path_strips_each_dot_prefix() -> None:
    assert oracle.normalize_repo_path("././file.py") == "file.py"


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


def test_frame_workspace_path_rejects_malformed_metadata_epoch(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        oracle,
        "safe_workspace_path",
        lambda *args, **kwargs: oracle.SafePath(None, (b"incomplete",), "file"),
    )

    _error(
        lambda: oracle._frame_workspace_path(
            SimpleNamespace(update=lambda value: None),
            str(tmp_path),
            b"tracked.py",
            deadline=time.monotonic() + 1,
            content_budget=10,
            content_required=False,
            index_entry=b"100644 blob-id 0",
            head_entry=b"100644 blob blob-id",
        ),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )


def test_oracle_generation_rejects_oversize_index(tmp_path: Path, monkeypatch) -> None:
    index = tmp_path / "index"
    index.write_bytes(b"index")
    identity = oracle.RootIdentity(str(tmp_path), 1, 2)
    monkeypatch.setattr(
        oracle, "canonical_root", lambda root: (str(tmp_path), identity)
    )
    monkeypatch.setattr(
        oracle,
        "git_output",
        lambda root, args, **k: b".\n" if "--git-dir" in args else b"",
    )

    class Huge:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            return b"x" * (64 * 1024 * 1024 + 1)

    monkeypatch.setattr(oracle, "_open_file", lambda *a, **k: Huge())
    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_CAPACITY")


def test_tracked_paths_rejects_bounded_path_count(monkeypatch) -> None:
    monkeypatch.setattr(oracle, "_MAX_WORKTREE_PATHS", 1)
    monkeypatch.setattr(oracle, "git_output", lambda *args, **kwargs: b"a\0b\0")

    _error(
        lambda: oracle._tracked_paths(".", deadline=time.monotonic() + 1),
        "DIFF_SNAPSHOT_CAPACITY",
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"malformed\0",
        b"100644 a 0\t\0",
        b"100644 a\tpath\0",
        b"100644 a 1\tpath\0",
        b"invalid a 0\tpath\0",
        b"100644 invalid-hash 0\tpath\0",
        b"100644 a 0\tpath\x00100644 b 0\tpath\0",
    ],
)
def test_index_entries_rejects_hostile_inventory(monkeypatch, raw: bytes) -> None:
    monkeypatch.setattr(oracle, "git_output", lambda *args, **kwargs: raw)

    _error(
        lambda: oracle._index_entries(".", deadline=time.monotonic() + 1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_index_entries_rejects_bounded_path_count(monkeypatch) -> None:
    raw = b"100644 a 0\ta\x00100644 b 0\tb\0"
    monkeypatch.setattr(oracle, "_MAX_WORKTREE_PATHS", 1)
    monkeypatch.setattr(oracle, "git_output", lambda *args, **kwargs: raw)

    _error(
        lambda: oracle._index_entries(".", deadline=time.monotonic() + 1),
        "DIFF_SNAPSHOT_CAPACITY",
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"malformed\0",
        b"100644 blob a\t\0",
        b"100644 a\tpath\0",
        b"invalid blob a\tpath\0",
        b"100644 blob invalid-hash\tpath\0",
        b"100644 tree a\tpath\0",
        b"100644 blob a\tpath\x00100644 blob b\tpath\0",
    ],
)
def test_head_entries_rejects_hostile_inventory(monkeypatch, raw: bytes) -> None:
    monkeypatch.setattr(oracle, "git_output", lambda *args, **kwargs: raw)

    _error(
        lambda: oracle._head_entries(".", deadline=time.monotonic() + 1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_head_entries_rejects_bounded_path_count(monkeypatch) -> None:
    raw = b"100644 blob a\ta\x00100644 commit b\tb\0"
    monkeypatch.setattr(oracle, "_MAX_WORKTREE_PATHS", 1)
    monkeypatch.setattr(oracle, "git_output", lambda *args, **kwargs: raw)

    _error(
        lambda: oracle._head_entries(".", deadline=time.monotonic() + 1),
        "DIFF_SNAPSHOT_CAPACITY",
    )


def _stub_oracle_inventory(
    tmp_path: Path,
    monkeypatch,
    *,
    tracked: list[bytes],
    indexed: dict[bytes, bytes],
    dirty: bytes = b"",
    untracked: bytes = b"",
) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "index").write_bytes(b"index")
    identity = oracle.RootIdentity(str(tmp_path), 1, 2)
    monkeypatch.setattr(
        oracle, "canonical_root", lambda root: (str(tmp_path), identity)
    )
    monkeypatch.setattr(oracle, "_tracked_paths", lambda *args, **kwargs: tracked)
    monkeypatch.setattr(oracle, "_index_entries", lambda *args, **kwargs: indexed)
    monkeypatch.setattr(oracle, "_head_entries", lambda *args, **kwargs: {})

    def git_output(root, args, **kwargs):
        if args == ["rev-parse", "--verify", "HEAD"]:
            return b"head\n"
        if args == ["rev-parse", "--git-dir"]:
            return b".git\n"
        if "--name-only" in args:
            return dirty
        if "--others" in args:
            return untracked
        return b""

    monkeypatch.setattr(oracle, "git_output", git_output)


def test_oracle_generation_rejects_tracked_index_inventory_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    _stub_oracle_inventory(tmp_path, monkeypatch, tracked=[b"tracked.py"], indexed={})

    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_GIT_ERROR")


def test_oracle_generation_rejects_dirty_inventory_over_capacity(
    tmp_path: Path, monkeypatch
) -> None:
    entry = b"100644 blob-id 0"
    _stub_oracle_inventory(
        tmp_path,
        monkeypatch,
        tracked=[b"tracked.py"],
        indexed={b"tracked.py": entry},
        dirty=b"tracked.py\0",
    )
    monkeypatch.setattr(oracle, "_MAX_WORKTREE_PATHS", 0)

    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_CAPACITY")


def test_oracle_generation_rejects_dirty_path_outside_tracked_inventory(
    tmp_path: Path, monkeypatch
) -> None:
    entry = b"100644 blob-id 0"
    _stub_oracle_inventory(
        tmp_path,
        monkeypatch,
        tracked=[b"tracked.py"],
        indexed={b"tracked.py": entry},
        dirty=b"untracked.py\0",
    )

    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_GIT_ERROR")


def test_oracle_generation_rejects_untracked_path_in_tracked_inventory(
    tmp_path: Path, monkeypatch
) -> None:
    entry = b"100644 blob-id 0"
    _stub_oracle_inventory(
        tmp_path,
        monkeypatch,
        tracked=[b"tracked.py"],
        indexed={b"tracked.py": entry},
        untracked=b"tracked.py\0",
    )

    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_GIT_ERROR")
