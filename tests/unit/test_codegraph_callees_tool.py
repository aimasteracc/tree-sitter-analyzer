"""RED tests for Feature 1 (Synapse): codegraph_callees tool surface.

The CodeGraphCalleesTool response shape today does NOT include the new
``callee_resolution`` / ``callee_resolved_file`` keys. Once the resolver
ships, every callee entry must carry them.

Harness mirrors ``tests/unit/test_callers_callees_tools.py`` so the
existing project-root + tool fixtures work the same way.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from tests.unit._navigation_test_support import assert_sqlite_deadline_falls_back
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools import relation_freshness as rf
from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool


@pytest.fixture
def indexed_call_project(tmp_path: Path) -> str:
    (tmp_path / "helper.py").write_text(
        "def helper():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "worker.py").write_text(
        "from helper import helper\n\n\ndef build():\n    return helper()\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return str(tmp_path)


@pytest.fixture
def callees_tool(indexed_call_project: str) -> CodeGraphCalleesTool:
    return CodeGraphCalleesTool(indexed_call_project)


class TestCodeGraphCalleesResolutionFields:
    """Once Synapse lands, every callee entry exposes the resolution columns."""

    @pytest.mark.asyncio
    async def test_callees_tool_response_includes_resolution_fields(
        self, callees_tool: CodeGraphCalleesTool
    ) -> None:
        """Each callees[*] entry must have callee_resolution + resolved_file.

        Uses a tiny indexed project where worker.build imports helper.helper,
        so the response list must be non-empty and include a resolved
        cross-file project callee without scanning the whole repository.
        """
        result = await callees_tool.execute(
            {"function_name": "build", "output_format": "json"}
        )
        assert result["success"] is True, f"tool errored: {result}"
        callees = result.get("callees", [])
        assert isinstance(callees, list), (
            f"expected list of callees, got {type(callees).__name__}"
        )
        assert callees, (
            "build is known to call helper; got an empty "
            "callees list, which suggests the cache is stale or the index "
            "missed the file"
        )

        # Every entry must carry the two new keys.
        missing_resolution = [
            i for i, e in enumerate(callees) if "callee_resolution" not in e
        ]
        missing_resolved_file = [
            i for i, e in enumerate(callees) if "callee_resolved_file" not in e
        ]
        assert not missing_resolution, (
            f"{len(missing_resolution)} of {len(callees)} callee entries "
            f"are missing 'callee_resolution' (e.g. entry "
            f"{callees[missing_resolution[0]]!r})"
        )
        assert not missing_resolved_file, (
            f"{len(missing_resolved_file)} of {len(callees)} callee entries "
            f"are missing 'callee_resolved_file' (e.g. entry "
            f"{callees[missing_resolved_file[0]]!r})"
        )

        # Values must come from the documented enum.
        allowed = {"local", "project", "stdlib", "third_party", "dynamic", "unknown"}
        for entry in callees:
            res = entry["callee_resolution"]
            assert res in allowed, (
                f"callee_resolution={res!r} not in allowed set {sorted(allowed)}"
            )
            # resolved_file is a string (possibly empty for unknown/stdlib).
            assert isinstance(entry["callee_resolved_file"], str)

        project_edges = [
            e
            for e in callees
            if e["callee_resolution"] == "project"
            and e["callee_resolved_file"] == "helper.py"
        ]
        assert project_edges, (
            "expected build -> helper to resolve across files via the EdgeStore "
            f"read path. Sample entries: {callees[:3]}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_type", [CodeGraphCallersTool, CodeGraphCalleesTool])
async def test_sqlite_deadline_falls_back_to_coordinate_query(
    tmp_path, monkeypatch, tool_type
) -> None:
    await assert_sqlite_deadline_falls_back(
        tmp_path,
        monkeypatch,
        tool_type(str(tmp_path)),
        {"function_name": "target"},
    )


# Issue #1450：关闭正文后必须彻底绕过源码读取路径。
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_type", "function_name"),
    [
        (CodeGraphCallersTool, "Service.target"),
        (CodeGraphCalleesTool, "caller"),
    ],
)
async def test_certified_graph_routes_report_cache_source(
    tmp_path, monkeypatch, tool_type, function_name
) -> None:
    """认证图回退路径必须准确声明缓存证据来源。"""
    (tmp_path / "sample.py").write_text(
        "class Service:\n"
        "    def target(self):\n"
        "        return 1\n\n"
        "def caller(service):\n"
        "    return service.target()\n",
        encoding="utf-8",
    )
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True

    tool = tool_type(str(tmp_path))
    monkeypatch.setattr(tool, "_cache_call_graph_built", lambda _cache: False)
    result = await tool.execute(
        {"function_name": function_name, "output_format": "json"}
    )

    assert result["data_source"] == "cache"


@pytest.mark.parametrize("tool_type", [CodeGraphCallersTool, CodeGraphCalleesTool])
def test_call_graph_tools_expose_body_opt_out(tool_type) -> None:
    """调用图工具必须声明保留默认行为的正文开关。"""
    schema = tool_type().get_tool_schema()

    assert schema["properties"]["include_bodies"] == {
        "type": "boolean",
        "description": (
            "When false, omit "
            f"{'caller' if tool_type is CodeGraphCallersTool else 'callee'} "
            "source bodies and return only call-graph coordinates and metadata."
        ),
        "default": True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_type", "function_name", "list_key", "count_key", "inline_method"),
    [
        (
            CodeGraphCallersTool,
            "helper",
            "callers",
            "caller_count",
            "_inline_caller_bodies",
        ),
        (
            CodeGraphCalleesTool,
            "build",
            "callees",
            "callee_count",
            "_inline_callee_bodies",
        ),
    ],
)
async def test_include_bodies_false_skips_source_enrichment(
    indexed_call_project,
    monkeypatch,
    tool_type,
    function_name,
    list_key,
    count_key,
    inline_method,
) -> None:
    """关闭正文时仍返回完整坐标结果，并且不进入源码读取路径。"""
    tool = tool_type(indexed_call_project)

    def reject_inline(*_args, **_kwargs):
        raise AssertionError("include_bodies=false must skip source enrichment")

    monkeypatch.setattr(tool, inline_method, reject_inline)
    result = await tool.execute(
        {
            "function_name": function_name,
            "include_bodies": False,
            "output_format": "json",
        }
    )

    assert result[count_key] == 1
    assert len(result[list_key]) == 1
    assert "body" not in result[list_key][0]


# ── dogfood 2026-10-14：长寿命 nav 不得用过期的内存调用图给出“确定”答案 ──
#
# 实测：同一 MCP 服务器内建索引 → callers=2 → 编辑源码新增第三个调用者 →
# 重建索引后仍答 2，且没有任何过期标记；新函数的 callees 被归咎为“拼写错误”。

_STORE_SOURCE = (
    "class Store:\n"
    "    def read_selector(self):\n"
    "        return 1\n\n"
    "    def one(self):\n"
    "        return self.read_selector()\n\n"
    "    def two(self):\n"
    "        return self.read_selector()\n"
)
_PROBE_METHOD = "\n    def _dogfood_probe(self):\n        return self.read_selector()\n"
_CALLERS_QUERY = {
    "action": "callers",
    "symbol": "Store.read_selector",
    "include_bodies": False,
}
_REFRESH = "`index action=cache mode=index` (CLI: `--ast-cache --ast-cache-mode index`)"
_STALE_STEP = (
    "Source changed since the index was built: store.py. This answer reflects "
    f"the index, not the edited files. Run {_REFRESH} to refresh, then retry."
)


def _evidence(freshness: str, reason: str) -> dict[str, object]:
    return {
        "freshness": freshness,
        "snapshot_id": None,
        "source_generation": None,
        "reason": reason,
    }


_STALE = _evidence("stale", "SOURCE_INDEX_MISMATCH")
_SCOPED = _evidence("unknown", "SOURCE_REVALIDATION_SCOPED")
_UNKNOWN = _evidence("unknown", "SOURCE_SCOPE_UNKNOWN")


async def _reindex(root: str) -> None:
    from tree_sitter_analyzer.mcp.tools.index_facade import build_index_facade

    result = await build_index_facade(root).execute(
        {"action": "cache", "mode": "index"}
    )
    assert result["success"] is True


@pytest.fixture
async def long_lived_nav(tmp_path: Path):
    """一个贯穿全部调用的 nav 实例，模拟同一 MCP 服务器进程。"""
    from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

    (tmp_path / "store.py").write_text(_STORE_SOURCE, encoding="utf-8")
    await _reindex(str(tmp_path))
    nav = build_nav_facade(str(tmp_path))
    first = await nav.execute(dict(_CALLERS_QUERY))
    assert [c["name"] for c in first["callers"]] == ["one", "two"]
    return nav, tmp_path


def _add_probe_caller(root: Path) -> None:
    (root / "store.py").write_text(_STORE_SOURCE + _PROBE_METHOD, encoding="utf-8")


@pytest.mark.asyncio
async def test_long_lived_nav_callers_reflect_reindex(long_lived_nav) -> None:
    # dogfood 2026-10-14：重建索引后内存调用图必须随索引身份失效重建
    nav, root = long_lived_nav
    _add_probe_caller(root)
    await _reindex(str(root))

    result = await nav.execute(dict(_CALLERS_QUERY))

    assert sorted(c["name"] for c in result["callers"]) == [
        "_dogfood_probe",
        "one",
        "two",
    ]


@pytest.mark.asyncio
async def test_long_lived_nav_callers_without_reindex_are_marked_stale(
    long_lived_nav,
) -> None:
    # dogfood 2026-10-14：未重建索引时答案必须声明过期并给出可执行的刷新步骤
    nav, root = long_lived_nav
    _add_probe_caller(root)

    result = await nav.execute(dict(_CALLERS_QUERY))

    assert (result["caller_count"], result["source_evidence"]) == (2, _STALE)
    assert result["agent_summary"]["next_step"] == _STALE_STEP


@pytest.mark.asyncio
async def test_new_symbol_absent_from_stale_index_is_not_a_spelling_error(
    long_lived_nav,
) -> None:
    # dogfood 2026-10-14：新函数未入索引时应报告索引过期，而不是“检查拼写”
    nav, root = long_lived_nav
    _add_probe_caller(root)

    result = await nav.execute(
        {"action": "callees", "symbol": "_dogfood_probe", "include_bodies": False}
    )

    assert (result["verdict"], result["source_evidence"]) == (
        "NOT_FOUND",
        _STALE,
    )
    assert result["next_step"] == (
        f"{_STALE_STEP} Symbol '_dogfood_probe' is not in the index, but the "
        "index is stale, so this is not evidence of absence."
    )


@pytest.mark.asyncio
async def test_unchanged_source_is_never_reported_fresh_by_scoped_check(
    long_lived_nav,
) -> None:
    # dogfood 2026-10-14：逐次检查只覆盖答案涉及的文件，所以不能宣称 fresh
    nav, _root = long_lived_nav

    result = await nav.execute(dict(_CALLERS_QUERY))

    assert result["source_evidence"] == _SCOPED


@pytest.mark.asyncio
async def test_memoized_graph_is_reused_while_index_identity_is_unchanged(
    tmp_path: Path,
) -> None:
    # dogfood 2026-10-14：身份检查必须廉价且稳定——索引未变时不重建调用图
    (tmp_path / "store.py").write_text(_STORE_SOURCE, encoding="utf-8")
    await _reindex(str(tmp_path))
    tool = CodeGraphCallersTool(str(tmp_path))
    query = {"function_name": "Store.read_selector", "include_bodies": False}
    await tool.execute(dict(query))
    first_graph = tool.get_call_graph()

    await tool.execute(dict(query))

    assert tool.get_call_graph() is first_graph


def _bump_mtime(path: Path) -> None:
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 10**9))


def _evidence_for(cache, root: Path, *, absence: bool):
    return rf.relation_source_evidence(cache, str(root), ["store.py"], absence=absence)


@pytest.fixture
def indexed_store(tmp_path: Path):
    """已建索引的单文件项目及其打开的缓存（freshness 单元测试共用）。"""
    (tmp_path / "store.py").write_text(_STORE_SOURCE, encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_project()
    try:
        yield cache, tmp_path
    finally:
        cache.close()


def test_touch_without_content_change_is_not_stale(indexed_store) -> None:
    # dogfood 2026-10-14：仅 mtime 变化须比较内容摘要，touch 不能误报过期
    cache, root = indexed_store
    _bump_mtime(root / "store.py")

    assert _evidence_for(cache, root, absence=False) == (_SCOPED, [])


def test_same_size_content_change_is_stale(indexed_store) -> None:
    # dogfood 2026-10-14：等长编辑只改变 mtime 与内容，必须由摘要识别为过期
    cache, root = indexed_store
    path = root / "store.py"
    path.write_text(_STORE_SOURCE.replace("return 1", "return 2"), encoding="utf-8")
    _bump_mtime(path)

    evidence, changed = _evidence_for(cache, root, absence=False)

    assert (evidence, changed) == (_STALE, ["store.py"])


def test_unreadable_source_counts_as_changed(indexed_store, monkeypatch) -> None:
    # dogfood 2026-10-14：无法重读的源码不能被当作与索引一致
    from tree_sitter_analyzer import incremental_sync_support

    cache, root = indexed_store
    _bump_mtime(root / "store.py")

    def unreadable(_path: str) -> str:
        raise OSError("locked")

    monkeypatch.setattr(incremental_sync_support, "file_content_hash", unreadable)

    assert _evidence_for(cache, root, absence=False) == (
        _STALE,
        ["store.py"],
    )


def test_absence_scan_over_budget_is_unknown(indexed_store, monkeypatch) -> None:
    # dogfood 2026-10-14：超出期限的复核不能以部分结果冒充一致或过期
    cache, root = indexed_store
    monkeypatch.setattr(rf, "_ABSENCE_SCAN_DEADLINE_SECONDS", -1.0)

    assert _evidence_for(cache, root, absence=True) == (_UNKNOWN, [])


def test_unreadable_index_rows_are_unknown(tmp_path: Path) -> None:
    # dogfood 2026-10-14：索引读失败是 unknown，不是“一致”
    class _BrokenCache:
        def get_conn(self):
            raise sqlite3.OperationalError("database is locked")

    assert _evidence_for(_BrokenCache(), tmp_path, absence=False) == (_UNKNOWN, [])


def test_no_cache_is_missing_index(tmp_path: Path) -> None:
    # dogfood 2026-10-14：没有索引时沿用 Pulse 的 missing / MISSING_INDEX
    assert _evidence_for(None, tmp_path, absence=True) == (
        _evidence("missing", "MISSING_INDEX"),
        [],
    )


def test_changed_files_names_at_most_three(tmp_path: Path) -> None:
    # dogfood 2026-10-14：找到足够点名的变更文件后即停止复核
    rows = [(f"{name}.py", 0, 1, "x") for name in ("a", "b", "c", "d")]

    assert rf._changed_files(str(tmp_path), rows, None) == ["a.py", "b.py", "c.py"]


def test_index_identity_reports_unresolvable_selector(tmp_path, monkeypatch) -> None:
    # dogfood 2026-10-14：无法解析的 generation 选择器得到稳定身份，不会每次重建
    from tree_sitter_analyzer.cache import generation_routing
    from tree_sitter_analyzer.cache.generation_selector import (
        InvalidGenerationSelector,
    )

    def invalid(_root: str):
        raise InvalidGenerationSelector("INDEX_GENERATION_SELECTOR_INVALID")

    monkeypatch.setattr(generation_routing, "resolve_index_location", invalid)

    assert rf.index_identity(str(tmp_path)) == (
        "unresolvable",
        "InvalidGenerationSelector",
        "INDEX_GENERATION_SELECTOR_INVALID",
    )


def test_index_identity_reports_unreadable_database(tmp_path: Path) -> None:
    # dogfood 2026-10-14：损坏的索引库得到稳定身份，不抛出也不伪装为空索引
    (tmp_path / ".ast-cache").mkdir()
    (tmp_path / ".ast-cache" / "index.db").write_bytes(b"not a sqlite database" * 64)

    assert rf.index_identity(str(tmp_path))[2:] == ("unreadable", "DatabaseError")
