"""RFC-0026 §2/§5 B1：候选树快照、夹具复制、补丁应用与 workspace 清理。

快照只用 ``lstat``、绝不跟随符号链接或阻塞在特殊文件上；任何无法读取的条目都
以独立签名记录，从而被 ``changed_entries`` 视为改动。每个测试只断言一个结果。
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b import candidate
from tree_sitter_analyzer.no1_010b.candidate import (
    CandidateError,
    apply_patch,
    copy_fixture,
    remove_tree,
    tree_snapshot,
)

POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: needs unprivileged symlinks / POSIX permission bits",
)


def test_copy_into_existing_destination_is_candidate_error(tmp_path: Path) -> None:
    source, destination = tmp_path / "src", tmp_path / "dst"
    source.mkdir()
    destination.mkdir()
    with pytest.raises(CandidateError, match="^fixture copy failed: "):
        copy_fixture(source, destination)


def test_git_apply_that_cannot_run_is_candidate_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def hung(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(["git"], candidate.GIT_TIMEOUT_S)

    monkeypatch.setattr(candidate.subprocess, "run", hung)
    with pytest.raises(CandidateError, match="^git apply could not run: "):
        apply_patch(tmp_path, tmp_path / "x.patch", {})


def test_file_replaced_after_lstat_is_special(tmp_path: Path) -> None:
    # TOCTOU 防护：打开后的 inode 与 lstat 时不同（被替换）即判为异常条目。
    target, other = tmp_path / "target", tmp_path / "other"
    target.write_bytes(b"a")
    other.write_bytes(b"b")
    assert candidate._file_digest(target, os.lstat(other)) == "special"


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux-only: /proc/self/mem is a regular file whose read() fails (EIO)",
)
def test_file_whose_read_fails_is_unreadable() -> None:
    mem = Path("/proc/self/mem")
    assert candidate._file_digest(mem, os.lstat(mem)) == "unreadable"


def test_vanished_entry_signature_is_unreadable(tmp_path: Path) -> None:
    assert candidate._entry_signature(tmp_path / "gone") == ("unreadable", False)


@POSIX_ONLY
def test_symlink_is_recorded_by_target_without_following(tmp_path: Path) -> None:
    (tmp_path / "link").symlink_to("../outside/secret")
    assert tree_snapshot(tmp_path)["link"] == "link:../outside/secret"


@POSIX_ONLY
def test_unreadable_symlink_target_is_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # lstat 之后、readlink 之前链接消失的竞态：记为不可读，而不是抛异常。
    (tmp_path / "link").symlink_to("target")

    def vanished(_path: object) -> str:
        raise FileNotFoundError("link vanished")

    monkeypatch.setattr(candidate.os, "readlink", vanished)
    assert tree_snapshot(tmp_path)["link"] == "unreadable"


@POSIX_ONLY
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses directory permission bits",
)
def test_unlistable_directory_is_unreadable(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        signature = tree_snapshot(tmp_path)["locked"]
    finally:
        locked.chmod(stat.S_IRWXU)
    assert signature == "unreadable"


def test_ignored_names_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_bytes(b"")
    (tmp_path / "kept.txt").write_bytes(b"")
    assert sorted(tree_snapshot(tmp_path, ("__pycache__",))) == [".", "kept.txt"]


@POSIX_ONLY
def test_remove_tree_does_not_chmod_through_symlinks(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep")
    outside.chmod(0o444)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "link").symlink_to(outside)
    remove_tree(workspace)
    observed = (workspace.exists(), stat.S_IMODE(outside.stat().st_mode))
    outside.chmod(stat.S_IRWXU)
    assert observed == (False, 0o444)


def test_remove_tree_tolerates_chmod_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "ws"
    (workspace / "sub").mkdir(parents=True)
    (workspace / "sub" / "f.txt").write_bytes(b"x")

    def denied(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("chmod denied")

    monkeypatch.setattr(candidate.os, "chmod", denied)
    remove_tree(workspace)
    assert workspace.exists() is False
