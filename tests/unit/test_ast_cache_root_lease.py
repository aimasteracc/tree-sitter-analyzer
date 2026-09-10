"""#1376：test_ast_cache_root_lease 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import errno
import os
from dataclasses import replace

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tests.unit._ast_cache_helpers import _python_language, _snapshot, requires_posix_fd
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
)
from tree_sitter_analyzer.indexing_snapshot import (
    build_index_candidate_snapshot,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


@requires_posix_fd
def test_force_rebuild_rejects_replaced_root_before_destructive_clear(
    tmp_path, monkeypatch
):
    # PR #1253 thread 3761703249: 来自已替换根目录的冻结文件不能
    # 授权清空原路径现在指向的缓存。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    root = tmp_path / "project"
    root.mkdir()
    source = root / "old.py"
    source.write_text("old = 1\n", encoding="utf-8")
    cache = ASTCache(str(root))
    cache.index_file(str(source))
    snapshot = build_index_candidate_snapshot(
        str(root),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=_python_language,
        materialize=True,
    )
    displaced = tmp_path / "displaced"
    root.rename(displaced)
    root.mkdir()
    (root / "replacement.py").write_text("replacement = 1\n", encoding="utf-8")
    # 在最初的实体化判定之后模拟路径替换，
    # 独立的清空前根目录复查仍必须拒绝它。
    monkeypatch.setattr(
        materialization, "index_candidate_snapshot_is_materialized", lambda _item: True
    )
    try:
        result = cache.index_project(
            force=True, max_files=10, candidate_snapshot=snapshot, workers=0
        )
        persisted = (
            cache.get_conn()
            .execute("SELECT file_path FROM ast_index ORDER BY file_path")
            .fetchall()
        )
    finally:
        cleanup_index_candidate_snapshot(snapshot)
        cache.close()

    assert (result["abort_remaining_phases"], [row[0] for row in persisted]) == (
        True,
        ["old.py"],
    )


@requires_posix_fd
def test_discard_root_lease_dispatch_is_exact(monkeypatch):
    import tree_sitter_analyzer.cache.indexer as indexer

    calls = []
    monkeypatch.setattr(
        indexer,
        "_discard_snapshot_generation",
        lambda *_args, **kwargs: calls.append(kwargs),
    )

    indexer._discard_with_root_lease(object(), object(), "a.py", None)
    indexer._discard_with_root_lease(object(), object(), "b.py", 17)

    assert calls == [{}, {"root_fd": 17}]


@pytest.mark.skipif(os.name != "posix", reason="GH-1253: POSIX root lease")
def test_force_rebuild_root_swap_keeps_replacement_mirror_isolated(
    tmp_path, monkeypatch
):
    # PR #1253 thread 3761703249: 破坏性清空后的清理必须仍然
    # 绑定到授权冻结 force rebuild 的根目录。
    import tree_sitter_analyzer.cache.indexer as indexer
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    root = tmp_path / "project"
    root.mkdir()
    source = root / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(root))
    cache.index_file(str(source))
    old_mirror = root / ".ast-cache" / "knowledge-graph.lbug"
    old_mirror.write_text("old mirror", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(root),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=_python_language,
        materialize=True,
    )
    displaced = tmp_path / "displaced"
    replacement_mirror = root / ".ast-cache" / "knowledge-graph.lbug"
    real_clear = indexer._clear_full_rebuild_rows

    def clear_then_replace_root(cache_arg, conn):
        real_clear(cache_arg, conn)
        root.rename(displaced)
        root.mkdir()
        replacement_mirror.parent.mkdir()
        replacement_mirror.write_text("replacement mirror", encoding="utf-8")

    monkeypatch.setattr(indexer, "_clear_full_rebuild_rows", clear_then_replace_root)
    try:
        result = cache.index_project(
            force=True, max_files=10, candidate_snapshot=snapshot, workers=0
        )
        observed = (
            result["indexed"],
            cache.get_conn().execute("SELECT COUNT(*) FROM ast_index").fetchone()[0],
            (displaced / ".ast-cache" / "knowledge-graph.lbug").exists(),
            replacement_mirror.read_text(encoding="utf-8"),
        )
    finally:
        cache.close()
        cleanup_index_candidate_snapshot(snapshot)

    assert observed == (1, 1, False, "replacement mirror")


@requires_posix_fd
def test_snapshot_root_identity_mismatch_closes_rejected_fd(tmp_path, monkeypatch):
    # PR #1253 thread 3761703249: 根租约不匹配时必须失败关闭，且不能
    # 遗留为验证身份而打开的描述符。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    snapshot = _snapshot(tmp_path, source)
    root_info = tmp_path.stat()
    mismatched = replace(
        snapshot,
        root_identity=(snapshot.project_root, root_info.st_dev, root_info.st_ino + 1),
    )
    real_open = materialization.os.open
    opened = []

    def record_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(materialization.os, "open", record_open)
    lease = materialization.open_index_candidate_snapshot_root(mismatched)

    assert (lease, len(opened)) == (None, 1)
    with pytest.raises(OSError) as exc_info:
        os.fstat(opened[0])
    assert exc_info.value.errno == errno.EBADF

    real_fstat = os.fstat
    opened.clear()

    def fail_fstat(_fd):
        raise OSError(errno.EIO, "injected fstat failure")

    monkeypatch.setattr(materialization.os, "fstat", fail_fstat)
    lease = materialization.open_index_candidate_snapshot_root(snapshot)

    assert (lease, len(opened)) == (None, 1)
    with pytest.raises(OSError) as exc_info:
        real_fstat(opened[0])
    assert exc_info.value.errno == errno.EBADF

    real_close = os.close

    def fail_close(_fd):
        raise OSError(errno.EIO, "injected close failure")

    opened.clear()
    monkeypatch.setattr(materialization.os, "close", fail_close)
    lease = materialization.open_index_candidate_snapshot_root(snapshot)
    assert (lease, len(opened), real_fstat(opened[0]).st_ino) == (
        None,
        1,
        root_info.st_ino,
    )
    real_close(opened[0])

    opened.clear()
    monkeypatch.setattr(materialization.os, "fstat", real_fstat)
    lease = materialization.open_index_candidate_snapshot_root(mismatched)
    assert (lease, len(opened), real_fstat(opened[0]).st_ino) == (
        None,
        1,
        root_info.st_ino,
    )
    real_close(opened[0])

    opened.clear()
    assert materialization.index_candidate_snapshot_root_is_current(snapshot) is False
    assert len(opened) == 1
    real_close(opened[0])


@requires_posix_fd
def test_root_lease_close_error_still_runs_owned_cleanup(tmp_path, monkeypatch):
    # PR #1253 P2: 关闭失败不能遗留 build marker 或冻结树。
    import tree_sitter_analyzer.cache.indexer as indexer
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization
    from tree_sitter_analyzer.cache.build_state import build_in_progress

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    created_roots = []
    root_fds = set()
    armed = False
    real_mkdtemp = materialization.tempfile.mkdtemp
    real_open_root = materialization.open_index_candidate_snapshot_root
    real_close = os.close
    real_clear = indexer._clear_full_rebuild_rows

    def record_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created_roots.append(path)
        return path

    def record_root_fd(snapshot):
        fd = real_open_root(snapshot)
        if fd is not None:
            root_fds.add(fd)
        return fd

    def clear_and_arm(cache_arg, conn):
        nonlocal armed
        real_clear(cache_arg, conn)
        armed = True

    def fail_armed_root_close(fd):
        if armed and fd in root_fds:
            root_fds.remove(fd)
            real_close(fd)
            raise OSError(errno.EIO, "injected root lease close failure")
        real_close(fd)

    with monkeypatch.context() as patcher:
        patcher.setattr(materialization.tempfile, "mkdtemp", record_mkdtemp)
        patcher.setattr(
            materialization, "open_index_candidate_snapshot_root", record_root_fd
        )
        patcher.setattr(indexer, "_clear_full_rebuild_rows", clear_and_arm)
        patcher.setattr(indexer.os, "close", fail_armed_root_close)
        result = cache.index_project(force=True, max_files=10, workers=0)

    try:
        observed = (
            result["indexed"],
            build_in_progress(cache.get_conn()),
            [os.path.exists(path) for path in created_roots],
        )
    finally:
        cache.close()

    assert observed == (1, False, [False])


@requires_posix_fd
def test_custom_db_path_force_rebuild_uses_root_lease_without_mirror(tmp_path):
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    project = tmp_path / "project"
    project.mkdir()
    source = project / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    external = tmp_path / "external" / "index.db"
    cache = ASTCache(str(project), db_path=str(external))
    snapshot = build_index_candidate_snapshot(
        str(project),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=_python_language,
        materialize=True,
    )
    try:
        result = cache.index_project(
            max_files=10, force=True, workers=0, candidate_snapshot=snapshot
        )
        count = cache.get_conn().execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
    finally:
        cache.close()
        cleanup_index_candidate_snapshot(snapshot)
    assert (result["indexed"], result["errors"], count) == (1, 0, 1)
    assert (project / ".ast-cache").exists() is False


@requires_posix_fd
def test_direct_force_rebuild_canonicalizes_symlink_project_root_once(tmp_path):
    # PR #1253 thread 3763401189: 直接 ASTCache force 调用必须接受根路径别名。
    physical_root = tmp_path / "physical"
    logical_root = tmp_path / "logical"
    physical_root.mkdir()
    logical_root.symlink_to(physical_root, target_is_directory=True)
    source = physical_root / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")

    cache = ASTCache(str(logical_root))
    try:
        result = cache.index_project(force=True, max_files=10, workers=0)
        observed = (
            cache.project_root,
            result["indexed"],
            result["errors"],
            cache.lookup(str(source)) is not None,
        )
    finally:
        cache.close()

    assert observed == (os.path.realpath(logical_root), 1, 0, True)
