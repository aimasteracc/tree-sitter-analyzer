import errno
import hashlib
import os
import time
from pathlib import Path

import pytest

import tree_sitter_analyzer.source_oracle as oracle
from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST


def _error(call, code: str) -> None:
    with pytest.raises(oracle.SourceOracleError, match=f"^{code}$"):
        call()


@POSIX_SNAPSHOT_TEST
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


@POSIX_SNAPSHOT_TEST
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


@POSIX_SNAPSHOT_TEST
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


@POSIX_SNAPSHOT_TEST
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


@POSIX_SNAPSHOT_TEST
def test_safe_absolute_regular_rejects_oversize_index(tmp_path: Path) -> None:
    index = tmp_path / "index"
    index.write_bytes(b"index")

    _error(
        lambda: oracle._safe_absolute_regular(
            str(index), deadline=time.monotonic() + 1, limit=4
        ),
        "DIFF_SNAPSHOT_CAPACITY",
    )


@POSIX_SNAPSHOT_TEST
def test_frame_workspace_gitlink_binds_initialized_directory(tmp_path: Path) -> None:
    checkout = tmp_path / "module"
    checkout.mkdir()
    digest = hashlib.sha256()

    charge = oracle._frame_workspace_path(
        digest,
        str(tmp_path),
        b"module",
        deadline=time.monotonic() + 1,
        content_budget=0,
        content_required=True,
        index_entry=b"160000 abcdef 0",
        head_entry=b"160000 commit abcdef",
    )

    assert charge == 0


def test_safe_absolute_regular_rejects_unsupported_platform(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(oracle, "_supports_nofollow", lambda: False)

    _error(
        lambda: oracle._safe_absolute_regular(
            str(tmp_path / "index"), deadline=time.monotonic() + 1, limit=1
        ),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


@POSIX_SNAPSHOT_TEST
def test_safe_absolute_regular_handles_missing_index(tmp_path: Path) -> None:
    result = oracle._safe_absolute_regular(
        str(tmp_path / "index"),
        deadline=time.monotonic() + 1,
        limit=1,
        allow_missing=True,
    )

    assert (result.data, result.metadata[-1], result.kind) == (
        None,
        b"missing",
        "missing",
    )


@POSIX_SNAPSHOT_TEST
def test_safe_absolute_regular_rejects_missing_index(tmp_path: Path) -> None:
    _error(
        lambda: oracle._safe_absolute_regular(
            str(tmp_path / "index"), deadline=time.monotonic() + 1, limit=1
        ),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


@POSIX_SNAPSHOT_TEST
def test_safe_absolute_regular_rejects_directory_leaf(tmp_path: Path) -> None:
    (tmp_path / "index").mkdir()

    _error(
        lambda: oracle._safe_absolute_regular(
            str(tmp_path / "index"), deadline=time.monotonic() + 1, limit=1
        ),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


@POSIX_SNAPSHOT_TEST
def test_safe_absolute_regular_detects_replace_between_stat_and_open(
    tmp_path: Path, monkeypatch
) -> None:
    index = tmp_path / "index"
    replacement = tmp_path / "replacement"
    index.write_bytes(b"old")
    replacement.write_bytes(b"new")
    real_open = oracle._open

    def replace_before_open(path, flags, *args, **kwargs):
        if path == "index" and not args:
            os.replace(replacement, index)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(oracle, "_open", replace_before_open)

    _error(
        lambda: oracle._safe_absolute_regular(
            str(index), deadline=time.monotonic() + 1, limit=10
        ),
        "DIFF_SNAPSHOT_SOURCE_CHANGED",
    )


@POSIX_SNAPSHOT_TEST
def test_safe_absolute_regular_ignores_close_error(tmp_path: Path, monkeypatch) -> None:
    index = tmp_path / "index"
    index.write_bytes(b"index")
    real_close = oracle._close
    calls = 0

    def close_then_raise(fd: int) -> None:
        nonlocal calls
        real_close(fd)
        calls += 1
        if calls == 1:
            raise OSError("close")

    monkeypatch.setattr(oracle, "_close", close_then_raise)

    result = oracle._safe_absolute_regular(
        str(index), deadline=time.monotonic() + 1, limit=10
    )

    assert result.data == b"index"


def test_regular_open_flags_fail_closed_without_platform_support(monkeypatch) -> None:
    monkeypatch.setattr(oracle, "_supports_nofollow", lambda: False)
    _error(oracle._regular_open_flags, "DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED")


@POSIX_SNAPSHOT_TEST
def test_safe_payload_read_rejects_replaced_ancestor_chain(tmp_path: Path) -> None:
    # PR #1252 review thread 3746878588: payload must match the pre-epoch manifest.
    root = tmp_path / "repo"
    target = root / "pkg" / "a.py"
    target.parent.mkdir(parents=True)
    target.write_text("trusted\n")
    before = oracle.safe_workspace_path(
        str(root), "pkg/a.py", deadline=time.monotonic() + 10, limit=1024
    )
    expected = oracle.stable_descriptor_chain(before.metadata)
    (root / "pkg").rename(root / "original")
    (root / "pkg").mkdir()
    (root / "pkg" / "a.py").write_text("replacement\n")

    _error(
        lambda: oracle.safe_workspace_path(
            str(root),
            "pkg/a.py",
            deadline=time.monotonic() + 10,
            limit=1024,
            expected_chain=expected,
        ),
        "DIFF_SNAPSHOT_SOURCE_CHANGED",
    )


def test_stable_descriptor_chain_rejects_malformed_metadata() -> None:
    # PR #1252 review thread 3746878588.
    _error(
        lambda: oracle.stable_descriptor_chain((b"bad",)),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )


@POSIX_SNAPSHOT_TEST
def test_safe_workspace_path_can_bind_regular_metadata_without_content(
    tmp_path: Path,
) -> None:
    target = tmp_path / "metadata-only.py"
    target.write_text("secret content\n")

    safe = oracle.safe_workspace_path(
        str(tmp_path),
        "metadata-only.py",
        deadline=time.monotonic() + 1,
        limit=0,
        read_regular=False,
    )

    assert (safe.kind, safe.data) == ("file", None)


@pytest.mark.parametrize("replacement_kind", ["file", "symlink"])
@POSIX_SNAPSHOT_TEST
def test_non_directory_ancestor_makes_descendant_missing(
    tmp_path: Path, replacement_kind: str
) -> None:
    # PR #1252 review thread 4858: replacement deletion is safe inventory state.
    root = tmp_path / "repo"
    ancestor = root / "pkg"
    ancestor.mkdir(parents=True)
    (ancestor / "a.py").write_text("old\n")
    (ancestor / "a.py").unlink()
    ancestor.rmdir()
    if replacement_kind == "file":
        ancestor.write_text("replacement\n")
    else:
        ancestor.symlink_to("replacement-target")

    result = oracle.safe_workspace_path(
        str(root), "pkg/a.py", deadline=time.monotonic() + 10, limit=1024
    )

    assert result.kind == "missing"
    assert result.metadata[-1] == b"missing"
    assert len(result.metadata) == 3


@POSIX_SNAPSHOT_TEST
def test_ancestor_disappearing_between_lstat_and_open_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 4858: concurrent ancestor deletion is a deletion.
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    real_open = oracle._open

    def open_path(path, flags, **kwargs):
        if path == "pkg":
            raise FileNotFoundError()
        return real_open(path, flags, **kwargs)

    monkeypatch.setattr(oracle, "_open", open_path)
    result = oracle.safe_workspace_path(
        str(root), "pkg/a.py", deadline=time.monotonic() + 10, limit=1024
    )

    assert result.kind == "missing"


@POSIX_SNAPSHOT_TEST
def test_ancestor_permission_error_remains_unsafe(tmp_path: Path, monkeypatch) -> None:
    # PR #1252 review thread 4858: permission failures are never deletions.
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    real_open = oracle._open

    def open_path(path, flags, **kwargs):
        if path == "pkg":
            raise PermissionError(errno.EACCES, "denied")
        return real_open(path, flags, **kwargs)

    monkeypatch.setattr(oracle, "_open", open_path)
    _error(
        lambda: oracle.safe_workspace_path(
            str(root), "pkg/a.py", deadline=time.monotonic() + 10, limit=1024
        ),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )


@POSIX_SNAPSHOT_TEST
def test_non_directory_ancestor_failed_second_lstat_is_unsafe(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 4858: both no-follow identities are mandatory.
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pkg").write_text("replacement")
    real_stat = oracle._stat
    calls = 0

    def stat_path(path, **kwargs):
        nonlocal calls
        if path == "pkg":
            calls += 1
            if calls == 2:
                raise FileNotFoundError()
        return real_stat(path, **kwargs)

    monkeypatch.setattr(oracle, "_stat", stat_path)
    _error(
        lambda: oracle.safe_workspace_path(
            str(root), "pkg/a.py", deadline=time.monotonic() + 10, limit=1024
        ),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )


@pytest.mark.parametrize(
    "unsafe_state", ["before-directory", "after-directory", "changed"]
)
@POSIX_SNAPSHOT_TEST
def test_unstable_non_directory_ancestor_is_unsafe(
    tmp_path: Path, monkeypatch, unsafe_state: str
) -> None:
    # PR #1252 review thread 4858: replacement races do not become deletions.
    root = tmp_path / "repo"
    root.mkdir()
    regular = root / "regular"
    regular.write_text("one")
    changed = root / "changed"
    changed.write_text("two")
    directory = root / "directory"
    directory.mkdir()
    before = directory.stat() if unsafe_state == "before-directory" else regular.stat()
    after = directory.stat() if unsafe_state == "after-directory" else changed.stat()
    stats = iter([before, after])
    real_stat = oracle._stat
    real_open = oracle._open

    def stat_path(path, **kwargs):
        return next(stats) if path == "pkg" else real_stat(path, **kwargs)

    def open_path(path, flags, **kwargs):
        if path == "pkg":
            raise OSError(errno.ENOTDIR, "not directory")
        return real_open(path, flags, **kwargs)

    monkeypatch.setattr(oracle, "_stat", stat_path)
    monkeypatch.setattr(oracle, "_open", open_path)
    _error(
        lambda: oracle.safe_workspace_path(
            str(root), "pkg/a.py", deadline=time.monotonic() + 10, limit=1024
        ),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )


@POSIX_SNAPSHOT_TEST
def test_ancestor_changed_between_lstat_and_directory_open_is_source_changed(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 4858: opened directory must match pre-open identity.
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    other = root / "other"
    other.mkdir()
    real_stat = oracle._stat

    def stat_path(path, **kwargs):
        return other.stat() if path == "pkg" else real_stat(path, **kwargs)

    monkeypatch.setattr(oracle, "_stat", stat_path)
    _error(
        lambda: oracle.safe_workspace_path(
            str(root), "pkg/a.py", deadline=time.monotonic() + 10, limit=1024
        ),
        "DIFF_SNAPSHOT_SOURCE_CHANGED",
    )
