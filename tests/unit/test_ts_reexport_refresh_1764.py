"""#1764：桶文件的再导出改动后，增量刷新必须等于全新重建。

``dup()`` 经 ``lib/index.ts`` 的 ``export * from './mid'`` 与 ``mid.ts`` 的
``export * from './a'`` 解析到 ``a.ts``。``mid.ts`` 再加一个也导出 ``dup`` 的星号来源后，
按 ES 语义这个名字不再被导出；调用文件既不改动、也不直接导入 ``mid.ts``，只有沿再导出
追踪导入方，范围回填才会重新解析它。
"""

from __future__ import annotations

import pytest

from tests.unit._index_canonical_dump import dump_differences
from tests.unit.test_js_object_export_refresh_1741 import (
    _dump,
    _fresh_guard,  # noqa: F401 — autouse fixture
    _sync,
    _wipe_index,
    _write,
)

_MID_ONE = "export * from './a';\n"
_MID_TWO = "export * from './a';\nexport * from './b';\n"
_MID_NAMED = "export { dup } from './b';\n"
_FILES = {
    "lib/a.ts": "export function dup() {\n  return 1;\n}\n",
    "lib/b.ts": "export function dup() {\n  return 2;\n}\n",
    "lib/index.ts": "export * from './mid';\n",
    "src/use.ts": (
        "import { dup } from '../lib/index';\nexport function run() {\n  return dup();\n}\n"
    ),
}


def _calls(dump: dict) -> list:
    return sorted(repr(edge) for edge in dump["edges"] if "dup" in repr(edge))


# slow_ok：每个用例做三次真实刷新与一次全新重建，并转储两份完整索引。
@pytest.mark.slow_ok
@pytest.mark.parametrize(
    ("before", "after"),
    [(_MID_ONE, _MID_TWO), (_MID_TWO, _MID_ONE), (_MID_ONE, _MID_NAMED)],
    ids=["add_conflicting_star", "drop_conflicting_star", "star_to_named"],
)
def test_refresh_after_reexport_change_equals_fresh_rebuild(
    tmp_path, before: str, after: str
) -> None:
    root = tmp_path / "project"
    for name, text in _FILES.items():
        _write(root, name, text)
    _write(root, "lib/mid.ts", before)
    _sync(root)
    _sync(root)
    _write(root, "lib/mid.ts", after, bump=True)
    result = _sync(root)
    refreshed = _dump(root)

    _wipe_index(root)
    _sync(root)
    rebuilt = _dump(root)

    assert result.backfill_scope["mode"] in {"scoped", "full"}, result.backfill_scope
    assert _calls(refreshed) == _calls(rebuilt)
    assert dump_differences(refreshed, rebuilt) == {}
