"""#1741：默认导出对象（及其 ``...spread`` 再导出）改动后，增量刷新必须等于全新重建。

``utils.findKey()`` 经 ``export default { findKey }`` 解析；``platform.generateString()``
还经中间文件的 ``...platform`` 展开。这些导出形状不产生符号，若不进入解析面，#1696
的范围回填会保留别的文件里的旧解析——删掉展开之后仍是确定的调用边。
"""

from __future__ import annotations

import os
import shutil
import stat

import pytest

from tests.unit._index_canonical_dump import canonical_dump, dump_differences

_UTILS_WITH = (
    "const findKey = (o, k) => o[k];\n\nfunction other() {\n  return 1;\n}\n\n"
    "export default {\n  findKey,\n  other,\n};\n"
)
_UTILS_WITHOUT = (
    "const findKey = (o, k) => o[k];\n\nfunction other() {\n  return 1;\n}\n\n"
    "export default {\n  other,\n};\n"
)
_PLATFORM_SPREAD = (
    "import platform from './node/index.js';\n\nexport default {\n  ...platform,\n};\n"
)
_PLATFORM_EMPTY = (
    "import platform from './node/index.js';\n\nexport default {\n  kind: 'x',\n};\n"
)
_FILES = {
    "lib/platform/node/index.js": (
        "const generateString = (n) => 'x'.repeat(n);\n\nexport default {\n  generateString,\n};\n"
    ),
    "lib/core.js": (
        "import utils from './utils.js';\n"
        "import platform from './platform/index.js';\n\n"
        "export function lookup(o) {\n  return utils.findKey(o, 'a');\n}\n\n"
        "export function boundary() {\n  return platform.generateString(3);\n}\n"
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


def _calls(dump: dict) -> list:
    return sorted(
        repr(edge)
        for edge in dump["edges"]
        if "findKey" in repr(edge) or "generateString" in repr(edge)
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
    ("rel", "before", "after"),
    [
        ("lib/utils.js", _UTILS_WITH, _UTILS_WITHOUT),
        ("lib/utils.js", _UTILS_WITHOUT, _UTILS_WITH),
        ("lib/platform/index.js", _PLATFORM_SPREAD, _PLATFORM_EMPTY),
        ("lib/platform/index.js", _PLATFORM_EMPTY, _PLATFORM_SPREAD),
    ],
    ids=["drop_member", "add_member", "drop_spread", "add_spread"],
)
def test_refresh_after_default_export_change_equals_fresh_rebuild(
    tmp_path, rel: str, before: str, after: str
) -> None:
    root = tmp_path / "project"
    for name, text in _FILES.items():
        _write(root, name, text)
    _write(root, "lib/utils.js", _UTILS_WITH)
    _write(root, "lib/platform/index.js", _PLATFORM_SPREAD)
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
    assert _calls(refreshed) == _calls(rebuilt)
    # #1746：`imports` 边的解析与索引顺序无关之后，全部边种类（及整份索引）都须一致。
    assert dump_differences(refreshed, rebuilt) == {}
