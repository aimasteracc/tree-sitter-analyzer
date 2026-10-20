"""#1699：经单例 / 构造 / 注解 / ``super()`` / 闭包接收者调用继承来的方法时，归属到 MRO 中最近的定义。

经公开的 ``nav callers``（``CodeGraphCallersTool``）在已索引的夹具上验证。
``Sub(Mixin, Base)``：``Mixin.fmt`` 与 ``Base.fmt`` 同名，C3 顺序下 ``Mixin.fmt`` 最近；
``Base.shared`` 只在基类上定义。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_BASE = (
    "class Base:\n"
    "    def shared(self):\n"
    "        return 0\n\n"
    "    def fmt(self):\n"
    "        return 0\n\n\n"
    "class Mixin:\n"
    "    def fmt(self):\n"
    "        return 1\n"
)
_SUB = (
    "from base import Base, Mixin\n\n\n"
    "class Sub(Mixin, Base):\n"
    "    def run(self):\n"
    "        return super().shared()\n\n"
    "    def again(self):\n"
    "        return super().fmt()\n"
)
_USE = (
    "from sub import Sub\n\n"
    "FMT = Sub()\n\n\n"
    "def via_singleton():\n"
    "    return FMT.fmt()\n\n\n"
    "def via_ctor():\n"
    "    s = Sub()\n"
    "    return s.fmt()\n\n\n"
    "def via_param(s: Sub):\n"
    "    return s.fmt()\n\n\n"
    "def outer():\n"
    "    s = Sub()\n\n"
    "    def inner():\n"
    "        return s.shared()\n\n"
    "    return inner()\n\n\n"
    "def shadowed():\n"
    "    s = Sub()\n\n"
    "    def inner2(s):\n"
    "        return s.shared()\n\n"
    "    return inner2(object())\n"
)


@pytest.fixture
async def shapes_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "base.py").write_text(_BASE, encoding="utf-8")
    (tmp_path / "sub.py").write_text(_SUB, encoding="utf-8")
    (tmp_path / "use.py").write_text(_USE, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": "base.py", "include_bodies": False}
    )


def _names(result: dict) -> set[str]:
    return {entry["name"] for entry in result["callers"]}


@pytest.mark.asyncio
async def test_nearest_definition_in_the_mro_wins(shapes_root: str) -> None:
    result = await _callers(shapes_root, "Mixin.fmt")

    # 单例、构造得到的局部变量、参数注解与 super()：都到达 C3 顺序中最近的 Mixin.fmt。
    assert _names(result) == {"via_singleton", "via_ctor", "via_param", "again"}


@pytest.mark.asyncio
async def test_the_shadowed_base_definition_gains_no_caller(shapes_root: str) -> None:
    result = await _callers(shapes_root, "Base.fmt")

    assert result["caller_count"] == 0


@pytest.mark.asyncio
async def test_super_and_closure_receivers_reach_the_base(shapes_root: str) -> None:
    result = await _callers(shapes_root, "Base.shared")

    # `inner2(s)` 的参数 `s` 遮蔽了闭包变量：不是调用方。
    assert _names(result) == {"run", "inner"}


def test_extractor_version_is_bumped_for_receiver_shapes() -> None:
    from tree_sitter_analyzer import ast_cache
    from tree_sitter_analyzer.cache import indexer

    assert (
        ast_cache._AST_CACHE_EXTRACTOR_VERSION,
        indexer._AST_CACHE_EXTRACTOR_VERSION,
    ) == (44, 44)
