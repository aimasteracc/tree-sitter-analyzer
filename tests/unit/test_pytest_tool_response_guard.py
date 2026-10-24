"""Unit tests for ``tests/pytest_tool_response_guard.py``."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests import pytest_tool_response_guard as guard
from tree_sitter_analyzer.mcp.tools.tool_response import ENVELOPE_RULES

BAD = {"success": True, "verdict": "NO_PATH"}
GOOD = {"success": True, "verdict": "SAFE"}


def _tool(module: str, response: dict[str, Any], *, facade: str | None = None):
    """A fake tool class whose ``__module__`` decides production vs double."""

    async def execute(self: Any, arguments: Any) -> dict[str, Any]:
        return response

    namespace: dict[str, Any] = {
        "__module__": module,
        "execute": guard.guard_execute(execute),
        "get_tool_definition": lambda self: {"name": "fake_tool"},
    }
    if facade is not None:
        namespace["facade_name"] = facade
    return type("FakeTool", (), namespace)()


@pytest.fixture
def state(monkeypatch: pytest.MonkeyPatch) -> guard._State:
    fresh = guard._State(mode="enforce", current="node::test")
    monkeypatch.setattr(guard, "_STATE", fresh)
    return fresh


def _run(tool: Any, arguments: Any = None) -> Any:
    return asyncio.run(tool.execute(arguments or {}))


def test_production_violation_is_recorded(state: guard._State) -> None:
    _run(_tool("tree_sitter_analyzer.mcp.tools.fake", BAD))
    found = state.found["node::test"]
    assert [(v.tool, v.rule) for v in found] == [("fake_tool", "base")]
    assert state.checked == 1


def test_conforming_response_records_nothing(state: guard._State) -> None:
    _run(_tool("tree_sitter_analyzer.mcp.tools.fake", GOOD))
    assert state.found == {}
    assert state.checked == 1


def test_test_double_is_not_checked(state: guard._State) -> None:
    _run(_tool("tests.unit.fakes", BAD))
    assert state.found == {}
    assert state.checked == 0


def test_facade_label_includes_action(state: guard._State) -> None:
    _run(
        _tool("tree_sitter_analyzer.mcp.tools.fake", BAD, facade="nav"),
        {"action": "call_path"},
    )
    assert state.found["node::test"][0].tool == "nav action=call_path"


def test_only_outermost_production_call_is_checked(state: guard._State) -> None:
    inner = _tool("tree_sitter_analyzer.mcp.tools.inner", BAD)

    async def outer_execute(self: Any, arguments: Any) -> dict[str, Any]:
        await inner.execute(arguments)
        return GOOD

    outer_cls = type(
        "Outer",
        (),
        {
            "__module__": "tree_sitter_analyzer.mcp.tools.outer",
            "execute": guard.guard_execute(outer_execute),
            "get_tool_definition": lambda self: {"name": "outer"},
        },
    )
    _run(outer_cls())
    assert state.found == {}
    assert state.checked == 1


def test_production_wrapping_a_double_is_skipped(state: guard._State) -> None:
    double = _tool("tests.unit.fakes", GOOD)

    async def outer_execute(self: Any, arguments: Any) -> dict[str, Any]:
        await double.execute(arguments)
        return BAD

    outer_cls = type(
        "Outer",
        (),
        {
            "__module__": "tree_sitter_analyzer.mcp.tools.outer",
            "execute": guard.guard_execute(outer_execute),
        },
    )
    _run(outer_cls())
    assert state.found == {}
    assert state.checked == 0


def test_guard_execute_is_idempotent() -> None:
    async def execute(self: Any, arguments: Any) -> None:
        return None

    once = guard.guard_execute(execute)
    assert guard.guard_execute(once) is once


def test_allowlist_matches_tool_pattern_and_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = {"tool": "nav action=*", "rule": "base", "issue": "#1", "reason": "x"}
    monkeypatch.setattr(guard, "ALLOWLIST", [entry])
    assert guard.allowlisted(guard.Violation("nav action=call_path", "base", "")) == 0
    assert (
        guard.allowlisted(guard.Violation("nav action=call_path", "error-code", ""))
        is None
    )
    assert guard.allowlisted(guard.Violation("search", "base", "")) is None


def test_triage_drops_allowlisted_and_duplicates(
    state: guard._State, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = {"tool": "nav*", "rule": "base", "issue": "#1", "reason": "x"}
    monkeypatch.setattr(guard, "ALLOWLIST", [entry])
    allowed = guard.Violation("nav action=x", "base", "m")
    failing = guard.Violation("search", "error-code", "m")
    result = guard.ToolResponseGuard()._triage("n", [allowed, failing, failing])
    assert result == [failing]
    assert state.allowlist_hits == {0}


def test_failure_message_names_tool_rule_and_fix() -> None:
    text = guard._describe("n::t", [guard.Violation("nav action=x", "base", "bad")])
    assert "nav action=x: [base] bad" in text
    assert "tests/tool_response_allowlist.py" in text


def test_invalid_mode_is_a_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(guard.MODE_ENV, "loud")
    monkeypatch.setattr(guard, "_STATE", guard._State(mode="off"))
    with pytest.raises(pytest.UsageError, match=guard.MODE_ENV):
        guard.install(object())  # type: ignore[arg-type]


def test_reported_rules_are_declared(state: guard._State) -> None:
    payload = {"success": False, "error": "x", "verdict": "SAFE", "truncated": 1}
    _run(_tool("tree_sitter_analyzer.mcp.tools.fake", payload))
    rules = {v.rule for v in state.found["node::test"]}
    assert rules == {"failure-verdict", "error-code", "truncation"}
    assert rules <= ENVELOPE_RULES
