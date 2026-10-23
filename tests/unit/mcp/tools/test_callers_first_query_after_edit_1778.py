"""#1778：编辑并增量刷新后的第一次 ``nav callers`` 与冷进程的答案逐字节相同。

长驻进程里：查询（建图、认证快照）→ 编辑（新增调用方，并新增不支持扩展名的文件与
名字像文件的目录）→ 增量刷新 → 第一次查询。答案（完整性判定、原因码、调用方与可能
调用方）必须等于在刷新后的索引上新启动的进程给出的答案，且看得到这次编辑。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import call_graph_memo, call_graph_snapshot_inputs
from tree_sitter_analyzer.languages.lang_extension_map import EXT_TO_LANG
from tree_sitter_analyzer.mcp.tools import certification_timeouts
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_AN_HOUR_NS = 3600 * 1_000_000_000

_WIDGET = (
    "class Widget:\n"
    "    def used(self):\n"
    "        return 1\n\n\n"
    "def run(w: Widget):\n"
    "    return w.used()\n"
)
_HELPER = "def helper():\n    return 3\n\n\ndef top():\n    return helper()\n"
_SECOND_CALLER = "\n\ndef again():\n    return helper()\n"
_NESTED_CALLER = (
    "from pkg.helper import helper\n\n\ndef nested():\n    return helper()\n"
)
_QUERIES = (
    ("helper", "pkg/helper.py"),
    ("used", "widget.py"),
    ("Widget.used", "widget.py"),
    ("top", "pkg/helper.py"),
)
# 冷进程：只导入、查询并打印规范化的答案。
_COLD = r"""
import asyncio, json, sys
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

tool = CodeGraphCallersTool(sys.argv[1])
out = []
for name, file_path in json.loads(sys.argv[2]):
    out.append(asyncio.run(tool.execute(
        {"function_name": name, "file_path": file_path, "include_bodies": False}
    )))
print(json.dumps(out, sort_keys=True, default=str))
"""


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(certification_timeouts.DIR_ENV, str(tmp_path / "timeouts"))
    certification_timeouts.clear()
    call_graph_memo.clear()
    call_graph_snapshot_inputs.clear()
    yield
    certification_timeouts.clear()
    call_graph_memo.clear()
    call_graph_snapshot_inputs.clear()


def _backdate(root: Path) -> None:
    stamp = time.time_ns() - _AN_HOUR_NS
    for path in sorted(root.rglob("*"), reverse=True):
        if ".ast-cache" not in path.parts:
            os.utime(path, ns=(stamp, stamp))
    os.utime(root, ns=(stamp, stamp))


async def _full_index(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    result = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert result["published"] is True


def _incremental_refresh(root: Path) -> None:
    """与 dogfood 刷新门（r12b ``refresh_ab``）相同的进程内增量刷新。"""
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_indexing
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    scope = make_source_scope_descriptor()
    cache = ASTCache(str(root))
    try:
        generation_indexing.run_incremental_sync(
            cache,
            max_files=scope.certification_max_files,
            exclude_patterns=scope.effective_excludes,
            source_scope=scope,
        )
    finally:
        cache.close()


def _args(name: str, file_path: str) -> dict[str, Any]:
    return {"function_name": name, "file_path": file_path, "include_bodies": False}


def _answer(result: dict[str, Any]) -> dict[str, Any]:
    """答案部分：去掉随快照与耗时变化的诊断字段。"""
    keep = (
        "function",
        "file_path",
        "completeness",
        "completeness_reasons",
        "callers",
        "possible_callers",
        "caller_count",
        "possible_caller_count",
        "data_source",
    )
    return json.loads(
        json.dumps({key: result.get(key) for key in keep}, sort_keys=True, default=str)
    )


def _cold_answers(root: Path) -> list[dict[str, Any]]:
    env = dict(os.environ)
    completed = subprocess.run(
        [sys.executable, "-c", _COLD, str(root), json.dumps(_QUERIES)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=600,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    return [_answer(item) for item in json.loads(completed.stdout.splitlines()[-1])]


@pytest.mark.slow_ok
@pytest.mark.asyncio
async def test_first_query_after_edit_and_refresh_equals_a_cold_process(
    tmp_path: Path,
) -> None:
    # The edit adds an unsupported file and a supported file under a directory whose
    # name has an unsupported suffix: the source inventory must still see the latter.
    assert EXT_TO_LANG.get(".txt") is None
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "widget.py").write_text(_WIDGET, encoding="utf-8")
    (root / "pkg" / "helper.py").write_text(_HELPER, encoding="utf-8")
    _backdate(root)
    await _full_index(root)

    tool = CodeGraphCallersTool(str(root))
    before = [_answer(await tool.execute(_args(*query))) for query in _QUERIES]
    assert before[0]["completeness"] == "complete", before[0]
    assert {c["name"] for c in before[0]["callers"]} == {"top"}

    (root / "pkg" / "helper.py").write_text(_HELPER + _SECOND_CALLER, encoding="utf-8")
    (root / "notes.txt").write_text("not source\n", encoding="utf-8")
    (root / "data.txt").mkdir()
    (root / "data.txt" / "extra.py").write_text(_NESTED_CALLER, encoding="utf-8")
    _backdate(root)
    _incremental_refresh(root)

    warm = [_answer(await tool.execute(_args(*query))) for query in _QUERIES]
    assert {c["name"] for c in warm[0]["callers"]} == {"top", "again", "nested"}
    # The import in data.txt/extra.py is a non-call reference: an honest verdict.
    assert warm[0]["completeness_reasons"] == ["NON_CALL_REFERENCES"], warm[0]

    assert warm == _cold_answers(root)
