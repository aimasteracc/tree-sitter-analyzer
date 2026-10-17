"""#1621：同名定义的身份不得在候选去重与可视化节点中合并。

``callee_resolution._item_key`` 曾按 ``qualified_name()`` 去重：没有接收者的
同名定义（两个嵌套的 ``inner``、条件分支里的两个 ``handler``）在同一文件中
只剩一个候选，歧义被隐藏，唯一候选的置信度被抬高。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cached_edge_resolution import CachedEdgeResolver
from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.callee_resolution import CalleeResolver

_NESTED_SAME_NAME = (
    "def outer_a(a):\n"
    "    def inner(b):\n"
    "        return b\n"
    "    return inner(a)\n\n\n"
    "def outer_b(a):\n"
    "    def inner(b):\n"
    "        return b\n"
    "    return inner(a)\n"
)


def _two_inner_refs() -> tuple[FunctionRef, FunctionRef]:
    return (
        FunctionRef("pulse.py", "inner", 2, "python", end_line=3),
        FunctionRef("pulse.py", "inner", 8, "python", end_line=9),
    )


def test_global_candidates_keep_both_receiverless_same_name_definitions() -> None:
    first, second = _two_inner_refs()
    resolver = CalleeResolver(
        functions_by_name={"inner": [first, second]},
        functions_by_file={"pulse.py": [first, second]},
        name_to_source={},
    )

    assert resolver.resolve_items("inner", "other.py") == [
        (first, 0.5),
        (second, 0.5),
    ]


def test_dict_candidates_with_distinct_ids_are_not_merged() -> None:
    """Synapse 的候选是不带行号的字典；同文件同名、不同符号 id 不能合并。"""
    first = {"name": "inner", "file": "pulse.py", "id": 11}
    second = {"name": "inner", "file": "pulse.py", "id": 12}
    resolver = CalleeResolver(
        functions_by_name={"inner": [first, second]},
        functions_by_file={"pulse.py": [first, second]},
        name_to_source={},
    )

    assert [item["id"] for item, _ in resolver.resolve_items("inner", "x.py")] == [
        11,
        12,
    ]


def test_same_identity_reached_twice_is_still_deduplicated() -> None:
    """身份相同（同一符号 id）的候选经本地与全局两档到达时只保留一次。"""
    local = {"name": "run", "file": "main.py", "id": 7}
    same_symbol = {"name": "run", "file": "main.py", "id": 7}
    resolver = CalleeResolver(
        functions_by_name={"run": [same_symbol]},
        functions_by_file={"main.py": [local]},
        name_to_source={"main.py": {"run": "main.py"}},
    )

    assert resolver.resolve_items("run", "main.py") == [(local, 1.0)]


def test_bare_global_call_to_two_same_name_definitions_is_only_possible() -> None:
    """唯一候选才能成为确定边；两个同名定义时调用只能是 possible。"""
    first, second = _two_inner_refs()
    caller_ref = FunctionRef("other.py", "other", 1, "python", end_line=2)
    resolver = CachedEdgeResolver(
        functions_by_name={"inner": [first, second], "other": [caller_ref]},
        functions_by_file={"pulse.py": [first, second], "other.py": [caller_ref]},
        file_import_map={},
    )

    targets = resolver.resolve(
        {
            "callee_name": "inner",
            "callee_full": "inner",
            "callee_resolution": "unknown",
        },
        "other.py",
    )

    assert targets.certain == []
    assert targets.possible == [first, second]


def test_index_does_not_bind_bare_call_to_one_of_two_same_name_definitions(
    tmp_path: Path,
) -> None:
    """索引期 single-global 规则：两个同名嵌套 ``inner`` 不再被当成唯一定义。"""
    (tmp_path / "pulse.py").write_text(_NESTED_SAME_NAME, encoding="utf-8")
    (tmp_path / "other.py").write_text(
        "def other(x):\n    return inner(x)\n", encoding="utf-8"
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
        conn = sqlite3.connect(cache.db_path)
        try:
            row = conn.execute(
                "SELECT callee_resolution, callee_symbol_id FROM edges "
                "WHERE kind='calls' AND file_path='other.py' AND callee_name='inner'"
            ).fetchone()
        finally:
            conn.close()
    finally:
        cache.close()

    assert row == ("unknown", None)


def _two_execute_methods() -> tuple[FunctionRef, FunctionRef, FunctionRef]:
    run = FunctionRef("main.py", "run", 1, "python", end_line=3)
    first = FunctionRef("tools.py", "execute", 2, "python", receiver="A", end_line=3)
    second = FunctionRef("tools.py", "execute", 6, "python", receiver="B", end_line=7)
    return run, first, second


async def _visualize(graph: object, fmt: str) -> dict:
    from unittest.mock import patch

    from tree_sitter_analyzer.mcp.tools.codegraph_visualize_tool import (
        CodeGraphVisualizeTool,
    )

    tool = CodeGraphVisualizeTool(str(Path(__file__).resolve().parents[2]))
    with patch.object(tool, "get_call_graph", return_value=graph):
        return await tool.execute(
            {
                "mode": "function",
                "function": "run",
                "depth": 1,
                "visualization_format": fmt,
                "output_format": "json",
            }
        )


def _graph_calling(run: FunctionRef, *callees: FunctionRef) -> object:
    from unittest.mock import MagicMock

    graph = MagicMock()
    graph.resolve_targets.return_value = [run]
    graph.callee_refs_of.side_effect = lambda ref: list(callees) if ref is run else []
    graph.caller_refs_of.return_value = []
    return graph


async def test_visualize_sigma_keeps_same_name_methods_as_distinct_nodes() -> None:
    run, first, second = _two_execute_methods()
    result = await _visualize(_graph_calling(run, first, second), "sigma")

    nodes = {
        node["key"]: (node["attributes"]["receiver"], node["attributes"]["line"])
        for node in result["graph"]["nodes"]
    }
    assert nodes == {
        "main_py__run_1": (None, 1),
        "tools_py__A_execute_2": ("A", 2),
        "tools_py__B_execute_6": ("B", 6),
    }
    assert result["stats"]["node_count"] == 3
    assert len(result["graph"]["edges"]) == 2


async def test_visualize_mermaid_keeps_same_name_methods_as_distinct_nodes() -> None:
    run, first, second = _two_execute_methods()
    result = await _visualize(_graph_calling(run, first, second), "mermaid")

    mermaid = result["mermaid"]
    assert 'tools_py__A_execute_2["tools.py::A.execute:2"]' in mermaid
    assert 'tools_py__B_execute_6["tools.py::B.execute:6"]' in mermaid
    assert "main_py__run_1 --> tools_py__A_execute_2" in mermaid
    assert "main_py__run_1 --> tools_py__B_execute_6" in mermaid
