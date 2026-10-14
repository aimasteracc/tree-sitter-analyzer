"""#1580：``stale_cache`` 警告只针对"从未做过解析"的索引触发。

背景：该警告随 Synapse 跨文件解析（v2, #133）引入，本意是提示"缓存建于解析
列出现之前，需要强制重建以填充解析列"。旧实现按单次答复的条目计算
unknown 占比（≥80% 即告警），于是在一个刚刚全量建好的索引上，只要某个
符号的调用方恰好多为未解析调用（接收者未知的方法调用等），每次答复都会
附带该警告并建议 ``--ast-cache-force``——重建之后依旧如此，形成无效循环。

本文件固定两侧行为：
* 新建索引（解析阶段已运行）上，即便答复条目全部未解析，也不得告警；
* 解析列从未写入的旧缓存（所有调用边仍为默认 ``unknown``）必须继续告警。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.unit._ast_cache_helpers import legacy_cache
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.codegraph_relation_tool import (
    _STALE_CACHE_WARNING,
    _is_stale_resolution,
    index_never_resolved,
    label_graph_relations,
)

# 被查询符号的调用方多为"接收者未知"的方法调用，且项目中有两个同名 `run`：
# 解析器无法确定目标，这些边在新建索引里合理地保持 unresolved。另有一条同文件直接调用，
# 保证解析阶段确实写入了至少一条已解析边。
_SOURCES = {
    "service.py": ("def run():\n    return 1\n\n\ndef boot():\n    return run()\n"),
    "other.py": "def run():\n    return 2\n",
    "worker_a.py": "def go_a(job):\n    return job.run()\n",
    "worker_b.py": "def go_b(job):\n    return job.run()\n",
    "worker_c.py": "def go_c(job):\n    return job.run()\n",
    "worker_d.py": "def go_d(job):\n    return job.run()\n",
    "worker_e.py": "def go_e(job):\n    return job.run()\n",
}


def _write_project(root: Path) -> None:
    for name, text in _SOURCES.items():
        (root / name).write_text(text, encoding="utf-8")


def _build_index(root: Path) -> None:
    cache = ASTCache(str(root))
    try:
        cache.index_project(workers=0)
    finally:
        cache.close()


def _build_never_resolved_cache(root: Path) -> None:
    """模拟解析列出现之前建成的旧库：原地写旧 index.db，所有调用边回到列默认值。"""
    cache = legacy_cache(str(root))
    try:
        cache.index_project(workers=0)
        conn = cache.get_conn()
        conn.execute(
            "UPDATE edges SET callee_resolution = 'unknown', "
            "callee_resolved_file = '', callee_symbol_id = NULL, "
            "metadata = json_remove(metadata, '$.callee_resolution', "
            "'$.callee_resolved_file') "
            "WHERE kind = 'calls'"
        )
        conn.commit()
    finally:
        cache.close()


@pytest.fixture
def fresh_index(tmp_path: Path) -> Path:
    _write_project(tmp_path)
    _build_index(tmp_path)
    return tmp_path


@pytest.fixture
def never_resolved_index(tmp_path: Path) -> Path:
    _write_project(tmp_path)
    _build_never_resolved_cache(tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_callers_on_fresh_index_omit_stale_cache_warning(
    fresh_index: Path,
) -> None:
    # #1580：答复条目多为未解析调用，但索引本身已完成解析——不是缓存陈旧。
    tool = CodeGraphCallersTool(str(fresh_index))
    result = await tool.execute({"function_name": "run", "output_format": "json"})

    assert result["caller_count"] == 6
    unknown = [c for c in result["callers"] if c["callee_resolution"] == "unknown"]
    assert len(unknown) == 5
    assert "warnings" not in result


@pytest.mark.asyncio
async def test_callees_on_fresh_index_omit_stale_cache_warning(
    fresh_index: Path,
) -> None:
    tool = CodeGraphCalleesTool(str(fresh_index))
    result = await tool.execute({"function_name": "go_a", "output_format": "json"})

    assert result["callee_count"] == 1
    assert result["callees"][0]["callee_resolution"] == "unknown"
    assert "warnings" not in result


@pytest.mark.asyncio
async def test_callers_on_never_resolved_cache_keep_stale_cache_warning(
    never_resolved_index: Path,
) -> None:
    # 解析列从未写入：这正是警告要发现的情形，必须继续告警。
    tool = CodeGraphCallersTool(str(never_resolved_index))
    result = await tool.execute({"function_name": "run", "output_format": "json"})

    assert result["caller_count"] == 6
    assert result["warnings"] == [_STALE_CACHE_WARNING]


@pytest.mark.asyncio
async def test_callees_on_never_resolved_cache_keep_stale_cache_warning(
    never_resolved_index: Path,
) -> None:
    tool = CodeGraphCalleesTool(str(never_resolved_index))
    result = await tool.execute({"function_name": "go_a", "output_format": "json"})

    assert result["callee_count"] == 1
    assert result["warnings"] == [_STALE_CACHE_WARNING]


class _ProbeCache:
    """只暴露 ``get_conn`` 的最小缓存：一张 edges 表，若干调用边标记。"""

    def __init__(self, resolutions: list[str]) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.execute(
            "CREATE TABLE edges (kind TEXT, callee_resolution TEXT, "
            "callee_resolved_file TEXT, metadata TEXT)"
        )
        self._conn.executemany(
            "INSERT INTO edges VALUES ('calls', ?, '', '{}')",
            [(r,) for r in resolutions],
        )

    def get_conn(self) -> sqlite3.Connection:
        return self._conn


_ALL_UNKNOWN = [{"callee_resolution": "unknown"} for _ in range(10)]


def test_helper_is_false_for_empty() -> None:
    assert _is_stale_resolution([], _ProbeCache(["unknown"])) is False


def test_helper_is_true_when_all_unknown_on_never_resolved_index() -> None:
    assert _is_stale_resolution(_ALL_UNKNOWN, _ProbeCache(["unknown"])) is True


def test_helper_is_false_when_all_unknown_on_resolved_index() -> None:
    # #1580：分母是索引而非答复——索引里有已解析边就不是"陈旧缓存"。
    cache = _ProbeCache(["unknown", "unknown", "local"])
    assert _is_stale_resolution(_ALL_UNKNOWN, cache) is False


def test_helper_is_false_without_cache_evidence() -> None:
    assert _is_stale_resolution(_ALL_UNKNOWN, None) is False


def test_helper_is_false_when_majority_resolved() -> None:
    # 30% unknown / 70% project → below the 80% threshold.
    entries = [{"callee_resolution": "unknown"} for _ in range(3)] + [
        {"callee_resolution": "project"} for _ in range(7)
    ]
    assert _is_stale_resolution(entries, _ProbeCache(["unknown"])) is False


def test_helper_trips_at_exactly_80_percent() -> None:
    # 8 unknown out of 10 = 80% → at threshold (inclusive).
    entries = [{"callee_resolution": "unknown"} for _ in range(8)] + [
        {"callee_resolution": "project"} for _ in range(2)
    ]
    assert _is_stale_resolution(entries, _ProbeCache(["unknown"])) is True


def test_index_never_resolved_is_false_for_index_without_call_edges() -> None:
    assert index_never_resolved(_ProbeCache([])) is False


def test_index_never_resolved_reads_metadata_marker_of_older_rows() -> None:
    cache = _ProbeCache(["unknown"])
    cache.get_conn().execute(
        "INSERT INTO edges VALUES ('calls', 'unknown', '', "
        '\'{"callee_resolution": "project"}\')'
    )
    assert index_never_resolved(cache) is False


def test_index_never_resolved_is_false_when_edges_table_unreadable() -> None:
    cache = _ProbeCache([])
    cache.get_conn().execute("DROP TABLE edges")
    assert index_never_resolved(cache) is False


# #1586：内存调用图回退路径上，每条边的 callee_resolution 必须如实反映边本身
# ——同文件目标为 local，跨文件目标为 project；不得一律 unknown，也不得把同文件
# 目标标成 project。
_LABEL_SOURCES = {
    "helper.py": "def helper():\n    return 1\n",
    "worker.py": (
        "from helper import helper\n\n\n"
        "def _local():\n    return 2\n\n\n"
        "def build():\n    _local()\n    return helper()\n"
    ),
    "service.py": (
        "class Service:\n"
        "    def run(self):\n        return 1\n\n"
        "    def boot(self):\n        return self.run()\n"
    ),
}


@pytest.fixture(params=["cache", "parse"])
def fallback_root(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """两条内存回退路径：已建索引但调用图标记为假，以及完全无索引的现场解析。"""
    for name, text in _LABEL_SOURCES.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    if request.param == "cache":
        _build_index(tmp_path)
    return tmp_path


def _labels(entries: list[dict]) -> list[tuple[str, str, str]]:
    return sorted(
        (e["name"], e["callee_resolution"], e["callee_resolved_file"]) for e in entries
    )


async def _fallback_execute(tool, monkeypatch, function_name: str) -> dict:
    monkeypatch.setattr(tool, "_cache_call_graph_built", lambda _cache: False)
    return await tool.execute({"function_name": function_name, "output_format": "json"})


@pytest.mark.asyncio
async def test_fallback_callers_label_same_file_target_local(
    fallback_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #1586：旧实现给分类器传空的被调用名，回退路径上每个条目都成了 unknown。
    tool = CodeGraphCallersTool(str(fallback_root))
    result = await _fallback_execute(tool, monkeypatch, "_local")

    assert _labels(result["callers"]) == [("build", "local", "worker.py")]


@pytest.mark.asyncio
async def test_fallback_callers_label_cross_file_target_project(
    fallback_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #1586：跨文件目标为 project，解析文件是目标所在文件而非调用方文件。
    tool = CodeGraphCallersTool(str(fallback_root))
    result = await _fallback_execute(tool, monkeypatch, "helper")

    assert _labels(result["callers"]) == [("build", "project", "helper.py")]


@pytest.mark.asyncio
async def test_qualified_callers_label_self_method_local(
    fallback_root: Path,
) -> None:
    # #1586：限定名 `Class.method` 总是走内存调用图。
    tool = CodeGraphCallersTool(str(fallback_root))
    result = await tool.execute(
        {"function_name": "Service.run", "output_format": "json"}
    )

    assert _labels(result["callers"]) == [("boot", "local", "service.py")]


@pytest.mark.asyncio
async def test_fallback_callees_label_local_and_project(
    fallback_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #1586 / round-2 dogfood：同文件被调用方曾被误标为 project。
    tool = CodeGraphCalleesTool(str(fallback_root))
    result = await _fallback_execute(tool, monkeypatch, "build")

    assert _labels(result["callees"]) == [
        ("_local", "local", "worker.py"),
        ("helper", "project", "helper.py"),
    ]


class _EdgelessGraph:
    """没有任何边的图：目标存在，但不连接到任何调用方。"""

    def resolve_targets(self, func_name, file_path=None):
        return ["target"]

    def caller_refs_of(self, target):
        return []


def test_entry_without_backing_edge_is_unknown_not_guessed() -> None:
    # #1586：找不到对应边时如实标 unknown，不再把条目自身文件冒充解析文件。
    entries = [{"name": "orphan", "file": "a.py", "line": 3}]
    labelled = label_graph_relations(
        _EdgelessGraph(), "target", None, entries, inbound=True
    )

    assert labelled == [
        {
            "name": "orphan",
            "file": "a.py",
            "line": 3,
            "callee_resolution": "unknown",
            "callee_resolved_file": "",
        }
    ]
