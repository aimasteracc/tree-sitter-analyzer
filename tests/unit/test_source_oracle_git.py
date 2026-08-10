import os
import shutil
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


def test_index_entries_uses_private_mode_600_exact_bytes(monkeypatch) -> None:
    observed: list[tuple[bytes, int, str]] = []

    def run(root, args, *, env, **kwargs):
        path = env["GIT_INDEX_FILE"]
        observed.append(
            (Path(path).read_bytes(), stat.S_IMODE(os.stat(path).st_mode), path)
        )
        return b"100644 a 0\tpath\0"

    monkeypatch.setattr(oracle, "run_git_bounded", run)

    entries = oracle._index_entries(
        ".", deadline=time.monotonic() + 1, index_bytes=b"exact-index"
    )

    assert entries == {b"path": b"100644 a 0"}
    assert observed[0][:2] == (b"exact-index", 0o600)
    assert Path(observed[0][2]).exists() is False


def test_index_entries_rejects_private_index_inside_project(
    tmp_path: Path, monkeypatch
) -> None:
    index_path = tmp_path / "private-index"

    def mkstemp(*, prefix):
        descriptor = os.open(index_path, os.O_CREAT | os.O_RDWR, 0o600)
        return descriptor, str(index_path)

    monkeypatch.setattr(oracle.tempfile, "mkstemp", mkstemp)

    _error(
        lambda: oracle._index_entries(
            str(tmp_path), deadline=time.monotonic() + 1, index_bytes=b"index"
        ),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )
    assert index_path.exists() is False


def test_index_entries_cleanup_tolerates_already_removed_temp(monkeypatch) -> None:
    real_unlink = os.unlink
    removed: list[str] = []

    def remove_then_report_missing(path):
        real_unlink(path)
        removed.append(path)
        raise FileNotFoundError

    monkeypatch.setattr(oracle, "run_git_bounded", lambda *a, **k: b"")
    monkeypatch.setattr(oracle.os, "unlink", remove_then_report_missing)

    entries = oracle._index_entries(
        ".", deadline=time.monotonic() + 1, index_bytes=b"index"
    )

    assert entries == {}
    assert len(removed) == 1


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
        if args == ["rev-parse", "--show-object-format"]:
            return b"sha1\n"
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
def test_oracle_generation_epoch_uses_frozen_index_entries(
    tmp_path: Path, monkeypatch
) -> None:
    entry = b"100644 blob-id 0"
    _stub_oracle_inventory(
        tmp_path, monkeypatch, tracked=[], indexed={b"tracked.py": entry}
    )
    monkeypatch.setattr(oracle, "_frame_workspace_path", lambda *a, **k: 0)
    epochs: list[oracle.GitEpoch] = []

    oracle.oracle_generation(str(tmp_path), epoch_out=epochs)

    assert epochs[0].index_entries == ((b"tracked.py", entry),)


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


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_preserves_repository_trailing_newline(
    tmp_path: Path,
) -> None:
    # PR #1252 review thread 3747224321.
    root = tmp_path / "repo\n"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)

    generation, identity = oracle.oracle_generation(str(root))

    assert (generation[:3], identity.realpath) == ("sg_", str(root.resolve()))


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_preserves_gitdir_trailing_newline(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3747224321.
    root = tmp_path / "worktree"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    git_dir = tmp_path / "metadata\n"
    shutil.copytree(root / ".git", git_dir)
    real_output = oracle.git_output

    def output(repo, args, **kwargs):
        if args == ["rev-parse", "--git-dir"]:
            return os.fsencode(git_dir) + b"\n"
        return real_output(repo, args, **kwargs)

    monkeypatch.setattr(oracle, "git_output", output)
    generation, identity = oracle.oracle_generation(str(root))

    assert (generation[:3], identity.realpath) == ("sg_", str(root.resolve()))


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_skips_missing_dirty_gitlink(
    tmp_path: Path, monkeypatch
) -> None:
    entry = b"160000 " + b"a" * 40 + b" 0"
    _stub_oracle_inventory(
        tmp_path,
        monkeypatch,
        tracked=[b"vendor"],
        indexed={b"vendor": entry},
        dirty=b"vendor\0",
    )

    generation, _identity = oracle.oracle_generation(str(tmp_path), "diff")

    assert generation[:3] == "sg_"


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_rejects_invalid_dirty_gitlink_oid(
    tmp_path: Path, monkeypatch
) -> None:
    entry = b"160000 " + b"a" * 40 + b" 0"
    _stub_oracle_inventory(
        tmp_path,
        monkeypatch,
        tracked=[b"vendor"],
        indexed={b"vendor": entry},
        dirty=b"vendor\0",
    )
    safe = core_oracle.SafePath(None, (b"1,2,16877,0,0,0",), "directory")
    monkeypatch.setattr(oracle, "safe_workspace_path", lambda *a, **k: safe)
    original = oracle.git_output

    def output(root, args, **kwargs):
        if args == ["rev-parse", "--verify", "HEAD"] and root != str(tmp_path):
            return b"not-an-oid\n"
        return original(root, args, **kwargs)

    monkeypatch.setattr(oracle, "git_output", output)

    _error(
        lambda: oracle.oracle_generation(str(tmp_path), "diff"),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_rejects_wrong_length_dirty_gitlink_oid(
    tmp_path: Path, monkeypatch
) -> None:
    entry = b"160000 " + b"a" * 40 + b" 0"
    _stub_oracle_inventory(
        tmp_path,
        monkeypatch,
        tracked=[b"vendor"],
        indexed={b"vendor": entry},
        dirty=b"vendor\0",
    )
    safe = core_oracle.SafePath(None, (b"1,2,16877,0,0,0",), "directory")
    monkeypatch.setattr(oracle, "safe_workspace_path", lambda *a, **k: safe)
    original = oracle.git_output

    def output(root, args, **kwargs):
        if args == ["rev-parse", "--verify", "HEAD"] and root != str(tmp_path):
            return b"a" * 39 + b"\n"
        return original(root, args, **kwargs)

    monkeypatch.setattr(oracle, "git_output", output)

    _error(
        lambda: oracle.oracle_generation(str(tmp_path), "diff"),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )
