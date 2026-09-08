"""#1376：test_ast_cache_candidate_cleanup 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import os
from dataclasses import replace
from pathlib import Path

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tests.unit._ast_cache_helpers import _OsProxy
from tree_sitter_analyzer.indexing_snapshot import (
    build_index_candidate_snapshot,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


def test_candidate_cleanup_without_owned_root_is_noop(tmp_path: Path) -> None:
    # PR #1253: 未冻结的快照绝不能授权递归清理。
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
    )
    cleanup_index_candidate_snapshot(snapshot)

    assert snapshot.frozen_root is None


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_is_idempotent_after_root_disappears(tmp_path: Path) -> None:
    # PR #1253 thread 3760428941: 已经释放的根目录是幂等的零操作。

    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
    )
    missing = replace(snapshot, frozen_root=str(tmp_path / "gone"))

    assert cleanup_index_candidate_snapshot(missing) is None


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_suppresses_root_open_failure(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: 根目录打开错误转为有界遥测。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    root = tmp_path / "candidate-root"
    root.mkdir()
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
    )

    frozen = replace(snapshot, frozen_root=str(root))
    monkeypatch.setattr(
        materialization,
        "os",
        _OsProxy(
            open=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                PermissionError("denied")
            )
        ),
    )

    warning = materialization.cleanup_index_candidate_snapshot(frozen)

    assert warning == "INDEX_CANDIDATE_CLEANUP_FAILED: denied"


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_rejects_path_identity_change_after_fd_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
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
    captured = Path(frozen.frozen_root or "")
    real_stat = materialization.os.stat

    def replaced_stat(path, *args, **kwargs):
        observed = real_stat(path, *args, **kwargs)
        if os.fspath(path) == os.fspath(captured):
            from types import SimpleNamespace

            return SimpleNamespace(st_dev=observed.st_dev, st_ino=observed.st_ino + 1)
        return observed

    monkeypatch.setattr(materialization.os, "stat", replaced_stat)
    warning = materialization.cleanup_index_candidate_snapshot(frozen)
    assert captured.exists() is True
    assert warning == (
        "INDEX_CANDIDATE_CLEANUP_FAILED: INDEX_CANDIDATE_CLEANUP_ROOT_REPLACED"
    )
    import shutil

    shutil.rmtree(captured)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_fstat_failure_is_warning_and_closes_fd(
    tmp_path: Path, monkeypatch
) -> None:
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
    real_fstat = materialization.os.fstat
    real_open = materialization.os.open
    opened: list[int] = []

    def record_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(materialization.os, "open", record_open)
    monkeypatch.setattr(
        materialization.os,
        "fstat",
        lambda _fd: (_ for _ in ()).throw(OSError("fstat denied")),
    )
    warning = materialization.cleanup_index_candidate_snapshot(frozen)
    monkeypatch.setattr(materialization.os, "fstat", real_fstat)
    assert warning == "INDEX_CANDIDATE_CLEANUP_FAILED: fstat denied"
    assert len(opened) == 1
    with pytest.raises(OSError):
        real_fstat(opened[0])
    import shutil

    shutil.rmtree(frozen.frozen_root or "")


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_never_recursively_removes_post_check_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    import shutil

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
    captured = Path(frozen.frozen_root or "")
    displaced = captured.with_name(captured.name + "-displaced")
    real_rmdir = materialization.os.rmdir

    def swap_then_rmdir(path):
        captured.rename(displaced)
        captured.mkdir()
        (captured / "replacement").write_text("keep", encoding="utf-8")
        return real_rmdir(path)

    monkeypatch.setattr(materialization.os, "rmdir", swap_then_rmdir)
    warning = materialization.cleanup_index_candidate_snapshot(frozen)
    assert (captured / "replacement").read_text(encoding="utf-8") == "keep"
    assert warning is not None
    monkeypatch.setattr(materialization.os, "rmdir", real_rmdir)
    shutil.rmtree(captured)
    shutil.rmtree(displaced)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_cleanup_keeps_replacement_root(tmp_path: Path) -> None:
    # PR #1253 thread 3763124090: 清理权限属于捕获的身份。
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
    captured = Path(frozen.frozen_root or "")
    displaced = captured.with_name(captured.name + "-displaced")
    captured.rename(displaced)
    captured.mkdir()
    sentinel = captured / "replacement"
    sentinel.write_text("keep", encoding="utf-8")

    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    warning = cleanup_index_candidate_snapshot(frozen)
    observed = (sentinel.read_text(encoding="utf-8"), displaced.exists())
    import shutil

    shutil.rmtree(captured)
    shutil.rmtree(displaced)

    assert observed == ("keep", True)
    assert (
        warning
        == "INDEX_CANDIDATE_CLEANUP_FAILED: INDEX_CANDIDATE_CLEANUP_ROOT_REPLACED"
    )
