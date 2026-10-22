"""#1746：JS/TS ``imports`` 边的 ``callee_resolved_file`` 不能取决于索引顺序。

写入时按"已经索引的文件"解析相对说明符：全新重建里导入方（``lib/platform/index.js``）
排在目标（``lib/platform/node/index.js``）之前，写成 ``""``；刷新时目标已在索引里，
写成目标文件——刷新因此不等于全新重建。两条路线都必须按本轮结束时的文件集合解析。
"""

from __future__ import annotations

import json
import os

import pytest

from tests.unit._index_canonical_dump import dump_differences
from tests.unit.test_js_object_export_refresh_1741 import (
    _dump,
    _sync,
    _wipe_index,
    _write,
)

_TARGET = "lib/platform/node/index.js"
_IMPORTER = "lib/platform/index.js"
_FILES = {
    _TARGET: "const generateString = (n) => 'x'.repeat(n);\n\nexport default { generateString };\n",
    _IMPORTER: "import platform from './node/index.js';\n\nexport default { ...platform };\n",
}


@pytest.fixture(autouse=True)
def _fresh_guard():
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    auto_index_guard.reset()
    yield
    auto_index_guard.reset()


def _import_targets(dump: dict) -> dict[str, str]:
    """``imports`` 边：``导入方 -> 模块节点`` 映射到写入的 ``callee_resolved_file``。"""
    out: dict[str, str] = {}
    for edge in dump["edges"]:
        if "imports" not in edge:
            continue
        texts = [value for value in edge if isinstance(value, str)]
        source = next(v for v in texts if v.startswith("file:"))
        target = next(v for v in texts if v.startswith("module:"))
        metadata = next(json.loads(v) for v in texts if v.startswith("{"))
        out[f"{source} -> {target}"] = metadata.get("callee_resolved_file", "")
    return out


# slow_ok：每个用例做多次真实刷新与一次全新重建，并转储两份完整索引。
@pytest.mark.slow_ok
def test_a_refreshed_importer_equals_a_fresh_rebuild(tmp_path) -> None:
    root = tmp_path / "project"
    for name, text in _FILES.items():
        _write(root, name, text)
    _sync(root)
    _sync(root)
    _write(
        root,
        _IMPORTER,
        _FILES[_IMPORTER].replace("...platform", "...platform, extra: 1"),
        bump=True,
    )
    _sync(root)
    refreshed = _dump(root)

    _wipe_index(root)
    _sync(root)
    rebuilt = _dump(root)

    assert dump_differences(refreshed, rebuilt) == {}
    # 解析结果是目标文件（不是两边一致地都为空）。
    assert _import_targets(rebuilt) == {
        "file:lib/platform/index.js -> module:./node/index.js": _TARGET
    }


@pytest.mark.slow_ok
def test_a_target_added_later_resolves_its_unchanged_importer(tmp_path) -> None:
    """目标文件后加入：未改动的导入方的边也要解析（全新重建同样解析）。"""
    root = tmp_path / "project"
    _write(root, _IMPORTER, _FILES[_IMPORTER])
    _sync(root)
    _sync(root)
    _write(root, _TARGET, _FILES[_TARGET], bump=True)
    _sync(root)
    refreshed = _dump(root)

    _wipe_index(root)
    _sync(root)
    rebuilt = _dump(root)

    assert dump_differences(refreshed, rebuilt) == {}
    assert _import_targets(refreshed) == {
        "file:lib/platform/index.js -> module:./node/index.js": _TARGET
    }


@pytest.mark.slow_ok
def test_a_deleted_target_clears_its_importer(tmp_path) -> None:
    root = tmp_path / "project"
    for name, text in _FILES.items():
        _write(root, name, text)
    _sync(root)
    _sync(root)
    os.remove(root / _TARGET)
    _sync(root)
    refreshed = _dump(root)

    _wipe_index(root)
    _sync(root)
    rebuilt = _dump(root)

    assert dump_differences(refreshed, rebuilt) == {}
    assert _import_targets(refreshed) == {
        "file:lib/platform/index.js -> module:./node/index.js": ""
    }


def test_the_pass_rewrites_only_well_formed_js_edges_whose_target_changed() -> None:
    """直接在边表上：只改形状正确、解析结果变了的 JS/TS 导入边；其余原样保留。"""
    import sqlite3

    from tree_sitter_analyzer.cache.import_specifier_edges import (
        resolve_import_specifier_edges,
    )
    from tree_sitter_analyzer.graph.edge_store import EdgeStore

    conn = sqlite3.connect(":memory:")
    EdgeStore(conn)
    conn.execute("CREATE TABLE ast_index (file_path TEXT PRIMARY KEY)")
    conn.executemany(
        "INSERT INTO ast_index(file_path) VALUES (?)", [(_TARGET,), (_IMPORTER,)]
    )

    def meta(resolved: str) -> str:
        return json.dumps(
            {"callee_resolved_file": resolved, "language": "javascript"},
            ensure_ascii=False,
            sort_keys=True,
        )

    rows = [
        # (source, target, line, metadata, column) —— 只有第一行该被改写
        ("file:lib/platform/index.js", "module:./node/index.js", 1, meta(""), ""),
        (
            "file:lib/platform/index.js",
            "module:./node/index.js",
            2,
            meta(_TARGET),
            _TARGET,
        ),
        ("file:lib/platform/index.js", "module:./missing.js", 3, meta(""), ""),
        ("file:lib/platform/index.js", "module:./node/index.js", 4, "{not json", ""),
        ("file:lib/platform/index.js", "module:./node/index.js", 5, "[1, 2]", ""),
        ("lib/platform/index.js", "module:./node/index.js", 6, meta(""), ""),
        ("file:lib/platform/index.js", "./node/index.js", 7, meta(""), ""),
    ]
    conn.executemany(
        "INSERT INTO edges (source_node_id, target_node_id, kind, line, metadata, "
        "language, callee_resolved_file) VALUES (?, ?, 'imports', ?, ?, 'javascript', ?)",
        rows,
    )

    stats = resolve_import_specifier_edges(conn)

    stored = conn.execute(
        "SELECT line, callee_resolved_file, metadata FROM edges ORDER BY line"
    ).fetchall()
    assert stats == {"total": 3, "resolved": 1, "unchanged": 2, "errors": 0}
    assert stored[0] == (1, _TARGET, meta(_TARGET))
    assert [row[1:] for row in stored[1:]] == [(row[4], row[3]) for row in rows[1:]]
