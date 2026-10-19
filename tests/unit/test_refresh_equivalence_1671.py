"""等价门（#1671 / #1673）：刷新后发布的索引内容必须等于同一源码的全新重建。

三种情形：(a) 无变化，(b) 编辑一个文件，(c) 新增并删除文件。项目含跨文件调用
（回填结果参与比较）与一个稳定失败文件。比较使用 ``_index_canonical_dump`` 的
规范化转储，排除项见该模块文档（仅时间戳、写入身份与代理键映射）。
"""

from __future__ import annotations

import os
import shutil
import stat
from types import SimpleNamespace

import pytest

from tests.unit._index_canonical_dump import canonical_dump, dump_differences

_FILES = {
    "pkg/__init__.py": "",
    "pkg/core.py": (
        "class Engine:\n"
        "    def run(self):\n"
        "        return helper()\n\n\n"
        "def helper():\n"
        "    return 1\n"
    ),
    "pkg/api.py": (
        "from pkg.core import Engine, helper\n\n\n"
        "def serve():\n"
        "    return Engine().run() + helper()\n"
    ),
    "app.py": "from pkg.api import serve\n\n\ndef main():\n    return serve()\n",
    "broken.py": "def broken():\n    return 4\n",
}
_REASON = 'Lua grammar not installed — pip install "tree-sitter-analyzer[lua]"'


@pytest.fixture
def root(tmp_path, monkeypatch):
    from tree_sitter_analyzer.core.parser import Parser
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    project = tmp_path / "project"
    for name, text in _FILES.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    original = Parser.parse_code

    def parse_code(self, source_code, language, filename=None, *args, **kwargs):
        if filename is not None and os.path.basename(filename) == "broken.py":
            return SimpleNamespace(success=False, error_message=_REASON)
        return original(self, source_code, language, filename, *args, **kwargs)

    monkeypatch.setattr(Parser, "parse_code", parse_code)
    auto_index_guard.reset()
    yield str(project)
    auto_index_guard.reset()


def _index_project(root):
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(root)
    try:
        cache.index_project(workers=0)
    finally:
        cache.close()


def _sync(root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    scope = make_source_scope_descriptor()
    cache = ASTCache(root)
    try:
        IncrementalSync(cache).sync(
            max_files=scope.certification_max_files,
            exclude_patterns=scope.effective_excludes,
            source_scope=scope,
        )
    finally:
        cache.close()


def _published_dump(root):
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    location = resolve_index_location(root)
    assert location.published is True
    return canonical_dump(location.path)


def _wipe_index(root):
    cache = os.path.join(root, ".ast-cache")
    # 已封存的版本文件带只读位（RFC-0032 slice 3），删除前先恢复写权限。
    for directory, _dirs, files in os.walk(cache):
        for name in files:
            os.chmod(os.path.join(directory, name), stat.S_IWRITE | stat.S_IREAD)
    shutil.rmtree(cache)


def _write(root, name, text):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))


def _change(root, scenario):
    if scenario == "edit":
        _write(
            root,
            "pkg/core.py",
            _FILES["pkg/core.py"].replace("return 1", "return 2")
            + "\n\ndef extra():\n    return helper()\n",
        )
    elif scenario == "add_delete":
        _write(
            root,
            "pkg/extra.py",
            "from pkg.core import helper\n\n\ndef more():\n    return helper()\n",
        )
        os.remove(os.path.join(root, "pkg/api.py"))


# slow_ok：每个用例做四次真实刷新（含一次全新重建）并转储两份完整索引。
@pytest.mark.slow_ok
@pytest.mark.parametrize("route", ["index_project", "sync"])
@pytest.mark.parametrize("scenario", ["noop", "edit", "add_delete"])
def test_refreshed_index_equals_a_fresh_rebuild(root, route, scenario) -> None:
    refresh = _index_project if route == "index_project" else _sync
    refresh(root)
    refresh(root)  # 第二次：父版本带稳定失败记录，零变化判定可用
    _change(root, scenario)
    refresh(root)
    refreshed = _published_dump(root)

    _wipe_index(root)
    refresh(root)
    rebuilt = _published_dump(root)

    assert dump_differences(refreshed, rebuilt) == {}
    assert refreshed["ast_index"]  # 非空：比较的不是两个空库
