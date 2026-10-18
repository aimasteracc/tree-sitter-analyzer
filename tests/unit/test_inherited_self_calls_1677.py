"""#1677：``self.m()`` 调用跨文件基类上继承来的方法，必须归属到 MRO 中最近的定义。

经公开的 ``nav callers``（``CodeGraphCallersTool``）在已索引的夹具上验证：
MRO 完全已知（每个基类都解析到项目类）时，最近的定义是确定调用方；
基类未解析时只是可能调用方；更下层子类的覆写仍只是可能目标（#1648）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_BASE = (
    "class Base:\n"
    "    def reset(self):\n"
    "        return 1\n\n"
    "    def shared(self):\n"
    "        return 2\n\n\n"
    # 同一文件里另一个类的同名方法：持久化的文件解析不足以区分，须按 MRO 绑定。
    "class Unrelated:\n"
    "    def reset(self):\n"
    "        return 4\n"
)
_CHILD = (
    "from base import Base\n\n\n"
    "class Child(Base):\n"
    "    def run(self):\n"
    "        return self.reset()\n\n"
    "    def again(self):\n"
    "        return self.shared()\n\n\n"
    "class GrandChild(Child):\n"
    "    def shared(self):\n"
    "        return 3\n\n"
    "    def deep(self):\n"
    "        return self.reset()\n"
)
_EXT = (
    "from somewhere_external import ExternalBase\n\n\n"
    "class Mixed(ExternalBase):\n"
    "    def go(self):\n"
    "        return self.reset()\n"
)
_OTHER = "class Other:\n    def reset(self):\n        return 0\n"


@pytest.fixture
async def mro_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "base.py").write_text(_BASE, encoding="utf-8")
    (tmp_path / "child.py").write_text(_CHILD, encoding="utf-8")
    (tmp_path / "ext.py").write_text(_EXT, encoding="utf-8")
    (tmp_path / "other.py").write_text(_OTHER, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str, file_path: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "file_path": file_path, "include_bodies": False}
    )


def _lines(result: dict) -> dict[str, int]:
    return {entry["name"]: entry["line"] for entry in result["callers"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Base.reset", "reset"])
async def test_inherited_self_call_is_a_certain_caller(
    mro_root: str, name: str
) -> None:
    result = await _callers(mro_root, name, "base.py")

    assert _lines(result) == {"run": 5, "deep": 16}
    if name == "Base.reset":
        # `Mixed(ExternalBase)` 的 MRO 未知：`self.reset()` 只是可能调用方。
        assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_unresolved_base_is_only_possible(mro_root: str) -> None:
    from tree_sitter_analyzer.call_graph import CachedCallGraph

    cache = CodeGraphCallersTool(mro_root)._try_get_cache()
    graph = CachedCallGraph(mro_root, cache=cache, fallback=False)

    possible = {c["name"] for c in graph.possible_callers_of("Base.reset", "base.py")}

    assert "go" in possible
    assert {c["name"] for c in graph.callers_of("Base.reset", "base.py")} == {
        "run",
        "deep",
    }


@pytest.mark.asyncio
async def test_override_further_down_stays_possible(mro_root: str) -> None:
    base = await _callers(mro_root, "Base.shared", "base.py")
    override = await _callers(mro_root, "GrandChild.shared", "child.py")

    assert _lines(base) == {"again": 8}
    assert override["caller_count"] == 0
    assert override["completeness"] != "complete"


@pytest.mark.asyncio
async def test_unrelated_same_name_method_gains_no_caller(mro_root: str) -> None:
    result = await _callers(mro_root, "Other.reset", "other.py")

    assert result["caller_count"] == 0
    assert result["completeness"] != "complete"


def test_hierarchy_rules() -> None:
    from tree_sitter_analyzer.class_mro import ClassKey, Hierarchy, external_lacks

    a, b, c, d = (ClassKey("m.py", name) for name in "ABCD")
    hierarchy = Hierarchy(
        parents={b: [a], c: [a], d: [b, c], a: ["ABC"]},
        methods={a: {"m": 1}, c: {"m": 2}, b: {"n": 3}},
    )
    # C3：D -> B -> C -> A，C 的 m 比 A 的更近。
    assert hierarchy.nearest(d, "m") == (c, True)
    assert hierarchy.nearest(b, "n") == (b, True)
    assert hierarchy.nearest(b, "absent") == (None, True)

    inconsistent = Hierarchy(parents={d: [a, b], b: [a]}, methods={a: {"m": 1}})
    assert inconsistent.nearest(d, "m") == (a, False)
    cyclic = Hierarchy(parents={a: [b], b: [a]}, methods={b: {"m": 1}})
    assert cyclic.nearest(a, "m")[1] is False
    unknown = Hierarchy(parents={a: ["thirdparty.Base"]}, methods={})
    assert unknown.nearest(a, "m") == (None, False)

    assert external_lacks("Generic[T]", "reset") is True
    assert external_lacks("Exception", "with_traceback") is False
    assert external_lacks("collections.abc.Mapping", "reset") is True
    assert external_lacks("thirdparty.Base", "reset") is False
    assert external_lacks("NotAName", "reset") is False


def test_load_hierarchy_tolerates_a_broken_index() -> None:
    import sqlite3

    from tree_sitter_analyzer.cache.inherited_self_calls import (
        resolve_inherited_self_calls,
    )
    from tree_sitter_analyzer.class_mro import load_hierarchy

    conn = sqlite3.connect(":memory:")
    assert load_hierarchy(conn).parents == {}
    assert resolve_inherited_self_calls(conn) == 0
