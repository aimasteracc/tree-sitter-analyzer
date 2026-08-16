"""RFC-0022 Phase A experiment harness contract (NO1-010A).

Exact pins for the internal harness bridge: strict decoded-request
validation (unknown fields rejected -> INVALID_REQUEST mapping), exact
primitive dispatch to the same-process MCP adapters, and the internal CLI
smoke entry.
"""

from __future__ import annotations

import asyncio

import pytest

from tree_sitter_analyzer.task_harness import (
    McpPrimitiveExecutor,
    request_from_dict,
)


def test_request_from_dict_understand() -> None:
    request = request_from_dict(
        "understand", {"task": "explain dispatch", "profile": "compact"}
    )
    assert request.task == "explain dispatch"
    assert request.budget.profile == "compact"


def test_request_from_dict_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="unknown request fields"):
        request_from_dict("understand", {"task": "x", "sneaky": True})
    with pytest.raises(ValueError, match="unknown budget fields"):
        request_from_dict("understand", {"task": "x", "budget": {"sneaky": 1}})
    with pytest.raises(ValueError, match="unknown diff fields"):
        request_from_dict(
            "assess_change", {"diff": {"source": "workspace", "extra": 1}}
        )


def test_request_from_dict_plan_change_one_of() -> None:
    task_request = request_from_dict("plan_change", {"task": "refactor x"})
    assert task_request.task == "refactor x"
    diff_request = request_from_dict(
        "plan_change",
        {"diff": {"source": "staged", "scope_paths": ["src/"]}},
    )
    assert diff_request.diff.source == "staged"
    assert diff_request.diff.scope_paths == ("src/",)


def test_request_from_dict_invalid_payloads_raise() -> None:
    with pytest.raises(ValueError, match="task must not be empty"):
        request_from_dict("understand", {"task": "  "})
    with pytest.raises(ValueError, match="exactly one of task or diff"):
        request_from_dict("plan_change", {})
    with pytest.raises(ValueError, match="exactly one diff"):
        request_from_dict("assess_change", {})


def test_executor_dispatches_to_pinned_adapters(monkeypatch) -> None:
    """The harness wires the real same-process adapters, not new ones."""
    import tree_sitter_analyzer.task_harness as harness

    seen: list[tuple[str, str, dict]] = []

    class FakeTool:
        async def execute(self, arguments):
            seen.append(arguments)
            return {"success": True, "action_version": "fake/v1"}

    class FakeFacade:
        async def execute(self, arguments):
            seen.append(arguments)
            return {"success": True, "action_version": "fake/v1"}

    monkeypatch.setattr(harness, "CodeGraphStatusTool", lambda root: FakeTool())
    monkeypatch.setattr(harness, "CodeGraphContextTool", lambda root: FakeTool())
    monkeypatch.setattr(harness, "build_edit_facade", lambda root: FakeFacade())
    monkeypatch.setattr(harness, "ChangeImpactTool", lambda root: FakeTool())

    executor = McpPrimitiveExecutor(".")
    assert asyncio.run(executor.call("index", "status", {"output_format": "json"})) == {
        "success": True,
        "action_version": "fake/v1",
    }
    assert (
        asyncio.run(executor.call("nav", "context", {"task": "x"}))["success"] is True
    )
    result = asyncio.run(executor.call("edit", "safe", {"file_path": "a.py"}))
    assert result["success"] is True
    # edit.* dispatches through the facade with the action key attached.
    assert seen[-1]["action"] == "safe"
    assert seen[-1]["file_path"] == "a.py"


def test_executor_rejects_unknown_primitive() -> None:
    executor = McpPrimitiveExecutor(".")
    with pytest.raises(ValueError, match="unknown primitive"):
        asyncio.run(executor.call("mystery", "action", {}))
