import io
import stat
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import tree_sitter_analyzer.source_oracle as core_oracle
import tree_sitter_analyzer.source_oracle_git as oracle
from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST


def _error(call, code: str) -> None:
    with pytest.raises(oracle.SourceOracleError, match=f"^{code}$"):
        call()


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


@POSIX_SNAPSHOT_TEST
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
        core_oracle, "_stat", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_GIT_ERROR")


@POSIX_SNAPSHOT_TEST
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
        core_oracle, "_stat", lambda *a, **k: SimpleNamespace(st_mode=stat.S_IFDIR)
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
        lambda *args, **kwargs: core_oracle.SafePath(None, (b"incomplete",), "file"),
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


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_rejects_tracked_index_inventory_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    _stub_oracle_inventory(tmp_path, monkeypatch, tracked=[b"tracked.py"], indexed={})

    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_GIT_ERROR")


@POSIX_SNAPSHOT_TEST
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


@POSIX_SNAPSHOT_TEST
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


@POSIX_SNAPSHOT_TEST
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


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_supports_unborn_head_untracked_file(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "new.py").write_text("value = 1\n")

    generation, identity = oracle.oracle_generation(str(tmp_path))

    assert (generation[:3], identity.realpath) == ("sg_", str(tmp_path.resolve()))


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_ignores_inherited_git_routing(
    tmp_path: Path, monkeypatch
) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong.git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "wrong-tree"))

    generation, _ = oracle.oracle_generation(str(tmp_path))

    assert generation[:3] == "sg_"


def test_head_identity_rejects_invalid_nonsymbolic_head(monkeypatch) -> None:
    monkeypatch.setattr(
        oracle,
        "git_output",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            oracle.SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        ),
    )

    _error(
        lambda: oracle._head_identity(".", deadline=time.monotonic() + 1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_rejects_unresolvable_git_toplevel(monkeypatch) -> None:
    identity = oracle.RootIdentity("/root", 1, 2)
    calls = 0

    def canonical(_root):
        nonlocal calls
        calls += 1
        if calls == 1:
            return "/root", identity
        raise oracle.SourceOracleError("DIFF_SNAPSHOT_ROOT_INVALID")

    monkeypatch.setattr(oracle, "canonical_root", canonical)
    monkeypatch.setattr(oracle, "git_output", lambda *args, **kwargs: b"/bad\n")

    _error(lambda: oracle.oracle_generation("/root"), "DIFF_SNAPSHOT_ROOT_MISMATCH")


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_rejects_different_git_toplevel(monkeypatch) -> None:
    identity = oracle.RootIdentity("/root", 1, 2)
    other = oracle.RootIdentity("/other", 1, 3)
    calls = 0

    def canonical(_root):
        nonlocal calls
        calls += 1
        return ("/root", identity) if calls == 1 else ("/other", other)

    monkeypatch.setattr(oracle, "canonical_root", canonical)
    monkeypatch.setattr(oracle, "git_output", lambda *args, **kwargs: b"/other\n")

    _error(lambda: oracle.oracle_generation("/root"), "DIFF_SNAPSHOT_ROOT_MISMATCH")


def test_capture_inventory_returns_sorted_normalized_diff_paths(monkeypatch) -> None:
    def output(root, args, **kwargs):
        return b"tracked.py\0" if "--others" not in args else b"new.py\0"

    monkeypatch.setattr(oracle, "git_output", output)
    assert oracle.capture_inventory(
        ".", "diff", deadline=time.monotonic() + 1, limit=100
    ) == ("new.py", "tracked.py")


def test_capture_inventory_rejects_tracked_untracked_overlap(monkeypatch) -> None:
    monkeypatch.setattr(oracle, "git_output", lambda *a, **k: b"same.py\0")
    _error(
        lambda: oracle.capture_inventory(
            ".", "diff", deadline=time.monotonic() + 1, limit=100
        ),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_capture_inventory_rejects_union_path_count(monkeypatch) -> None:
    def output(root, args, **kwargs):
        return b"a\0" if "--others" not in args else b"b\0"

    monkeypatch.setattr(oracle, "git_output", output)
    monkeypatch.setattr(oracle, "_MAX_WORKTREE_PATHS", 1)
    _error(
        lambda: oracle.capture_inventory(
            ".", "diff", deadline=time.monotonic() + 1, limit=100
        ),
        "DIFF_SNAPSHOT_CAPACITY",
    )


@pytest.mark.parametrize(
    ("raw", "limit"), [(b"x" * 4097 + b"\0", 5000), (b"path\0", 1)]
)
def test_capture_inventory_rejects_encoded_storage_capacity(
    monkeypatch, raw: bytes, limit: int
) -> None:
    monkeypatch.setattr(oracle, "git_output", lambda *a, **k: raw)
    _error(
        lambda: oracle.capture_inventory(
            ".", "staged", deadline=time.monotonic() + 1, limit=limit
        ),
        "DIFF_SNAPSHOT_CAPACITY",
    )
