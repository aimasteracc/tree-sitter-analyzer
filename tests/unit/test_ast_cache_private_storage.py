"""#1376：test_ast_cache_private_storage 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import errno
import os
from pathlib import Path

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tests.unit._ast_cache_helpers import _OsProxy
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
)
from tree_sitter_analyzer.indexing_snapshot import (
    build_index_candidate_snapshot,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


@pytest.mark.skipif(
    os.name != "posix", reason="GH-1253: dir_fd private writer is POSIX-only"
)
def test_private_candidate_write_rejects_zero_progress(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253: 停滞的私有写入不能发布冻结源码。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    root_fd = os.open(tmp_path, os.O_RDONLY)
    monkeypatch.setattr(materialization.os, "write", lambda *_args: 0)
    try:
        with pytest.raises(OSError, match="no write progress"):
            materialization._write_private_file(root_fd, "leaf", b"x")
    finally:
        os.close(root_fd)


@pytest.mark.skipif(
    os.name != "posix", reason="GH-1253: dir_fd private writer is POSIX-only"
)
def test_private_candidate_write_works_without_nofollow_flag(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253: 可移植 writer 保留独占创建语义。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    class OsProxy:
        def __getattr__(self, name):
            if name == "O_NOFOLLOW":
                raise AttributeError(name)
            return getattr(os, name)

    monkeypatch.setattr(materialization, "os", OsProxy())
    root_fd = os.open(tmp_path, os.O_RDONLY)
    try:
        materialization._write_private_file(root_fd, "leaf", b"x")
    finally:
        os.close(root_fd)

    assert (tmp_path / "leaf").read_bytes() == b"x"


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_owned_cleanup_failure_preserves_success_and_attempts_every_leaf(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: 清理只产生有界遥测，绝不是授权依据。
    import shutil

    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    attempted: list[str] = []
    created: list[str] = []
    real_unlink = materialization.os.unlink
    real_mkdtemp = materialization.tempfile.mkdtemp

    def record_root(*args, **kwargs):
        root = real_mkdtemp(*args, **kwargs)
        created.append(root)
        return root

    def record_unlink(path, *args, **kwargs):
        attempted.append(str(path))
        return real_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(materialization.tempfile, "mkdtemp", record_root)
        patcher.setattr(materialization.os, "unlink", record_unlink)
        patcher.setattr(
            materialization.os,
            "rmdir",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("busy")),
        )
        result = cache.index_project(max_files=10, force=True, workers=0)
    cache.close()
    for root in created:
        shutil.rmtree(root, ignore_errors=True)

    assert (result["indexed"], result["errors"]) == (2, 0)
    assert result["cleanup_warning"] == "INDEX_CANDIDATE_CLEANUP_FAILED: busy"
    assert attempted == ["candidate-00000000", "candidate-00000001"]


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_tolerates_leaf_already_unlinked(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: 叶节点已经不存在时，仍是幂等成功。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    monkeypatch.setattr(
        materialization,
        "os",
        _OsProxy(
            unlink=lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError())
        ),
    )

    warning = materialization.cleanup_index_candidate_snapshot(frozen)
    assert warning == (
        "INDEX_CANDIDATE_CLEANUP_FAILED: "
        + str(
            OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY), frozen.frozen_root)
        )
    )
    import shutil

    shutil.rmtree(frozen.frozen_root or "")


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_chmods_then_retries_denied_unlink(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: 权限拒绝只允许一次安全的 chmod 重试。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    real_unlink = materialization.os.unlink
    calls = 0

    def deny_once(path, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("readonly")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(materialization, "os", _OsProxy(unlink=deny_once))

    assert (materialization.cleanup_index_candidate_snapshot(frozen), calls) == (
        None,
        2,
    )


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_tolerates_leaf_disappearing_during_retry(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: 重试中的竞争不能升级成主要失败。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    outcomes = iter((PermissionError("readonly"), FileNotFoundError()))

    def fail_unlink(*_args, **_kwargs):
        raise next(outcomes)

    monkeypatch.setattr(materialization, "os", _OsProxy(unlink=fail_unlink))

    warning = materialization.cleanup_index_candidate_snapshot(frozen)
    assert warning == (
        "INDEX_CANDIDATE_CLEANUP_FAILED: "
        + str(
            OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY), frozen.frozen_root)
        )
    )
    import shutil

    shutil.rmtree(frozen.frozen_root or "")


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_reports_failed_chmod_retry(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: 重试耗尽只记录警告遥测。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    frozen = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    monkeypatch.setattr(
        materialization,
        "os",
        _OsProxy(
            unlink=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                PermissionError("readonly")
            ),
            chmod=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                PermissionError("still denied")
            ),
        ),
    )

    warning = materialization.cleanup_index_candidate_snapshot(frozen)

    assert warning == (
        "INDEX_CANDIDATE_CLEANUP_FAILED: "
        + str(
            OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY), frozen.frozen_root)
        )
    )
    import shutil

    shutil.rmtree(frozen.frozen_root or "")


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_reports_close_failure(tmp_path: Path, monkeypatch) -> None:
    # PR #1253 thread 3760428941: 描述符关闭错误不能逃逸出清理过程。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
        materialize=True,
    )
    real_close = materialization.os.close

    def close_then_report(fd):
        real_close(fd)
        raise OSError("close failed")

    monkeypatch.setattr(materialization, "os", _OsProxy(close=close_then_report))

    warning = materialization.cleanup_index_candidate_snapshot(snapshot)

    assert warning == "INDEX_CANDIDATE_CLEANUP_FAILED: close failed"


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_tolerates_rmtree_missing_race(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: 执行 rmtree 时目标已消失，仍应视为清理成功。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
        materialize=True,
    )
    root = snapshot.frozen_root or ""
    monkeypatch.setattr(
        materialization.os,
        "rmdir",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    try:
        warning = materialization.cleanup_index_candidate_snapshot(snapshot)
    finally:
        try:
            os.rmdir(root)
        except FileNotFoundError:
            pass

    assert warning is None


def test_release_helper_suppresses_unexpected_cleanup_exception(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: 最终所有权边界必须保留主要输出。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
    )
    monkeypatch.setattr(
        materialization,
        "cleanup_index_candidate_snapshot",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("unexpected")),
    )
    result = {"success": True}

    materialization.release_index_candidate_snapshot(snapshot, result)

    assert result == {
        "success": True,
        "cleanup_warning": "INDEX_CANDIDATE_CLEANUP_FAILED: unexpected",
    }
