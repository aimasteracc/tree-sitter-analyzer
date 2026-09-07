"""FacadeTool 场景化加固测试（变异测试驱动，v1.29.2 轮次二）。

锁定分发框架的精确行为：错误信封逐键精确值、拼写自愈建议、
schema 的枚举与核心参数集、bespoke 优先级、根路径再绑定传播。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.mcp.tools.facade_tool import (
    _CORE_FACADE_PARAMS,
    _FACADE_CONTROL_KEYS,
    FacadeTool,
)


class _RecordingInner(BaseMCPTool):
    """记录收到的参数与根路径重绑的最小内层工具。"""

    def __init__(self, name: str = "inner") -> None:
        super().__init__(None)
        self.seen_args: dict[str, Any] | None = None
        self.rebound_roots: list[str] = []
        self._name = name

    def get_tool_schema(self) -> dict[str, Any]:  # pragma: no cover - 框架接口
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.seen_args = dict(arguments)
        return {"success": True, "verdict": "INFO", "echo": arguments.get("query")}

    def get_tool_definition(self) -> dict[str, Any]:  # pragma: no cover - 框架接口
        return {
            "name": self._name,
            "description": "",
            "inputSchema": self.get_tool_schema(),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:  # pragma: no cover
        return True

    def set_project_path(self, project_root: str | None) -> None:
        self.rebound_roots.append(project_root or "")


async def _run(coro: Any) -> Any:
    return (
        asyncio.get_event_loop().run_until_complete(coro)
        if False
        else asyncio.run(coro)
    )


def _facade(**kwargs: Any) -> tuple[FacadeTool, _RecordingInner]:
    inner = _RecordingInner()
    f = FacadeTool("demo", {"alpha": inner, "beta": _RecordingInner()}, **kwargs)
    return f, inner


def _noop_inner() -> _RecordingInner:
    return _RecordingInner("noop")


# ---------- 场景：错误信封 _action_error ----------


class TestActionErrorEnvelope:
    def _facade_two_actions(self) -> FacadeTool:
        return FacadeTool(
            "demo", {"alpha": _RecordingInner(), "beta": _RecordingInner()}
        )

    def test_无建议时信封逐键精确(self):
        f = self._facade_two_actions()
        env = f._action_error("boom")
        assert env == {
            "success": False,
            "verdict": "ERROR",
            "error_type": "validation",
            "error": "boom",
            "facade": "demo",
            "available_actions": ["alpha", "beta"],
            "suggestion": None,
            "summary_line": "demo: boom",
            "agent_summary": {
                "verdict": "ERROR",
                "summary_line": "demo: boom",
                "next_step": "Set action to one of: alpha, beta.",
            },
        }

    def test_有建议时消息前缀与next_step(self):
        f = self._facade_two_actions()
        env = f._action_error("unknown thing", suggestion="alpha")
        assert env["error"] == "did you mean: alpha? unknown thing"
        assert env["summary_line"] == "demo: did you mean: alpha? unknown thing"
        assert env["suggestion"] == "alpha"
        assert (
            env["agent_summary"]["next_step"]
            == "Did you mean action 'alpha'? Else set action to one of: alpha, beta."
        )

    def test_无注册动作的兜底next_step(self):
        f = FacadeTool("empty", {})
        env = f._action_error("nothing works")
        assert env["available_actions"] == []
        assert (
            env["agent_summary"]["next_step"]
            == "No actions are registered on this facade."
        )

    def test_动作列表排序去重(self):
        # 注册顺序打乱 + bespoke 与 action 重名 → 排序去重后的并集
        f = FacadeTool(
            "demo",
            {"zeta": _RecordingInner(), "alpha": _RecordingInner()},
            {"mid": _noop_bespoke()},
        )
        assert f._available_actions() == ["alpha", "mid", "zeta"]


def _noop_bespoke():
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "bespoke": True, "seen": args}

    return handler


# ---------- 场景：拼写自愈 ----------


class TestClosestAction:
    def _f(self) -> FacadeTool:
        return FacadeTool(
            "demo", {"navigate": _RecordingInner(), "explore": _RecordingInner()}
        )

    def test_近距错拼自愈(self):
        assert self._f()._closest_action("navigte") == "navigate"
        assert self._f()._closest_action("explor") == "explore"

    def test_远距错拼不给建议(self):
        assert self._f()._closest_action("zzzzzz") is None

    def test_精确命中返回自身(self):
        assert self._f()._closest_action("navigate") == "navigate"


# ---------- 场景：execute 分发 ----------


class TestExecuteDispatch:
    def test_缺action(self):
        f, _ = _facade()
        env = asyncio.run(f.execute({}))
        assert env["success"] is False
        assert env["error"] == "missing required parameter 'action'"
        assert env["available_actions"] == ["alpha", "beta"]

    def test_非字符串action(self):
        f, _ = _facade()
        env = asyncio.run(f.execute({"action": 123}))
        assert env["success"] is False
        assert env["error"] == "missing required parameter 'action'"

    def test_未知action带自愈建议(self):
        f = FacadeTool("demo", {"navigate": _RecordingInner()})
        env = asyncio.run(f.execute({"action": "navigte", "query": "x"}))
        assert env["success"] is False
        assert env["suggestion"] == "navigate"
        assert "unknown action 'navigte'" in env["error"]
        assert "valid actions are: navigate" in env["error"]

    def test_内层分发参数透传与原样返回(self):
        f, inner = _facade()
        result = asyncio.run(f.execute({"action": "alpha", "query": "needle"}))
        assert result == {"success": True, "verdict": "INFO", "echo": "needle"}
        assert inner.seen_args is not None
        assert "action" not in inner.seen_args  # 控制键已被剥除

    def test_bespoke优先于同名action_map路由(self):
        inner = _RecordingInner()
        f = FacadeTool("demo", {"dup": inner}, {"dup": _noop_bespoke()})
        result = asyncio.run(f.execute({"action": "dup", "query": "q"}))
        assert result["bespoke"] is True
        assert inner.seen_args is None  # 内层未被触碰

    def test_bespoke收到剥离控制键后的参数(self):
        seen: dict[str, Any] = {}

        async def handler(args: dict[str, Any]) -> int:
            seen.update(args)
            return 42

        FacadeTool("demo", {}, {"count": handler})
        f2 = FacadeTool("demo", {}, {"count": handler})
        result = asyncio.run(
            f2.execute({"action": "count", "symbol": "s", "mode": "x"})
        )
        assert result == 42  # 裸 int 原样转发,不包信封
        # action 被剥、symbol 规范化复制;mode 是核心参数原样透传
        assert seen == {"symbol": "s", "function_name": "s", "mode": "x"}


# ---------- 场景：bespoke 参数清理 ----------


class TestCleanBespokeArgs:
    def test_控制键全部剥离(self):
        # 控制键只有 action;scope/mode 是核心参数,原样透传
        cleaned = FacadeTool._clean_bespoke_args(
            {"action": "a", "scope": "s", "mode": "m", "query": "q"}
        )
        assert cleaned == {"query": "q", "scope": "s", "mode": "m"}

    def test_控制键集合内容锁定(self):
        # 控制键是门面自身的路由键,不该漏进内层;当前仅 action
        assert set(_FACADE_CONTROL_KEYS) == {"action"}

    def test_symbol防御性拷贝到function_name(self):
        cleaned = FacadeTool._clean_bespoke_args({"symbol": "my_func"})
        assert cleaned == {"symbol": "my_func", "function_name": "my_func"}

    def test_显式function_name优先(self):
        cleaned = FacadeTool._clean_bespoke_args(
            {"symbol": "ignored", "function_name": "explicit"}
        )
        assert cleaned == {"symbol": "ignored", "function_name": "explicit"}


# ---------- 场景：公开 schema ----------


class TestPublicSchema:
    def test_枚举为排序并集_必填action_宽松附加(self):
        f = FacadeTool(
            "demo",
            {"zeta": _RecordingInner(), "alpha": _RecordingInner()},
            {"mid": _noop_bespoke()},
        )
        schema = f.get_tool_schema()
        assert schema["type"] == "object"
        assert schema["properties"]["action"]["enum"] == ["alpha", "mid", "zeta"]
        assert schema["required"] == ["action"]
        assert schema["additionalProperties"] is True
        assert (
            "One of: alpha, mid, zeta" in schema["properties"]["action"]["description"]
        )

    def test_核心参数全部声明且不进必填(self):
        f = FacadeTool("demo", {"alpha": _RecordingInner()})
        schema = f.get_tool_schema()
        for key in _CORE_FACADE_PARAMS:
            assert key in schema["properties"], key
            assert key not in schema["required"]

    def test_额外公开参数进schema但不进必填(self):
        f = FacadeTool(
            "demo",
            {"alpha": _RecordingInner()},
            extra_public_params={"kind": {"type": "string", "description": "d"}},
        )
        schema = f.get_tool_schema()
        assert schema["properties"]["kind"] == {"type": "string", "description": "d"}
        assert schema["required"] == ["action"]

    def test_工具定义_默认描述含动作计数与清单(self):
        f = FacadeTool("demo", {"alpha": _RecordingInner(), "beta": _RecordingInner()})
        d = f.get_tool_definition()
        assert d["name"] == "demo"
        assert d["description"] == (
            "Facade dispatching 2 actions via the 'action' parameter: alpha, beta."
        )
        assert d["inputSchema"]["required"] == ["action"]

    def test_工具定义_自定义描述与注解透传(self):
        f = FacadeTool(
            "demo",
            {"alpha": _RecordingInner()},
            description="my facade",
            annotations={"readOnlyHint": False},
        )
        d = f.get_tool_definition()
        assert d["description"] == "my facade"
        assert d["annotations"] == {"readOnlyHint": False}


# ---------- 场景：validate_arguments ----------


class TestValidateArguments:
    def test_合法action返回True(self):
        f = FacadeTool("demo", {"alpha": _RecordingInner()}, {"bes": _noop_bespoke()})
        assert f.validate_arguments({"action": "alpha"}) is True
        assert f.validate_arguments({"action": "bes"}) is True

    def test_缺失action报错文案(self):
        f = FacadeTool("demo", {"alpha": _RecordingInner()})
        with pytest.raises(ValueError, match="missing required parameter 'action'"):
            f.validate_arguments({})

    def test_未知action报错含候选清单(self):
        f = FacadeTool("demo", {"alpha": _RecordingInner()})
        with pytest.raises(ValueError, match="unknown action 'nope'.*alpha"):
            f.validate_arguments({"action": "nope"})


# ---------- 场景：根路径再绑定传播（G3） ----------


class TestRootRebindPropagation:
    def test_内层与bespoke内层都收到重绑(self):
        inner_a, inner_b = _RecordingInner("a"), _RecordingInner("b")
        f = FacadeTool("demo", {"alpha": inner_a}, project_root="/tmp/root1")
        f.register_bespoke_inner(inner_b)
        assert "/tmp/root1" in inner_a.rebound_roots
        assert "/tmp/root1" in inner_b.rebound_roots

    def test_后续根路径变化继续传播(self):
        inner = _RecordingInner()
        f = FacadeTool("demo", {"alpha": inner}, project_root="/tmp/root1")
        f.set_project_path("/tmp/root2")
        assert inner.rebound_roots.count("/tmp/root2") == 1

    def test_根为None时不传播(self):
        inner = _RecordingInner()
        f = FacadeTool("demo", {"alpha": inner})
        inner.rebound_roots.clear()
        f.set_project_path(None)
        assert inner.rebound_roots == []
