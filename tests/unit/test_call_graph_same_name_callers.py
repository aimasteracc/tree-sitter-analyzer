"""#1596：同一文件中同名的两个调用方不得被合并为一条。

实测（dogfood 第 3 轮）：``nav callers apply_budget`` 只列出一次 ``execute``，
而 ``PulseTool.execute`` 与 ``PulseBatchTool.execute``（pulse_tool.py:188、:325）
各调用一次。缓存调用图按“同文件第一个同名函数”绑定调用方，丢掉了第二个。
调用方的身份必须包含所在类（或定义行）。
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.call_graph import CachedCallGraph, CallGraph, FunctionRef
from tree_sitter_analyzer.call_graph_binding import pick_caller_ref
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_PULSE = (
    "def apply_budget(x):\n"
    "    return x\n\n\n"
    "class PulseTool:\n"
    "    def execute(self, a):\n"
    "        return apply_budget(a)\n\n\n"
    "class PulseBatchTool:\n"
    "    def execute(self, a):\n"
    "        return apply_budget(a)\n"
)


@pytest.fixture
async def pulse_root(tmp_path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "pulse.py").write_text(_PULSE, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(tmp_path)


@pytest.mark.asyncio
async def test_cached_graph_keeps_both_same_name_callers(pulse_root) -> None:
    # #1596：两个类各有一个 `execute`，各自调用目标一次 → 两条调用方。
    tool = CodeGraphCallersTool(pulse_root)
    cache = tool._try_get_cache()
    assert cache is not None
    graph = CachedCallGraph(pulse_root, cache=cache, fallback=False)

    callers = graph.callers_of("apply_budget")

    assert [(c["name"], c["line"], c.get("receiver")) for c in callers] == [
        ("execute", 6, "PulseTool"),
        ("execute", 11, "PulseBatchTool"),
    ]


@pytest.mark.asyncio
async def test_sql_path_keeps_both_same_name_callers(pulse_root) -> None:
    # #1596：SQL 路径的去重键含定义行，两条都应保留（CLI 与 MCP 共用此工具）。
    result = await CodeGraphCallersTool(pulse_root).execute(
        {"function_name": "apply_budget", "include_bodies": False}
    )

    assert result["caller_count"] == 2
    assert sorted((c["name"], c["line"]) for c in result["callers"]) == [
        ("execute", 6),
        ("execute", 11),
    ]


def _ref(name: str, line: int, end: int, receiver: str | None = None) -> FunctionRef:
    return FunctionRef("pulse.py", name, line, "python", receiver, end)


def test_pick_caller_ref_prefers_the_exact_definition_line() -> None:
    # #1596：定义行精确匹配优先；其次是包含该行的函数；最后才退回同文件第一个。
    first = _ref("execute", 6, 7, "PulseTool")
    second = _ref("execute", 11, 12, "PulseBatchTool")
    elsewhere = FunctionRef("other.py", "execute", 11, "python")
    candidates = [elsewhere, first, second]

    assert pick_caller_ref(candidates, "pulse.py", 11) is second
    assert pick_caller_ref(candidates, "pulse.py", 7) is first
    assert pick_caller_ref(candidates, "pulse.py", 0) is first
    assert pick_caller_ref(candidates, "missing.py", 11) is elsewhere
    assert pick_caller_ref([], "pulse.py", 11) is None


def test_callers_of_does_not_merge_same_name_refs_without_receiver() -> None:
    # #1596：没有 receiver 的同名函数（例如两个嵌套 `inner`）按定义行区分。
    graph = CallGraph(".")
    target = _ref("apply_budget", 1, 2)
    inner_a = _ref("inner", 5, 6)
    inner_b = _ref("inner", 9, 10)
    graph._func_by_name["apply_budget"].append(target)
    graph._callers[target].extend([inner_a, inner_b])
    graph._built = True

    assert [c["line"] for c in graph.callers_of("apply_budget")] == [5, 9]


def _nested_graph() -> CallGraph:
    """#1619：run → 两个同名嵌套 inner（无 receiver），各自再调用 log_a / log_b。"""
    graph = CallGraph(".")
    run = _ref("run", 1, 2)
    inner_a, inner_b = _ref("inner", 5, 6), _ref("inner", 9, 10)
    graph._func_by_name["run"].append(run)
    graph._func_by_file["pulse.py"].append(run)
    graph._callees[run].extend([inner_a, inner_b])
    graph._callees[inner_a].append(_ref("log_a", 13, 14))
    graph._callees[inner_b].append(_ref("log_b", 17, 18))
    graph._callers[run].extend([inner_a, inner_b])
    graph._built = True
    return graph


def test_call_chain_keeps_both_same_name_callees() -> None:
    # #1619：边去重键按身份；按 qualified_name 时 run->inner 只走一次，丢掉 log_b。
    chain = _nested_graph().call_chain("run", depth=2)

    assert [(e["callee"]["name"], e["callee"]["line"]) for e in chain] == [
        ("inner", 5),
        ("inner", 9),
        ("log_a", 13),
        ("log_b", 17),
    ]


def test_file_impact_counts_both_same_name_callers() -> None:
    # #1619：file_impact 的上游去重按身份，两个同名嵌套 inner 都计入。
    assert _nested_graph().file_impact("pulse.py")["upstream_count"] == 2
