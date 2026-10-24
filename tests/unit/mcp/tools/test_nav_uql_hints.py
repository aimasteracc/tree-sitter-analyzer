"""uql 采用提示：callers 之后逐个追问调用方时，nav 指向一次 ``search action=uql``。

单跳调用的响应不变 (不为提示付字节)；只有检测到 "callers → 对其调用方 test_map /
callers" 的序列时才追加提示，且提示中的查询必须能被 UQL 解析器接受。
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.codegraph_impact_tool import CodeGraphImpactTool
from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade
from tree_sitter_analyzer.mcp.tools.nav_uql_hints import (
    CallerFollowUps,
    append_next_step,
    hint_after_callers,
    hint_after_test_map,
    hint_for_caller_tree,
    uql_literal,
)
from tree_sitter_analyzer.uql.errors import Ok
from tree_sitter_analyzer.uql.parser import parse_query

_QUERY = re.compile(r'query="([^"]+)"')


def _callers_payload(*names: str, cls: str | None = None) -> dict[str, Any]:
    callers = [{"name": n, "file": "src/a.py", "line": i} for i, n in enumerate(names)]
    if cls is not None:
        for entry in callers:
            entry["class"] = cls
    return {
        "success": True,
        "verdict": "INFO",
        "callers": callers,
        "agent_summary": {"next_step": "Review callers above."},
    }


def _query_of(hint: str) -> str:
    match = _QUERY.search(hint)
    assert match, hint
    return match.group(1)


# ── memory ──────────────────────────────────────────────────────────────────


def test_source_of_finds_a_listed_caller_bare_or_qualified() -> None:
    memory = CallerFollowUps()
    memory.record("target", _callers_payload("helper", cls="Svc"))
    assert memory.source_of("helper") == "target"
    assert memory.source_of("Svc.helper") == "target"
    assert memory.source_of("Other.helper") == "target"  # bare name matches
    assert memory.source_of("unrelated") is None


def test_the_queried_symbol_itself_is_not_a_follow_up() -> None:
    memory = CallerFollowUps()
    memory.record("rec", _callers_payload("rec"))  # recursion lists itself
    assert memory.source_of("rec") is None


def test_memory_ignores_unusable_input() -> None:
    memory = CallerFollowUps()
    memory.record(None, _callers_payload("a"))
    memory.record("x", {"success": False, "error": "boom"})
    memory.record("y", "not a dict")
    memory.record(
        "z", {"callers": [{"name": "<module>"}, "junk", {"name": 3}, {"name": ""}]}
    )
    assert memory.source_of("a") is None
    assert memory.source_of(None) is None
    assert memory.source_of("") is None


def test_memory_is_bounded_and_prefers_the_latest_answer() -> None:
    memory = CallerFollowUps()
    memory.record("first", _callers_payload("shared", "old_only"))
    for i in range(4):
        memory.record(f"s{i}", _callers_payload("shared"))
    assert memory.source_of("old_only") is None  # evicted after 4 newer answers
    assert memory.source_of("shared") == "s3"


def test_names_per_answer_are_capped() -> None:
    memory = CallerFollowUps()
    memory.record("t", _callers_payload(*(f"f{i}" for i in range(600))))
    assert memory.source_of("f10") == "t"
    assert memory.source_of("f599") is None


# ── hint text ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "hint",
    [
        hint_after_test_map("raw_to_path"),
        hint_after_callers("Cls.method"),
        hint_for_caller_tree("export_html", 3),
    ],
)
def test_every_hint_names_a_query_the_uql_parser_accepts(hint: str | None) -> None:
    assert hint and "search action=uql" in hint
    assert isinstance(parse_query(_query_of(hint)), Ok)


def test_caller_tree_depth_is_clamped_to_the_impact_range() -> None:
    assert "impact(depth=10)" in hint_for_caller_tree("f", 50)
    assert "impact(depth=1)" in hint_for_caller_tree("f", 0)


def test_names_that_cannot_be_quoted_get_no_hint() -> None:
    assert uql_literal("it's") is None
    assert hint_after_test_map("a b") is None
    assert hint_after_callers("x'y") is None
    assert hint_for_caller_tree("renders correctly", 2) == ""


def test_append_next_step_appends_creates_and_skips_failures() -> None:
    base = {"success": True, "agent_summary": {"next_step": "A."}}
    out = append_next_step(base, "B.")
    assert out["agent_summary"]["next_step"] == "A. B."
    assert base["agent_summary"]["next_step"] == "A."  # input not mutated
    assert append_next_step({"success": True}, "B.")["agent_summary"] == {
        "next_step": "B."
    }
    failed = {"success": False, "error": "x"}
    assert append_next_step(failed, "B.") is failed
    assert append_next_step(base, None) is base
    assert append_next_step("text", "B.") == "text"


# ── through the nav facade ──────────────────────────────────────────────────


def _inner(facade: Any, kind: type) -> Any:
    for inner in facade._bespoke_inners:
        if type(inner) is kind:
            return inner
    raise AssertionError(f"{kind.__name__} not registered")


def _facade_with_fakes() -> Any:
    facade = build_nav_facade(project_root=None)
    callers = _inner(facade, CodeGraphCallersTool)
    callers.execute = AsyncMock(
        side_effect=lambda args: _callers_payload(
            *(
                {"target": ["helper"], "helper": ["outer"]}.get(
                    args["function_name"], []
                )
            )
        )
    )
    graph = MagicMock()
    graph.resolve_targets.return_value = [
        FunctionRef(
            file_path="src/a.py", name="helper", start_line=1, language="python"
        )
    ]
    graph.caller_refs_of.return_value = [
        FunctionRef(
            file_path="tests/test_a.py",
            name="test_helper",
            start_line=3,
            language="python",
        )
    ]
    graph.possible_caller_refs_of.return_value = []
    _inner(facade, CodeGraphImpactTool)._call_graph = graph
    return facade


@pytest.mark.asyncio
async def test_a_lone_test_map_or_callers_call_is_unchanged() -> None:
    facade = _facade_with_fakes()
    tm = await facade.execute({"action": "test_map", "symbol": "helper"})
    assert "action=uql" not in tm["agent_summary"]["next_step"]
    callers = await facade.execute({"action": "callers", "function_name": "target"})
    assert callers["agent_summary"]["next_step"] == "Review callers above."


@pytest.mark.asyncio
async def test_test_map_on_a_listed_caller_points_at_uql() -> None:
    facade = _facade_with_fakes()
    await facade.execute({"action": "callers", "function_name": "target"})
    tm = await facade.execute({"action": "test_map", "symbol": "helper"})
    step = tm["agent_summary"]["next_step"]
    assert step.startswith("Run per-file tests: pytest tests/test_a.py.")
    assert "symbol('target').callers().tests()" in step


@pytest.mark.asyncio
async def test_callers_of_a_listed_caller_points_at_a_depth_query() -> None:
    facade = _facade_with_fakes()
    await facade.execute({"action": "callers", "function_name": "target"})
    second = await facade.execute({"action": "callers", "symbol": "helper"})
    step = second["agent_summary"]["next_step"]
    assert step.startswith("Review callers above. ")
    assert "symbol('target').callers(depth=2)" in step
