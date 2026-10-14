"""无索引现场解析预算（parse_fallback_budget）的行为测试。

#1562：2026-10-14 dogfood 审计中，``nav callers`` 在没有索引的 2415 文件仓库上
静默解析整仓 346 s。预算之外必须立即返回 INDEX_MISSING，而不是现场解析。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.call_graph import CallGraph
from tree_sitter_analyzer.mcp.tools import parse_fallback_budget as budget
from tree_sitter_analyzer.mcp.tools._call_tree_tool import CodeGraphCallerTreeTool
from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool


def _write_project(root: Path, file_count: int) -> str:
    for i in range(file_count):
        (root / f"mod_{i}.py").write_text(
            f"def caller_{i}():\n    target()\n\ndef target():\n    return {i}\n",
            encoding="utf-8",
        )
    return str(root)


@pytest.fixture
def over_budget_root(tmp_path, monkeypatch) -> str:
    # 预算压到 2，用 3 个文件模拟 "大仓库"，保持测试廉价。
    monkeypatch.setattr(budget, "PARSE_FALLBACK_MAX_FILES", 2)
    return _write_project(tmp_path, 3)


@pytest.fixture
def forbid_parse(monkeypatch) -> None:
    def _fail(self: CallGraph) -> None:
        raise AssertionError("whole-repo parse must not run over budget")

    monkeypatch.setattr(CallGraph, "build", _fail)


def test_count_source_files_skips_excluded_and_hidden_dirs(tmp_path) -> None:
    _write_project(tmp_path, 2)
    for skipped in ("node_modules", ".hidden", "__pycache__"):
        (tmp_path / skipped).mkdir()
        (tmp_path / skipped / "x.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not source\n", encoding="utf-8")
    assert budget.count_source_files(str(tmp_path)) == 2


def test_count_source_files_stops_at_limit(tmp_path) -> None:
    _write_project(tmp_path, 5)
    assert budget.count_source_files(str(tmp_path), limit=3) == 3


def test_next_step_names_both_index_routes_and_file_count() -> None:
    assert budget.index_missing_next_step(2415) == (
        "No index exists yet, and this project has 2415 source files — more than "
        "the 200-file limit for an on-the-fly parse, so nothing was parsed. Build "
        "the index once: MCP `index action=cache mode=index` (CLI: "
        "`tree-sitter-analyzer --ast-cache --ast-cache-mode index`). It parses "
        "every source file once — expect minutes, not seconds, for 2415 files — "
        "and later graph reads are SQL lookups. Then retry this query."
    )


def test_refusal_is_skipped_when_a_cache_exists(over_budget_root) -> None:
    tool = CodeGraphCallersTool(over_budget_root)
    assert tool._parse_fallback_refusal(object(), "callers", function="x") is None


@pytest.mark.asyncio
async def test_callers_without_index_over_budget_returns_index_missing(
    over_budget_root, forbid_parse
) -> None:
    # Issue #1562: nav callers silently parsed a 2415-file repo for 346 s.
    result = await CodeGraphCallersTool(over_budget_root).execute(
        {"function_name": "target"}
    )
    assert (
        result["error_code"],
        result["verdict"],
        result["source_file_count"],
        result["parse_fallback_max_files"],
        result["function"],
    ) == ("INDEX_MISSING", "WARN", 3, 2, "target")


@pytest.mark.asyncio
async def test_callees_without_index_over_budget_returns_index_missing(
    over_budget_root, forbid_parse
) -> None:
    # Issue #1562: the callees relation shares the same whole-repo parse fallback.
    result = await CodeGraphCalleesTool(over_budget_root).execute(
        {"function_name": "caller_0"}
    )
    assert (result["error_code"], result["agent_summary"]["summary_line"]) == (
        "INDEX_MISSING",
        "callees: 'caller_0' unavailable — no index for 3 source files",
    )


@pytest.mark.asyncio
async def test_caller_tree_without_index_over_budget_returns_index_missing(
    over_budget_root, forbid_parse
) -> None:
    # Issue #1562: caller_tree expands through the same parse fallback.
    result = await CodeGraphCallerTreeTool(over_budget_root).execute(
        {"symbol": "target"}
    )
    assert (result["error_code"], result["symbol"], result["next_step"]) == (
        "INDEX_MISSING",
        "target",
        budget.index_missing_next_step(3),
    )


@pytest.mark.asyncio
async def test_callers_without_index_within_budget_still_parses(tmp_path) -> None:
    root = _write_project(tmp_path, 2)
    result = await CodeGraphCallersTool(root).execute({"function_name": "target"})
    assert (result["data_source"], result["caller_count"]) == ("parse", 2)
