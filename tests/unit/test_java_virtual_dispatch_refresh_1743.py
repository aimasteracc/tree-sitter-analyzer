"""#1743：Java 经声明类型的绑定依赖别的文件的类、基类型与方法；刷新必须等于全新重建。"""

from __future__ import annotations

import os
import shutil
import stat

import pytest

from tests.unit._index_canonical_dump import canonical_dump

P = "src/main/java/com/ex/"
_BASE = (
    "package com.ex;\n\npublic class Base {\n  public int run() {\n    return 1;\n  }\n\n"
    "  public int stop() {\n    return 2;\n  }\n}\n"
)
_BASE_NO_STOP = "package com.ex;\n\npublic class Base {\n  public int run() {\n    return 1;\n  }\n}\n"
_MID = "package com.ex;\n\npublic class Mid extends Base {\n}\n"
_MID_ROOT = "package com.ex;\n\npublic class Mid {\n  public int run() {\n    return 3;\n  }\n}\n"
_LEAF = "package com.ex;\n\npublic class Leaf extends Mid {\n}\n"
_LEAF_OVERRIDE = "package com.ex;\n\npublic class Leaf extends Mid {\n  @Override\n  public int run() {\n    return 4;\n  }\n}\n"
_FILES = {
    P + "Use.java": (
        "package com.ex;\n\npublic class Use {\n"
        "  int a(Mid m) {\n    return m.run() + m.stop();\n  }\n\n"
        "  int b(Leaf l) {\n    return l.run();\n  }\n}\n"
    ),
}


def _write(root, rel: str, text: str, bump: bool = False) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if bump:
        info = os.stat(path)
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))


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


def _call_edges(dump: dict) -> list:
    return sorted(repr(edge) for edge in dump["edges"] if "'calls'" in repr(edge))


@pytest.fixture(autouse=True)
def _fresh_guard():
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    auto_index_guard.reset()
    yield
    auto_index_guard.reset()


# slow_ok：每个用例做三次真实刷新与一次全新重建，并转储两份完整索引。
@pytest.mark.slow_ok
@pytest.mark.parametrize(
    ("rel", "before", "after"),
    [
        (P + "Base.java", _BASE, _BASE_NO_STOP),
        (P + "Mid.java", _MID, _MID_ROOT),
        (P + "Mid.java", _MID_ROOT, _MID),
        (P + "Leaf.java", _LEAF, _LEAF_OVERRIDE),
    ],
    ids=[
        "ancestor_drops_method",
        "mid_changes_parent",
        "mid_gains_parent",
        "leaf_adds_override",
    ],
)
def test_refresh_after_hierarchy_change_equals_fresh_rebuild(
    tmp_path, rel: str, before: str, after: str
) -> None:
    root = tmp_path / "project"
    for name, text in _FILES.items():
        _write(root, name, text)
    _write(root, P + "Base.java", _BASE)
    _write(root, P + "Mid.java", _MID)
    _write(root, P + "Leaf.java", _LEAF)
    _write(root, rel, before)
    _sync(root)
    _sync(root)
    _write(root, rel, after, bump=True)
    result = _sync(root)
    refreshed = _dump(root)

    _wipe_index(root)
    _sync(root)
    rebuilt = _dump(root)

    assert result.backfill_scope["mode"] in {"scoped", "full"}, result.backfill_scope
    assert _call_edges(refreshed) == _call_edges(rebuilt)
