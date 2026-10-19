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
    # ``ast_cache mode=sync`` 不带默认排除模式，会把 ``tests/golden/corpus_*``
    # 一并索引；其后的项目索引刷新按默认范围清除它们，结果必须与全新重建相同。
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
