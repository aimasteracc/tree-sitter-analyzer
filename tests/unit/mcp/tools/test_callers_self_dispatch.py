"""#1635：基类里的 ``self.hook()`` 是 ``Base.hook`` 的调用方；子类覆写时也可能是
``Sub.hook`` 的调用方。

dogfood 第 6 轮：``Base.run`` 调用 ``self.hook()``，``Sub`` 覆写 ``hook``——
``Base.hook`` 得到 0 个调用方（``unknown``），属于召回缺口。``self`` 的静态类型
就是外围类，因此调用点至少绑定到外围类自己的方法；动态分派可能落到任何覆写，
所以覆写方必须保持非 complete（除非边已归属给它）。
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_BASE = (
    "class Base:\n"
    "    def run(self):\n"
    "        return self.hook()\n\n"
    "    def hook(self):\n"
    "        return 1\n\n\n"
    "class Sub(Base):\n"
    "    def hook(self):\n"
    "        return super().hook() + 1\n\n"
    "    def other(self):\n"
    "        return self.hook()\n\n\n"
    "def drive(obj):\n"
    "    return obj.hook()\n"
)
#: 另一个文件里的覆写：``Base.run`` 的 ``self.hook()`` 同样可能分派到它。
_LEAF = (
    "from base import Base\n\n\n"
    "class Leaf(Base):\n"
    "    def hook(self):\n"
    "        return 3\n"
)
#: 无覆写的对照：``self.ping()`` 只可能是 ``Solo.ping``。
_SOLO = (
    "class Solo:\n"
    "    def start(self):\n"
    "        return self.ping()\n\n"
    "    def ping(self):\n"
    "        return 0\n"
)


@pytest.fixture
async def hook_root(tmp_path):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "base.py").write_text(_BASE, encoding="utf-8")
    (tmp_path / "leaf.py").write_text(_LEAF, encoding="utf-8")
    (tmp_path / "solo.py").write_text(_SOLO, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


def _names(result: dict) -> set[tuple[str, int]]:
    return {(c["name"], c["line"]) for c in result["callers"]}


@pytest.mark.asyncio
async def test_self_call_in_base_is_a_caller_of_base_method(hook_root) -> None:
    # #1635：`Base.run` 的 `self.hook()` 绑定到外围类自己的 `Base.hook`。
    result = await _callers(hook_root, "Base.hook")

    # `Sub.hook`（第 10 行）的 `super().hook()` 同样指向 `Base.hook`。
    assert {("run", 2), ("hook", 10)} <= _names(result)
    assert result["caller_count"] == len(result["callers"])


@pytest.mark.asyncio
async def test_base_method_with_super_call_is_not_complete(hook_root) -> None:
    # 负对照：`super().hook()`、`obj.hook()` 都可能到达 `Base.hook` 却未归属，
    # 因此调用方列表不是普查。
    result = await _callers(hook_root, "Base.hook")

    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_override_in_same_file_is_not_complete(hook_root) -> None:
    # #1635：`Base.run` 的 `self.hook()` 可能分派到 `Sub.hook`——不得答 complete。
    result = await _callers(hook_root, "Sub.hook")

    assert result["completeness"] != "complete"
    assert result["completeness_reason"] is not None


@pytest.mark.asyncio
async def test_self_call_in_subclass_binds_to_its_own_override(hook_root) -> None:
    # #1635：`Sub.other` 的 `self.hook()` 静态类型是 `Sub`，绑定到 `Sub.hook`。
    result = await _callers(hook_root, "Sub.hook")

    assert ("other", 13) in _names(result)


@pytest.mark.asyncio
async def test_override_in_other_file_is_not_complete(hook_root) -> None:
    # 负对照：另一个文件里的覆写同样可能被基类的 `self.hook()` 分派到。
    result = await _callers(hook_root, "Leaf.hook")

    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_super_call_is_not_bound_to_the_caller_itself(hook_root) -> None:
    # 负对照：`Sub.hook` 里的 `super().hook()` 不是对 `Sub.hook` 自身的调用。
    result = await _callers(hook_root, "Sub.hook")

    assert ("hook", 10) not in _names(result)


@pytest.mark.asyncio
async def test_self_call_without_override_stays_resolved(hook_root) -> None:
    # 对照：没有覆写时 `self.ping()` 只可能是 `Solo.ping`。
    result = await _callers(hook_root, "Solo.ping")

    assert _names(result) == {("start", 2)}


@pytest.mark.asyncio
async def test_cross_file_override_reached_only_by_self_call(tmp_path) -> None:
    # #1635：唯一指向 `hook` 的调用是基类里的 `self.hook()`——修复前 `Leaf.hook`
    # 答 `complete, 0`（假的 complete），`Base.hook` 则正确地有 1 个调用方。
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "base.py").write_text(
        "class Base:\n"
        "    def run(self):\n"
        "        return self.hook()\n\n"
        "    def hook(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "leaf.py").write_text(_LEAF, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True

    leaf = await _callers(str(tmp_path), "Leaf.hook")
    assert (leaf["caller_count"], leaf["completeness"]) == (0, "unknown")
    assert leaf["completeness_reason"] == "NAME_ONLY_INBOUND"
    base = await _callers(str(tmp_path), "Base.hook")
    assert _names(base) == {("run", 2)}
