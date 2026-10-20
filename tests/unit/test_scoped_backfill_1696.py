"""#1696：按依赖界定的回填——1 个文件的刷新只重新解析受影响的边，结果等于全新重建。

每种编辑都覆盖一类解析输入：函数体、签名、增删方法（同名候选与 MRO 最近定义）、
基类变化（MRO）、改名导入（#1670）与返回注解（RFC-0038 工厂）。等价门用
``_index_canonical_dump`` 的规范化转储比较刷新后的索引与同一源码的全新重建，并要求
这次刷新确实走了范围回填。
"""

from __future__ import annotations

import os
import shutil
import stat

import pytest

from tests.unit._index_canonical_dump import canonical_dump, dump_differences

_FILES = {
    "pkg/__init__.py": "",
    "pkg/base.py": (
        "class Base:\n"
        "    def shared(self):\n"
        "        return 0\n\n"
        "    def fmt(self):\n"
        "        return 0\n\n\n"
        "class Mixin:\n"
        "    def fmt(self):\n"
        "        return 1\n\n\n"
        "class Store:\n"
        "    def publish(self):\n"
        "        return 1\n\n\n"
        "def make():\n"
        "    return Store()\n\n\n"
        "def factory() -> Store:\n"
        "    return Store()\n"
    ),
    "pkg/sub.py": (
        "from .base import Base, Mixin\n\n\n"
        "class Sub(Mixin, Base):\n"
        "    def run(self):\n"
        "        return self.shared() + super().fmt()\n"
    ),
    "pkg/hub.py": "from .base import make as _make\nfrom .base import factory\n",
    "app.py": (
        "from pkg.base import factory\n"
        "from pkg.hub import _make\n"
        "from pkg.sub import Sub\n\n"
        "SINGLE = Sub()\n\n\n"
        "def go():\n"
        "    s = factory()\n"
        "    s.publish()\n"
        "    SINGLE.fmt()\n"
        "    x = Sub()\n"
        "    x.shared()\n"
        "    return _make()\n\n\n"
        "def items(xs):\n"
        "    return xs.append(1)\n"
    ),
    "other.py": "def unrelated():\n    return 7\n",
    # 传递子类、模块别名与星号导入：依赖经它们传播。
    "pkg/deep.py": (
        "from .sub import Sub\n\n\n"
        "class Deep(Sub):\n"
        "    def go(self):\n"
        "        return self.fmt() + self.shared()\n\n\n"
        "def build() -> Deep:\n"
        "    return Deep()\n"
    ),
    "star.py": "from pkg.base import *\n\n\ndef s():\n    return make()\n",
    "modalias.py": (
        "import pkg.base as pb\n"
        "from pkg.deep import build\n\n\n"
        "def m():\n"
        "    d = build()\n"
        "    d.shared()\n"
        "    s = pb.factory()\n"
        "    s.publish()\n"
        "    return pb.make()\n"
    ),
    # 经模块导入继承：只能通过子类链（继承边）找到它。
    "pkg/deeper.py": (
        "from . import deep\n\n\n"
        "class Deeper(deep.Deep):\n"
        "    def z(self):\n"
        "        return self.fmt()\n"
    ),
}

#: 编辑名 -> (文件, 旧文本, 新文本)
_EDITS = {
    "body_only": (
        "pkg/base.py",
        "        return 0\n\n    def fmt",
        "        return 5\n\n    def fmt",
    ),
    "signature": ("pkg/base.py", "def shared(self):", "def shared(self, extra=None):"),
    "add_method": (
        "pkg/base.py",
        "class Mixin:\n",
        "class Mixin:\n    def shared(self):\n        return 9\n\n",
    ),
    "remove_method": (
        "pkg/base.py",
        "class Mixin:\n    def fmt(self):\n        return 1\n",
        "class Mixin:\n    pass\n",
    ),
    "base_class": ("pkg/sub.py", "class Sub(Mixin, Base):", "class Sub(Base):"),
    "import_alias": (
        "pkg/hub.py",
        "from .base import make as _make",
        "from .base import factory as _make",
    ),
    "return_annotation": (
        "pkg/base.py",
        "def factory() -> Store:",
        "def factory() -> Base:",
    ),
    # 星号导入换了来源：整文件处理（所有名字都算变化）。
    "star_import": ("star.py", "from pkg.base import *", "from pkg.sub import *"),
}


def _write_tree(root) -> None:
    for name, text in _FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _sync(root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    scope = make_source_scope_descriptor()
    cache = ASTCache(str(root))
    try:
        return IncrementalSync(cache).sync(
            max_files=scope.certification_max_files,
            exclude_patterns=scope.effective_excludes,
            source_scope=scope,
        )
    finally:
        cache.close()


def _dump(root):
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    location = resolve_index_location(str(root))
    assert location.published is True
    return canonical_dump(location.path)


def _wipe_index(root) -> None:
    cache = os.path.join(root, ".ast-cache")
    # 已封存的版本文件带只读位（RFC-0032 slice 3），删除前先恢复写权限。
    for directory, _dirs, files in os.walk(cache):
        for name in files:
            os.chmod(os.path.join(directory, name), stat.S_IWRITE | stat.S_IREAD)
    shutil.rmtree(cache)


def _edit(root, name: str) -> None:
    rel, old, new = _EDITS[name]
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, name
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))


@pytest.fixture(autouse=True)
def _fresh_guard():
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    auto_index_guard.reset()
    yield
    auto_index_guard.reset()


# slow_ok：每个用例做三次真实刷新与一次全新重建，并转储两份完整索引。
@pytest.mark.slow_ok
@pytest.mark.parametrize("edit", sorted(_EDITS))
def test_scoped_refresh_equals_a_fresh_rebuild(tmp_path, edit: str) -> None:
    root = tmp_path / "project"
    _write_tree(root)
    _sync(root)
    _sync(root)
    _edit(root, edit)
    result = _sync(root)
    refreshed = _dump(root)

    _wipe_index(root)
    _sync(root)
    rebuilt = _dump(root)

    assert result.backfill_scope["mode"] == "scoped", result.backfill_scope
    assert dump_differences(refreshed, rebuilt) == {}
    assert refreshed["edges"]
    if edit == "body_only":
        # 只改函数体：解析面不变，没有依赖文件，名字重置的边恢复为原解析。
        assert result.backfill_scope["surface_changed_files"] == 0
        assert result.backfill_scope["dependent_files"] == 0
        assert result.backfill_scope["scope_names"] == 0
    else:
        assert result.backfill_scope["surface_changed_files"] == 1


def test_scope_falls_back_to_full_when_it_cannot_be_bounded() -> None:
    import sqlite3

    from tree_sitter_analyzer.cache import backfill_scope

    conn = sqlite3.connect(":memory:")
    # 没有调用图标记（上一轮回填未收敛）：不武装，回填为全量。
    backfill_scope.begin(conn)
    assert backfill_scope.decide(None, conn, 1).to_dict() == {
        "mode": "full",
        "reason": "COLLECTOR_NOT_ARMED",
    }
    assert backfill_scope.decide(None, conn, None).reason == "CHANGED_FILES_UNKNOWN"
    with backfill_scope.active(conn, None):
        assert backfill_scope.current(conn) is None


def _row(
    symbols: list[dict], imports: list[str] = (), module_types: dict | None = None
):
    import json

    payload: dict = {"symbols": symbols, "syntax_error": False}
    if module_types:
        payload["module_types"] = module_types
    return (
        "python",
        json.dumps(payload),
        json.dumps([{"text": t, "line": 1} for t in imports]),
    )


def test_surface_ignores_positions_and_sees_resolution_inputs() -> None:
    from tree_sitter_analyzer.cache.backfill_scope import _surface

    base = {
        "kind": "function",
        "name": "make",
        "line": 3,
        "end_line": 4,
        "params": "()",
    }
    moved = dict(base, line=9, end_line=12, complexity=4, docstring="x")
    assert _surface(_row([base])).items == _surface(_row([moved])).items
    typed = dict(base, return_type="Store")
    old, new = _surface(_row([base])), _surface(_row([typed]))
    assert old.items["make"] != new.items["make"]
    aliased = _surface(_row([], ["from .base import factory as make"]))
    plain = _surface(_row([], ["from .base import make"]))
    assert aliased.items["make"] != plain.items["make"]
    singleton = _surface(_row([], module_types={"S": {"returns_of": "Sub"}}))
    assert singleton.items["S"]
    klass = _surface(
        _row([{"kind": "class", "name": "Sub", "line": 1, "parents": ["A"]}])
    )
    assert klass.classes == {"Sub"}
    # 星号导入与不认识的导入只能整文件处理：它们进入文件级标记。
    star = _surface(_row([], ["from .base import *"]))
    assert star.items["@flags"] != _surface(_row([])).items["@flags"]
    assert _surface(None).items == {}
