"""#1673 等价门（仓库实测发现）：删除文件后的刷新必须等于全新重建。

本仓库的编辑链（索引 → 同步 → 索引）在删除文件后留下两类与全新重建不同的行：

* Java 枚举方法的 ``contains`` 边以占位类节点（``class:Operation``）为源，其
  ``file_path`` 列为空，按文件删除边时漏掉，文件删除后仍留在索引中；
* 撤销“受该文件符号影响”的调用解析时，按名称匹配的分支在该文件的符号行已被
  删除之后才执行，什么也匹配不到。
"""

from __future__ import annotations

import os
import shutil
import stat

import pytest

from tests.unit._index_canonical_dump import canonical_dump, dump_differences

_JAVA = """\
public class Shapes {
    public int area() { return 1; }
}

enum Operation {
    ADD {
        public int apply(int x, int y) { return x + y; }
    },
    SUBTRACT {
        public int apply(int x, int y) { return x - y; }
    }
}
"""
_PY = {
    "app.py": "from lib import helper\n\n\ndef main():\n    return helper()\n",
    "lib.py": "def helper():\n    return 1\n",
    "other.py": "def helper():\n    return 2\n\n\ndef unused():\n    return helper()\n",
    "user.py": "def run(item):\n    return item.create()\n",
    "first.py": "class First:\n    def create(self):\n        return 1\n",
    "second.py": "class Second:\n    def create(self):\n        return 2\n",
}


@pytest.fixture
def root(tmp_path):
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    project = tmp_path / "project"
    project.mkdir()
    (project / "Ops.java").write_text(_JAVA, encoding="utf-8")
    for name, text in _PY.items():
        (project / name).write_text(text, encoding="utf-8")
    auto_index_guard.reset()
    yield project
    auto_index_guard.reset()


def _refresh(root):
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(str(root))
    try:
        cache.index_project(workers=0)
    finally:
        cache.close()


def _dump(root):
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    return canonical_dump(resolve_index_location(str(root)).path)


def _wipe(root):
    cache = os.path.join(root, ".ast-cache")
    for directory, _dirs, files in os.walk(cache):
        for name in files:
            os.chmod(os.path.join(directory, name), stat.S_IWRITE | stat.S_IREAD)
    shutil.rmtree(cache)


# slow_ok：两次刷新、一次全新重建并转储两份完整索引。
@pytest.mark.slow_ok
@pytest.mark.parametrize("removed", ["Ops.java", "other.py", "second.py"])
def test_refresh_after_a_removal_equals_a_fresh_rebuild(root, removed) -> None:
    _refresh(root)
    os.remove(root / removed)
    _refresh(root)
    refreshed = _dump(root)

    _wipe(root)
    _refresh(root)

    assert dump_differences(refreshed, _dump(root)) == {}


# slow_ok：三次刷新（含同步路由）、一次全新重建并转储两份完整索引。
@pytest.mark.slow_ok
def test_sync_scope_then_index_scope_equals_a_fresh_rebuild(root) -> None:
    # 混合路由链：项目索引 → ``ast_cache mode=sync`` → 项目索引。两条路由共用
    # 默认范围（#1697，``tests/golden/corpus_*`` 不入索引），结果必须与全新重建相同。
    from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

    corpus = root / "tests" / "golden"
    corpus.mkdir(parents=True)
    (corpus / "corpus_extra.py").write_text(
        "class Extra:\n    def create(self):\n        return 3\n\n\n"
        "def helper():\n    return 4\n",
        encoding="utf-8",
    )
    _refresh(root)
    import asyncio

    asyncio.run(ASTCacheTool(str(root)).execute({"mode": "sync"}))
    _refresh(root)
    refreshed = _dump(root)

    _wipe(root)
    _refresh(root)

    assert dump_differences(refreshed, _dump(root)) == {}


def test_discarding_a_file_resets_calls_bound_by_its_names(tmp_path) -> None:
    # 删除一个声明了 ``create`` 的文件会改变 ``create`` 的唯一性，所以调用名为
    # ``create`` 的边（即使解析到别的文件）必须撤销并在回填中重新解析。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache.write import discard_file_rows

    (tmp_path / "user.py").write_text(
        "def run():\n    return create()\n", encoding="utf-8"
    )
    (tmp_path / "a.py").write_text("def create():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def create():\n    return 2\n", encoding="utf-8")
    database = tmp_path / "custom" / "index.db"
    database.parent.mkdir()
    cache = ASTCache(str(tmp_path), str(database))
    try:
        cache.index_project(workers=0)
        conn = cache._get_conn()
        conn.execute(
            "UPDATE edges SET callee_resolution = 'project', "
            "callee_resolved_file = 'a.py' "
            "WHERE kind = 'calls' AND file_path = 'user.py' AND callee_name = 'create'"
        )
        conn.commit()
        discard_file_rows(conn, "b.py", cache.fts5_available)
        conn.commit()
        row = conn.execute(
            "SELECT callee_resolution, callee_resolved_file FROM edges "
            "WHERE kind = 'calls' AND file_path = 'user.py' AND callee_name = 'create'"
        ).fetchone()
    finally:
        cache.close()

    assert tuple(row) == ("unknown", "")
