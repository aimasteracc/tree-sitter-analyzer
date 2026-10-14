"""默认定位符首次写入前引导版本、旧库采纳与只读不引导的契约。

RFC-0032 slice 1（#1554）：rfcs/evidence/0032-feasibility E1（2026-10-13）
测得默认定位符在首次发布前仍原地写旧 ``.ast-cache/index.db``，旧候选重放会删除
更新的行（b.py 被删、``ast_call_graph_state`` built→unbuilt、进程 exit 0）。
"""

import os
import sqlite3
from pathlib import Path

import pytest

_A = "def alpha():\n    return 1\n"
_A_CHANGED = "def alpha():\n    return 2\n"
_B = "def beta():\n    return alpha()\n"
_C = "def gamma():\n    return 3\n"
_ROUTES = ["ensure_indexed", "index_project", "index_file", "invalidate", "sync"]


@pytest.fixture
def root(tmp_path):
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text(_A, encoding="utf-8")
    auto_index_guard.reset()
    yield str(project)
    auto_index_guard.reset()


def _scope():
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    return make_source_scope_descriptor()


def _capture(root):
    from tree_sitter_analyzer.constants import EXCLUDE_DIRS
    from tree_sitter_analyzer.indexing_snapshot import (
        build_index_candidate_snapshot,
        walk_index_candidate_entries,
    )
    from tree_sitter_analyzer.project_graph import _language_from_ext

    scope = _scope()
    return build_index_candidate_snapshot(
        root,
        max_files=scope.certification_max_files,
        exclude_patterns=scope.effective_excludes,
        walk_fn=lambda path: walk_index_candidate_entries(
            path, excluded_dir_names=frozenset(EXCLUDE_DIRS)
        ),
        language_fn=_language_from_ext,
    )


def _sync(root, candidate=None):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync

    scope = _scope()
    cache = ASTCache(root)
    try:
        return IncrementalSync(cache).sync(
            max_files=scope.certification_max_files,
            exclude_patterns=scope.effective_excludes,
            candidate_snapshot=candidate,
            source_scope=scope,
        )
    finally:
        cache.close()


def _write(root, route, rel_path):
    """经默认定位符的真实公共写入口执行一次变更。"""
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    if route == "ensure_indexed":
        auto_index_guard.reset()
        auto_index_guard.ensure_indexed(root).close()
        return
    if route == "sync":
        assert _sync(root).errors == 0
        return
    cache = ASTCache(root)
    try:
        if route == "index_project":
            assert cache.index_project()["errors"] == 0
        elif route == "index_file":
            assert cache.index_file(os.path.join(root, rel_path))["status"] == "indexed"
        else:
            cache.invalidate(os.path.join(root, rel_path))
    finally:
        cache.close()


def _dump(root):
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path

    connection = sqlite3.connect(
        resolve_index_path(root).as_uri() + "?mode=ro", uri=True
    )
    try:
        return tuple(connection.iterdump())
    finally:
        connection.close()


def _indexed_files(root):
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path

    connection = sqlite3.connect(
        resolve_index_path(root).as_uri() + "?mode=ro", uri=True
    )
    try:
        rows = connection.execute("SELECT file_path FROM ast_index ORDER BY 1")
        return [row[0] for row in rows]
    finally:
        connection.close()


def _legacy(root):
    return Path(root) / ".ast-cache" / "index.db"


def _published(root):
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    return resolve_index_location(root).published


@pytest.mark.parametrize("route", _ROUTES)
def test_first_mutation_publishes_generation_without_legacy_database(root, route):
    # #1554 / E1（2026-10-13）：首次写入必须先引导版本，不能原地创建旧库。
    _write(root, route, "a.py")
    assert (_published(root), _legacy(root).exists()) == (True, False)


def test_ensure_indexed_cache_reads_published_generation(root):
    # #1554 / E5 ensure_indexed_fresh.published_selector=false（2026-10-13）。
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path
    from tree_sitter_analyzer.mcp.utils.auto_index_guard import ensure_indexed

    cache = ensure_indexed(root)
    try:
        assert (
            cache.db_path == str(resolve_index_path(root)),
            cache.db_path == str(_legacy(root)),
            [row["name"] for row in cache.get_functions()],
        ) == (True, False, ["alpha"])
    finally:
        cache.close()


def test_read_only_calls_do_not_bootstrap_fresh_project(root):
    # RFC-0032 Revision 1：只读调用不得引导、修复或删除存储（#1554）。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.mcp.utils.auto_index_guard import ensure_indexed

    assert ensure_indexed(root, auto_build=False) is None
    cache = ASTCache(root)
    try:
        assert (cache.get_stats()["total_files"], cache.get_functions()) == (0, [])
    finally:
        cache.close()
    storage = Path(root) / ".ast-cache" / "index-generations"
    assert (_legacy(root).exists(), storage.exists()) == (False, False)


@pytest.mark.parametrize("capture_first", [False, True], ids=["indexed", "fresh"])
def test_obsolete_replay_without_prior_publication_is_superseded(root, capture_first):
    # #1554 / E1（2026-10-13）：未发布默认库上旧候选重放删除 b.py 且 exit 0。
    from tree_sitter_analyzer.cache.generation_store import Superseded

    old = _capture(root) if capture_first else None
    assert _sync(root).errors == 0
    old = old or _capture(root)
    (Path(root) / "b.py").write_text(_B, encoding="utf-8")
    assert _sync(root).errors == 0
    before = _dump(root)
    with pytest.raises(Superseded, match="INDEX_GENERATION_SUPERSEDED"):
        _sync(root, old)
    assert (_dump(root), _indexed_files(root)) == (before, ["a.py", "b.py"])


def test_identical_bytes_replay_without_prior_publication_is_superseded(root):
    # #1554 / E1 identical-bytes ABA（2026-10-13）：内容回到原字节也不能复用旧候选。
    from tree_sitter_analyzer.cache.generation_store import Superseded

    source = Path(root) / "a.py"
    assert _sync(root).errors == 0
    original = os.stat(source)
    old = _capture(root)
    source.write_text(_A_CHANGED, encoding="utf-8")
    assert _sync(root).errors == 0
    source.write_text(_A, encoding="utf-8")
    os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
    assert _sync(root).errors == 0
    before = _dump(root)
    with pytest.raises(Superseded, match="INDEX_GENERATION_SUPERSEDED"):
        _sync(root, old)
    assert _dump(root) == before


@pytest.mark.parametrize("route", _ROUTES)
def test_obsolete_replay_after_route_write_is_superseded(root, route):
    # #1554 / E1（2026-10-13）：每条默认写入口完成的更新都不能被旧候选回滚。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache.generation_store import Superseded

    _write(root, route, "a.py")
    old = _capture(root)
    (Path(root) / "b.py").write_text(_B, encoding="utf-8")
    # ensure_indexed 对已认证缓存只走快路径，不会再写；更新改由同步完成。
    _write(root, "sync" if route == "ensure_indexed" else route, "b.py")
    before = _dump(root)
    cache = ASTCache(root)
    try:
        with pytest.raises(Superseded, match="INDEX_GENERATION_SUPERSEDED"):
            if route == "index_project":
                cache.index_project(candidate_snapshot=old, source_scope=_scope())
            else:
                _sync(root, old)
    finally:
        cache.close()
    assert (_dump(root), _legacy(root).exists()) == (before, False)


def _seed_legacy(root):
    """模拟 v2.2.0 及之前首次发布前原地写入留下的旧 ``.ast-cache/index.db``。"""
    from tests.unit._ast_cache_helpers import engine_cache, write_legacy_index

    cache = engine_cache(root)
    try:
        assert cache.index_project()["errors"] == 0
        write_legacy_index(cache)
    finally:
        cache.close()


def test_read_only_calls_do_not_migrate_legacy_database(root):
    # RFC-0032 Revision 1：只读调用不得迁移旧库（#1554）。
    from tree_sitter_analyzer.ast_cache import ASTCache

    _seed_legacy(root)
    cache = ASTCache(root)
    try:
        names = [row["name"] for row in cache.get_functions()]
    finally:
        cache.close()
    assert (names, _published(root)) == (["alpha"], False)


def _legacy_dump(root):
    connection = sqlite3.connect(_legacy(root).as_uri() + "?mode=ro", uri=True)
    try:
        return tuple(connection.iterdump())
    finally:
        connection.close()


def test_first_mutation_adopts_legacy_database_without_writing_it(root):
    # #1554：旧库整库复制进首个版本后再写，旧库逻辑内容保持不变。
    from tree_sitter_analyzer.ast_cache import ASTCache

    _seed_legacy(root)
    (Path(root) / "c.py").write_text(_C, encoding="utf-8")
    cache = ASTCache(root)
    try:
        legacy_before = _legacy_dump(root)
        assert cache.index_file(os.path.join(root, "c.py"))["status"] == "indexed"
        names = sorted(row["name"] for row in cache.get_functions())
    finally:
        cache.close()
    assert (names, _published(root), _legacy_dump(root) == legacy_before) == (
        ["alpha", "gamma"],
        True,
        True,
    )


def test_derived_mutation_on_legacy_database_writes_published_copy(root):
    # #1554：约束持久化等派生写入在首次发布前也不得原地改旧库。
    from tree_sitter_analyzer.cache.generation_indexing import mutate_index_path
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path

    _seed_legacy(root)
    written = []
    mutate_index_path(root, _legacy(root), written.append)
    assert (written, _published(root)) == ([resolve_index_path(root)], True)


def test_write_in_read_scope_is_visible_without_creating_legacy_database(root):
    # #1554：MCP 调用的读绑定若停在旧定位符，首写后会打开并新建旧 index.db。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache.generation_reads import generation_read_scope

    with generation_read_scope():
        cache = ASTCache(root)
        try:
            assert cache.index_project()["errors"] == 0
            total = cache.get_stats()["total_files"]
        finally:
            cache.close()
    assert (total, _legacy(root).exists()) == (1, False)


def test_first_publication_keeps_files_indexed_beside_per_file_error(root, monkeypatch):
    # #1554：旧路由遇到单文件失败（如缺少可选语法）仍原地保留其余文件；
    # 首次发布无父版本可保护，不能因此整体丢弃，否则自动索引永远为空。
    from tree_sitter_analyzer.ast_cache import ASTCache

    (Path(root) / "b.py").write_text(_B, encoding="utf-8")
    original = ASTCache.index_file

    def fail_b(self, file_path, *args, **kwargs):
        if file_path.endswith("b.py"):
            return {
                "file": "b.py",
                "status": "error",
                "reason": "grammar not installed",
            }
        return original(self, file_path, *args, **kwargs)

    monkeypatch.setattr(ASTCache, "index_file", fail_b)
    errors = _sync(root).errors
    assert (errors, _published(root), _indexed_files(root)) == (1, True, ["a.py"])


def test_raw_write_on_never_indexed_cache_is_rejected(root):
    # #1554：进程内空库若可写，原始连接写入会静默丢失；须同已发布版本一样拒绝。
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(root)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            cache.get_conn().execute("DELETE FROM ast_index")
    finally:
        cache.close()
