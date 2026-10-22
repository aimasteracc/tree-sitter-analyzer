"""#1721：函数内 ``global _f`` 重新绑定再导出模块的属性，范围回填也必须看见它。

#1705 在 ``hub`` 重新绑定 ``_f`` 时不把 ``owner._f()`` 解析到 ``core.f``。#1696 的范围
回填只在改动文件的解析面（``symbols_json`` / 导入）变化时重新解析别的文件的边；
函数内的 ``global _f; _f = ...`` 不产生符号，解析面不变，``user.py`` 的旧解析被原样
保留——增量刷新与全新重建给出不同的索引。

等价门：增删这样的重新绑定之后，刷新结果的规范化转储等于同一源码的全新重建。
"""

from __future__ import annotations

import os
import shutil
import stat

import pytest

from tests.unit._index_canonical_dump import canonical_dump, dump_differences

_PLAIN_HUB = "from .core import f as _f\n\n\ndef install(value):\n    return value\n"
_REBINDING_HUB = (
    "from .core import f as _f\n\n\n"
    "def install(value):\n"
    "    global _f\n"
    "    _f = value\n"
    "    return value\n"
)
_FILES = {
    "pkg/__init__.py": "",
    "pkg/core.py": "def f(x):\n    return x\n",
    "pkg/user.py": (
        "import pkg.hub as owner\n\n\ndef use(x):\n    return owner._f(x)\n"
    ),
    "other.py": "def unrelated():\n    return 7\n",
}


def _write_tree(root, hub: str) -> None:
    for name, text in {**_FILES, "pkg/hub.py": hub}.items():
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
    for directory, _dirs, files in os.walk(cache):
        for name in files:
            os.chmod(os.path.join(directory, name), stat.S_IWRITE | stat.S_IREAD)
    shutil.rmtree(cache)


def _rewrite_hub(root, text: str) -> None:
    path = root / "pkg" / "hub.py"
    path.write_text(text, encoding="utf-8")
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))


def _owner_call_resolution(dump: dict) -> list:
    return sorted(
        repr(edge)
        for edge in dump["edges"]
        if "owner._f" in repr(edge) or "'_f'" in repr(edge)
    )


@pytest.fixture(autouse=True)
def _fresh_guard():
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    auto_index_guard.reset()
    yield
    auto_index_guard.reset()


# slow_ok：每个用例做三次真实刷新与一次全新重建，并转储两份完整索引。
@pytest.mark.slow_ok
@pytest.mark.parametrize(
    ("before", "after"),
    [(_PLAIN_HUB, _REBINDING_HUB), (_REBINDING_HUB, _PLAIN_HUB)],
    ids=["add_global_rebinding", "remove_global_rebinding"],
)
def test_refresh_after_a_global_rebinding_equals_a_fresh_rebuild(
    tmp_path, before: str, after: str
) -> None:
    root = tmp_path / "project"
    _write_tree(root, before)
    _sync(root)
    _sync(root)
    _rewrite_hub(root, after)
    result = _sync(root)
    refreshed = _dump(root)

    _wipe_index(root)
    _sync(root)
    rebuilt = _dump(root)

    # 范围回填可以保留，也可以退回全量；但必须与全新重建一致。
    assert result.backfill_scope["mode"] in {"scoped", "full"}, result.backfill_scope
    assert dump_differences(refreshed, rebuilt) == {}
    assert _owner_call_resolution(refreshed) == _owner_call_resolution(rebuilt)


def test_surface_sees_global_rebindings() -> None:
    import json

    from tree_sitter_analyzer.cache.backfill_scope import _surface

    def row(rebinds: list[str] | None) -> tuple[str, str, str]:
        payload: dict = {"symbols": [], "syntax_error": False}
        if rebinds is not None:
            payload["module_rebinds"] = rebinds
        return ("python", json.dumps(payload), "[]")

    assert _surface(row(["_f"])).items.get("_f") != _surface(row(None)).items.get("_f")
    assert _surface(row([])).items == _surface(row(None)).items


def test_module_rebinds_are_extracted() -> None:
    import tree_sitter
    import tree_sitter_python

    from tree_sitter_analyzer.module_rebinds import module_rebinds

    source = (
        "import os\n"
        "x = 1\n"
        "def a():\n"
        "    global _f, _g\n"
        "    _f = 1\n"
        "def b():\n"
        "    def inner():\n"
        "        nonlocal y\n"
        "    y = 2\n"
        "del os\n"
        "del (p, q)\n"
        "del z.attr\n"
        "class C:\n"
        "    def m(self):\n"
        "        global _h\n"
    )
    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_python.language()))
    tree = parser.parse(source.encode("utf-8"))

    # `global` 名字（任意深度）与模块级 `del` 的名字；`nonlocal` 不是模块名字。
    assert module_rebinds(tree.root_node) == ["_f", "_g", "_h", "os", "p", "q"]


def test_extractor_version_is_bumped_for_module_rebinds() -> None:
    from tree_sitter_analyzer import ast_cache
    from tree_sitter_analyzer.cache import indexer

    assert (
        ast_cache._AST_CACHE_EXTRACTOR_VERSION,
        indexer._AST_CACHE_EXTRACTOR_VERSION,
    ) == (50, 50)
