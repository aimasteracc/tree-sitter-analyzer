"""#1669：项目里唯一的同名方法，不能把每个接收者未知的 ``x.<name>()`` 都当作确定调用方。

经公开的 ``nav callers``（``CodeGraphCallersTool``）在已索引的夹具上验证：
只有接收者被证明的调用（``self`` / ``cls``、注解或构造得到的类型、导入的模块或类、
类名本身）才是确定调用方；接收者未知的同名调用最多是 ``name_only`` 的可能调用方，
并让答复保持非 ``complete``；影响类消费者仍能经 ``possible_*`` 看到它们。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_HEALTH = (
    "class HealthHistory:\n"
    "    def __init__(self):\n"
    "        self._entries: list = []\n\n"
    "    def append(self, entry):\n"
    "        self._entries.append(entry)\n\n"
    "    def record(self, entry):\n"
    "        self.append(entry)\n\n\n"
    "def make_history():\n"
    "    return HealthHistory()\n"
)
_USERS = (
    "from health import HealthHistory\n\n\n"
    "class Holder:\n"
    "    def __init__(self):\n"
    "        self.x: list = []\n\n"
    "    def add(self, item):\n"
    "        self.x.append(item)\n\n\n"
    "def typed(h: HealthHistory):\n"
    "    h.append(1)\n\n\n"
    "def constructed():\n"
    "    h = HealthHistory()\n"
    "    h.append(2)\n\n\n"
    "def untyped(items):\n"
    "    items.append(3)\n\n\n"
    "def by_class(h):\n"
    "    HealthHistory.append(h, 4)\n\n\n"
    "def chained(owner):\n"
    "    owner.history.append(5)\n\n\n"
    "def fresh():\n"
    "    HealthHistory().append(6)\n\n\n"
    "class Sub(HealthHistory):\n"
    "    pass\n\n\n"
    "def via_sub():\n"
    "    s = Sub()\n"
    "    s.append(7)\n"
)
_FILES = (
    "class Files:\n"
    "    def open(self, path):\n"
    "        return path\n\n\n"
    "def read(path):\n"
    "    return open(path)\n"
)
_MODULES = (
    "import health\n"
    "import health as hh\n\n\n"
    "def via_module():\n"
    "    return health.make_history()\n\n\n"
    "def via_alias():\n"
    "    return hh.make_history()\n"
)

#: ``HealthHistory.append`` 的确定调用方：调用方名 → 定义行。
_CERTAIN = {
    "record": 8,
    "typed": 12,
    "constructed": 16,
    "by_class": 25,
    "fresh": 33,
    "via_sub": 41,
}
#: 接收者未知或已知为别的类型的同名调用：不得成为确定调用方。
_NOT_CERTAIN = ("append", "add", "untyped", "chained")


@pytest.fixture
async def history_root(tmp_path: Path) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "health.py").write_text(_HEALTH, encoding="utf-8")
    (tmp_path / "users.py").write_text(_USERS, encoding="utf-8")
    (tmp_path / "modules.py").write_text(_MODULES, encoding="utf-8")
    (tmp_path / "files.py").write_text(_FILES, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True
    return str(tmp_path)


async def _callers(root: str, name: str, file_path: str | None = None) -> dict:
    arguments: dict = {"function_name": name, "include_bodies": False}
    if file_path is not None:
        arguments["file_path"] = file_path
    return await CodeGraphCallersTool(root).execute(arguments)


def _lines(result: dict) -> dict[str, int]:
    return {entry["name"]: entry["line"] for entry in result["callers"]}


@pytest.mark.asyncio
async def test_only_proven_receivers_are_certain_callers(history_root: str) -> None:
    result = await _callers(history_root, "HealthHistory.append", "health.py")

    assert _lines(result) == _CERTAIN


@pytest.mark.asyncio
async def test_unproven_receivers_keep_the_answer_incomplete(
    history_root: str,
) -> None:
    result = await _callers(history_root, "HealthHistory.append", "health.py")

    assert result["completeness"] == "incomplete"
    assert "NAME_ONLY_INBOUND" in result["completeness_reasons"]


@pytest.mark.asyncio
async def test_bare_file_scoped_query_lists_no_foreign_receiver(
    history_root: str,
) -> None:
    # SQL 路径（裸名 + 文件）：接收者未知的调用不得因持久化的“唯一名”解析而列出。
    result = await _callers(history_root, "append", "health.py")

    assert set(_lines(result)) & set(_NOT_CERTAIN) == set()
    assert result["completeness"] != "complete"


@pytest.mark.asyncio
async def test_unproven_receivers_stay_possible_for_impact(history_root: str) -> None:
    from tree_sitter_analyzer.call_graph import CachedCallGraph
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    cache = CodeGraphCallersTool(history_root)._try_get_cache()
    graph = CachedCallGraph(history_root, cache=cache, fallback=False)

    possible = {
        entry["name"]: entry["match"]
        for entry in graph.possible_callers_of("HealthHistory.append", "health.py")
    }

    # `self.x: list` 的 `append` 同样只按名字可能到达：过近似一侧保留全部同名调用。
    assert possible == {
        "append": "name_only",
        "add": "name_only",
        "untyped": "name_only",
        "chained": "name_only",
    }


@pytest.mark.asyncio
async def test_bare_call_never_binds_to_a_method(history_root: str) -> None:
    # 项目里唯一的 `open` 是方法 `Files.open`：裸调用 `open(path)` 是内建函数。
    result = await _callers(history_root, "Files.open", "files.py")

    assert result["caller_count"] == 0


@pytest.mark.asyncio
async def test_module_receivers_stay_certain(history_root: str) -> None:
    result = await _callers(history_root, "make_history", "health.py")

    assert _lines(result) == {"via_module": 5, "via_alias": 9}


def test_extractor_version_is_bumped_for_unique_name_binding() -> None:
    from tree_sitter_analyzer import ast_cache
    from tree_sitter_analyzer.cache import indexer

    assert (
        ast_cache._AST_CACHE_EXTRACTOR_VERSION,
        indexer._AST_CACHE_EXTRACTOR_VERSION,
    ) == (42, 42)


@pytest.mark.parametrize(
    ("callee_full", "receiver", "unproven", "constructed", "type_name"),
    [
        ("xs.append", "xs", True, None, "xs"),
        ("self.append", "self", False, None, "self"),
        ("super().run", "super()", False, "super", "super"),
        ("self._entries.append", "self._entries", True, None, "_entries"),
        ("Foo().bar", "Foo()", True, "Foo", "Foo"),
        ("mod.Foo(a.b, 2).bar", "mod.Foo(a.b, 2)", True, "mod.Foo", "Foo"),
        ("get_foo().bar", "get_foo()", True, "get_foo", "get_foo"),
        ("Foo(1).x(2).bar", "Foo(1).x(2)", True, None, "x(2)"),
        ("helper", "", False, None, ""),
    ],
)
def test_receiver_proof_helpers(
    callee_full: str,
    receiver: str,
    unproven: bool,
    constructed: str | None,
    type_name: str,
) -> None:
    from tree_sitter_analyzer.receiver_proof import (
        constructed_class,
        has_unproven_receiver,
        receiver_type_name,
        split_receiver,
    )

    qualifier, _base = split_receiver(callee_full)
    assert (
        qualifier,
        has_unproven_receiver(callee_full),
        constructed_class(qualifier),
        receiver_type_name(qualifier),
    ) == (receiver, unproven, constructed, type_name)


def test_graph_receiver_proof_via_module_import() -> None:
    from tree_sitter_analyzer.cached_edge_resolution import (
        CachedEdgeResolver,
        _module_name,
    )
    from tree_sitter_analyzer.call_graph import FunctionRef

    fetch = FunctionRef(
        file_path="client.py", name="fetch", start_line=1, language="python"
    )
    resolver = CachedEdgeResolver(
        functions_by_name={"fetch": [fetch]},
        functions_by_file={"client.py": [fetch]},
        file_import_map={"main.py": {"client": "client.py"}},
    )
    edge = {
        "callee_name": "fetch",
        "callee_full": "client.fetch",
        "callee_resolution": "unknown",
        "callee_resolved_file": "",
    }

    assert resolver.resolve(edge, "main.py").certain == [fetch]
    # 未导入该模块的文件里，`client.fetch` 的接收者未被证明。
    assert resolver.resolve(edge, "other.py").certain == []
    assert (_module_name("pkg/__init__.py"), _module_name("pkg/client.py")) == (
        "pkg",
        "client",
    )


@pytest.mark.asyncio
async def test_bare_callback_parameter_is_not_a_method_caller(tmp_path: Path) -> None:
    # 第二遍按名字解析：`rollback()` 调用的是参数，不是项目里唯一的方法 `Conn.rollback`。
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "conn.py").write_text(
        "class Conn:\n    def rollback(self):\n        return 1\n", encoding="utf-8"
    )
    (tmp_path / "job.py").write_text(
        "def run(rollback):\n    return rollback()\n", encoding="utf-8"
    )
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 10}
    )
    assert indexed["published"] is True

    for name in ("Conn.rollback", "rollback"):
        result = await _callers(str(tmp_path), name, "conn.py")
        assert result["caller_count"] == 0, name
