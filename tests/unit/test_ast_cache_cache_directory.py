"""#1376：test_ast_cache_cache_directory 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import os
from types import SimpleNamespace

import pytest

import tests.unit._ast_cache_helpers as _fixtures
import tree_sitter_analyzer.ast_cache as ast_cache_module
from tests.unit._ast_cache_helpers import _python_language, requires_posix_fd
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
def test_cache_constructor_rejects_cache_dir_replacement_during_db_open(
    tmp_path, monkeypatch
):
    real_init = ASTCache._init_db
    cache_dir = tmp_path / ".ast-cache"
    displaced = tmp_path / ".ast-cache-displaced"

    def init_then_replace(cache):
        real_init(cache)
        cache_dir.rename(displaced)
        cache_dir.mkdir()

    monkeypatch.setattr(ASTCache, "_init_db", init_then_replace)
    with pytest.raises(RuntimeError, match="directory changed while opening database"):
        ASTCache(str(tmp_path))


def test_pinned_mirror_invalidation_rejects_unbound_cache_dir(tmp_path):
    import tree_sitter_analyzer.cache.indexer as indexer

    cache = SimpleNamespace(project_root=str(tmp_path), _cache_dir_fd=None)
    with pytest.raises(OSError, match="AST_CACHE_DIRECTORY_UNBOUND"):
        indexer._invalidate_ladybug(cache, root_fd=17)


def test_pinned_mirror_invalidation_skips_unowned_custom_cache():
    import tree_sitter_analyzer.cache.indexer as indexer

    cache = SimpleNamespace(_uses_project_mirror=False, _cache_dir_fd=17)
    assert indexer._invalidate_ladybug(cache, root_fd=19) is False


@requires_posix_fd
def test_force_rebuild_rejects_cache_dir_probe_error_before_clear(
    tmp_path, monkeypatch
):
    import tree_sitter_analyzer.cache.indexer as indexer
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=_python_language,
        materialize=True,
    )
    real_open = indexer.os.open

    def fail_cache_probe(path, flags, *args, **kwargs):
        if path == ".ast-cache" and kwargs.get("dir_fd") is not None:
            raise OSError("probe denied")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(indexer.os, "open", fail_cache_probe)
    try:
        result = cache.index_project(
            force=True, max_files=10, candidate_snapshot=snapshot, workers=0
        )
        persisted = (
            cache.get_conn().execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
        )
    finally:
        cache.close()
        cleanup_index_candidate_snapshot(snapshot)

    assert result["abort_remaining_phases"] is True
    assert persisted == 1


@requires_posix_fd
def test_force_rebuild_rejects_replaced_cache_dir_before_clear(tmp_path):
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=_python_language,
        materialize=True,
    )
    cache_dir = tmp_path / ".ast-cache"
    displaced = tmp_path / ".ast-cache-displaced"
    cache_dir.rename(displaced)
    cache_dir.mkdir()
    replacement_mirror = cache_dir / "knowledge-graph.lbug"
    replacement_mirror.write_text("replacement", encoding="utf-8")

    try:
        result = cache.index_project(
            force=True, max_files=10, candidate_snapshot=snapshot, workers=0
        )
        persisted = (
            cache.get_conn().execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
        )
    finally:
        cache.close()
        cleanup_index_candidate_snapshot(snapshot)

    assert result["abort_remaining_phases"] is True
    assert persisted == 1
    assert replacement_mirror.read_text(encoding="utf-8") == "replacement"


@requires_posix_fd
def test_force_rebuild_cache_dir_swap_keeps_replacement_mirror_isolated(
    tmp_path, monkeypatch
):
    # PR #1253 review 3762869113: 镜像清理遵循已打开数据库的所有者。
    import tree_sitter_analyzer.cache.indexer as indexer
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    cache_dir = tmp_path / ".ast-cache"
    displaced = tmp_path / ".ast-cache-displaced"
    old_mirror = cache_dir / "knowledge-graph.lbug"
    old_mirror.write_text("old mirror", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=_python_language,
        materialize=True,
    )
    replacement_mirror = cache_dir / "knowledge-graph.lbug"
    real_clear = indexer._clear_full_rebuild_rows

    def clear_then_replace_cache(cache_arg, conn):
        real_clear(cache_arg, conn)
        cache_dir.rename(displaced)
        cache_dir.mkdir()
        replacement_mirror.write_text("replacement mirror", encoding="utf-8")

    monkeypatch.setattr(indexer, "_clear_full_rebuild_rows", clear_then_replace_cache)
    try:
        result = cache.index_project(
            force=True, max_files=10, candidate_snapshot=snapshot, workers=0
        )
        observed = (
            result["indexed"],
            cache.get_conn().execute("SELECT COUNT(*) FROM ast_index").fetchone()[0],
            (displaced / "knowledge-graph.lbug").exists(),
            replacement_mirror.read_text(encoding="utf-8"),
            sorted(path.name for path in cache_dir.iterdir()),
        )
    finally:
        cache.close()
        cleanup_index_candidate_snapshot(snapshot)

    assert observed == (1, 1, False, "replacement mirror", ["knowledge-graph.lbug"])


@requires_posix_fd
def test_custom_db_path_does_not_create_project_cache_directory(tmp_path):
    # PR #1253 thread 3763044682: 自定义存储没有项目镜像的操作权限。
    project = tmp_path / "readonly-project"
    project.mkdir()
    external = tmp_path / "external" / "index.db"

    cache = ASTCache(str(project), db_path=str(external))
    try:
        observed = ((project / ".ast-cache").exists(), external.exists())
    finally:
        cache.close()

    assert observed == (False, True)


@requires_posix_fd
def test_cache_constructor_closes_directory_fd_when_fstat_fails(tmp_path, monkeypatch):
    # PR #1253 thread 3763183168: 在捕获身份前取得的 fd 也由当前操作负责。

    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir()
    real_open = os.open
    real_close = os.close
    opened: list[int] = []
    closed: list[int] = []

    def tracked_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if os.fspath(path) == str(cache_dir):
            opened.append(fd)
        return fd

    def fail_tracked_fstat(fd):
        if fd in opened:
            raise OSError("identity unavailable")
        return os.fstat(fd)

    def tracked_close(fd):
        if fd in opened:
            closed.append(fd)
        return real_close(fd)

    monkeypatch.setattr(ast_cache_module.os, "open", tracked_open)
    monkeypatch.setattr(ast_cache_module.os, "fstat", fail_tracked_fstat)
    monkeypatch.setattr(ast_cache_module.os, "close", tracked_close)

    with pytest.raises(OSError, match="identity unavailable"):
        ASTCache(str(tmp_path))

    assert closed == opened


@requires_posix_fd
def test_nonmaterialized_candidate_rejects_replacement_cache_before_write(
    tmp_path,
):
    # PR #1253 thread 3763790630: 实时候选必须认证写入根目录。
    root = tmp_path / "project"
    root.mkdir()
    source = root / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(root))
    cache.index_file(str(source))
    snapshot = build_index_candidate_snapshot(
        str(root),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=_python_language,
    )
    displaced = tmp_path / "displaced"
    root.rename(displaced)
    root.mkdir()
    replacement = root / "replacement.py"
    replacement.write_text("replacement = 1\n", encoding="utf-8")

    try:
        result = cache.index_project(
            max_files=10,
            exclude_patterns=frozenset(),
            candidate_snapshot=snapshot,
            workers=0,
        )
        persisted = (
            cache.get_conn()
            .execute("SELECT file_path FROM ast_index ORDER BY file_path")
            .fetchall()
        )
        replacement_entries = sorted(path.name for path in root.iterdir())
    finally:
        cache.close()

    assert (
        result["abort_remaining_phases"],
        result["files"],
        [row[0] for row in persisted],
        replacement_entries,
    ) == (
        True,
        [{"file": "", "status": "error", "reason": "INDEX_CACHE_HIERARCHY_CHANGED"}],
        ["app.py"],
        ["replacement.py"],
    )


@requires_posix_fd
def test_candidate_cache_hierarchy_rejects_unbound_and_wrong_root(
    tmp_path, monkeypatch
):
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    root_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    info = os.fstat(root_fd)
    cache = SimpleNamespace(_uses_project_mirror=True, _cache_dir_fd=None)
    snapshot = SimpleNamespace(
        root_identity=(os.path.realpath(tmp_path), info.st_dev, info.st_ino)
    )
    try:
        cache._uses_project_mirror = False
        assert (
            materialization.index_candidate_cache_hierarchy_is_current(
                snapshot, cache, root_fd=root_fd
            )
            is True
        )
        cache._uses_project_mirror = True
        assert (
            materialization.index_candidate_cache_hierarchy_is_current(
                snapshot, cache, root_fd=root_fd
            )
            is False
        )
        cache._cache_dir_fd = root_fd
        snapshot.root_identity = (os.path.realpath(tmp_path), -1, -1)
        assert (
            materialization.index_candidate_cache_hierarchy_is_current(
                snapshot, cache, root_fd=root_fd
            )
            is False
        )
    finally:
        os.close(root_fd)


@requires_posix_fd
def test_candidate_cache_hierarchy_owned_root_close_failure_is_bounded(
    tmp_path, monkeypatch
):
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    root_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    info = os.fstat(root_fd)
    cache = SimpleNamespace(_uses_project_mirror=True, _cache_dir_fd=root_fd)
    snapshot = SimpleNamespace(
        root_identity=(os.path.realpath(tmp_path), info.st_dev, info.st_ino)
    )
    monkeypatch.setattr(
        materialization, "open_index_candidate_snapshot_root", lambda _s: root_fd
    )
    monkeypatch.setattr(
        materialization.os,
        "open",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("probe")),
    )
    real_close = materialization.os.close
    monkeypatch.setattr(
        materialization.os, "close", lambda _fd: (_ for _ in ()).throw(OSError("close"))
    )
    assert (
        materialization.index_candidate_cache_hierarchy_is_current(snapshot, cache)
        is False
    )
    monkeypatch.setattr(materialization.os, "close", real_close)
    os.close(root_fd)
