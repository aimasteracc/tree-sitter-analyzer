"""#1697：同一份源码与配置下，``ast_cache mode=sync`` 与索引路由的索引必须相同。

此前同步路由不带默认排除模式（``tests/golden/corpus_*``），会把语料文件一并
索引；它还按单文件路径为重新索引的文件排入 ``ast_symbol_activation`` 队列行，
而项目索引默认（``TSA_INDEX_ACTIVATION`` 未开启）只清除这些行。两条路由因此
对同一份源码给出不同的索引。现在两者共用 ``index_source_scope`` 的默认范围与
项目索引的 activation 策略，规范化转储逐表相同（含清单记录的范围描述）。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import stat
from pathlib import Path

import pytest

from tests.unit._index_canonical_dump import canonical_dump, dump_differences

_CORPUS = "tests/golden/corpus_extra.py"
_SOURCES = {
    "app.py": "from lib import helper\n\n\ndef main():\n    return helper()\n",
    "lib.py": "def helper():\n    return 1\n",
    "user.py": "class User:\n    def create(self):\n        return main()\n",
    _CORPUS: "class Extra:\n    def create(self):\n        return 3\n",
}


@pytest.fixture
def root(tmp_path, monkeypatch):
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    # 默认策略：项目索引不计算 activation（两条路由都应只清除队列行）。
    monkeypatch.delenv("TSA_INDEX_ACTIVATION", raising=False)
    project = tmp_path / "project"
    for rel, text in _SOURCES.items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    auto_index_guard.reset()
    yield project
    auto_index_guard.reset()


def _index_route(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

    result = asyncio.run(ASTCacheTool(str(root)).execute({"mode": "index"}))
    assert result.get("success") is not False, result


def _sync_route(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

    result = asyncio.run(ASTCacheTool(str(root)).execute({"mode": "sync"}))
    assert result.get("success") is not False, result


def _database(root: Path) -> str:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    return str(resolve_index_location(str(root)).path)


def _indexed_paths(root: Path) -> set[str]:
    import sqlite3

    conn = sqlite3.connect(f"file:{_database(root)}?mode=ro", uri=True)
    try:
        return {row[0] for row in conn.execute("SELECT file_path FROM ast_index")}
    finally:
        conn.close()


def _wipe(root: Path) -> None:
    cache = root / ".ast-cache"
    for directory, _dirs, files in os.walk(cache):
        for name in files:
            os.chmod(os.path.join(directory, name), stat.S_IWRITE | stat.S_IREAD)
    shutil.rmtree(cache)


# 两条链各自写入改动；固定 mtime，使 ``ast_index.mtime_ns`` 可逐行比较。
_FIXED_MTIME_NS = 1_700_000_000 * 1_000_000_000


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    os.utime(path, ns=(_FIXED_MTIME_NS, _FIXED_MTIME_NS))


def _edit(root: Path) -> None:
    _write(
        root / "lib.py",
        "def helper():\n    return 2\n\n\ndef extra():\n    return helper()\n",
    )


def _add_delete(root: Path) -> None:
    _write(
        root / "added.py",
        "from lib import helper\n\n\ndef added():\n    return helper()\n",
    )
    os.remove(root / "user.py")


_CHANGES = {"none": lambda _root: None, "edit": _edit, "add_delete": _add_delete}


# slow_ok：每条路由各建一次索引并转储。
@pytest.mark.slow_ok
def test_sync_from_empty_excludes_default_corpus_like_the_index_route(root) -> None:
    _index_route(root)
    indexed = _indexed_paths(root)
    _wipe(root)

    _sync_route(root)
    synced = _indexed_paths(root)

    assert _CORPUS not in indexed
    assert _CORPUS not in synced
    assert synced == indexed


# slow_ok：每个场景两条链（索引后改动，再分别经同步 / 索引刷新），各转储一次。
@pytest.mark.slow_ok
@pytest.mark.parametrize("change", sorted(_CHANGES))
def test_sync_refresh_dump_equals_index_refresh_dump(root, change) -> None:
    backup = root.parent / "pristine"
    shutil.copytree(root, backup)

    _index_route(root)
    _CHANGES[change](root)
    _sync_route(root)
    via_sync = canonical_dump(_database(root))
    _wipe(root)

    shutil.rmtree(root)
    shutil.copytree(backup, root)
    _index_route(root)
    _CHANGES[change](root)
    _index_route(root)
    via_index = canonical_dump(_database(root))

    assert dump_differences(via_sync, via_index) == {}
    assert via_sync["ast_symbol_activation"] == []


# slow_ok：旧行为建库（不带默认排除）后同步一次并转储。
@pytest.mark.slow_ok
def test_sync_prunes_excluded_rows_left_by_an_older_index(root) -> None:
    from tree_sitter_analyzer.ast_cache import ASTCache

    # 旧代码的同步路由不带默认排除：库里留有语料文件的行。
    cache = ASTCache(str(root))
    try:
        cache.index_project(workers=0, exclude_patterns=frozenset())
    finally:
        cache.close()
    assert _CORPUS in _indexed_paths(root)

    _sync_route(root)
    via_sync = canonical_dump(_database(root))
    _wipe(root)
    _index_route(root)

    assert _CORPUS not in {row[0] for row in via_sync["ast_index"]}
    assert dump_differences(via_sync, canonical_dump(_database(root))) == {}


def test_in_place_sync_prunes_default_excluded_rows(root, tmp_path) -> None:
    # 自定义 db_path 的原地同步（无候选快照）同样按默认范围删除旧的语料行，
    # 被排除的文件也不算作“在场”，否则完整性检查永远不成立。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync

    database = tmp_path / "custom" / "index.db"
    database.parent.mkdir()
    cache = ASTCache(str(root), str(database))
    try:
        cache.index_project(workers=0, exclude_patterns=frozenset())
        conn = cache.get_conn()
        before = {r[0] for r in conn.execute("SELECT file_path FROM ast_index")}
        result = IncrementalSync(cache).sync(max_files=100)
        after = {r[0] for r in conn.execute("SELECT file_path FROM ast_index")}
    finally:
        cache.close()

    assert _CORPUS in before
    assert after == before - {_CORPUS}
    assert result.deleted_files == 1
    assert result.errors == 0


def test_default_scope_is_the_one_shared_source() -> None:
    from tree_sitter_analyzer.cache.indexer import _DEFAULT_EXCLUDE_PATTERNS
    from tree_sitter_analyzer.index_source_scope import (
        default_exclude_patterns,
        make_source_scope_descriptor,
    )
    from tree_sitter_analyzer.mcp.tools.full_index_tool import (
        _resolve_exclude_patterns,
    )

    assert _DEFAULT_EXCLUDE_PATTERNS is default_exclude_patterns()
    assert (
        _resolve_exclude_patterns([], False)
        == make_source_scope_descriptor().effective_excludes
        == default_exclude_patterns()
    )
