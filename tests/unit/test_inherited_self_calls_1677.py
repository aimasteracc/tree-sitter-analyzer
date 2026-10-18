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


def test_mro_edge_cases_stay_conservative() -> None:
    import sqlite3

    from tree_sitter_analyzer.call_graph import _lazy_hierarchy
    from tree_sitter_analyzer.class_mro import (
        ClassKey,
        Hierarchy,
        _node,
        _ordered_parents,
        external_lacks,
    )

    assert external_lacks("", "m") is False
    assert external_lacks("os.no_such_module.Base", "m") is False
    assert _ordered_parents("not json", []) == []
    assert _ordered_parents('["Base"]', [ClassKey("b.py", "Other")]) == [
        "Base",
        "<unordered Other>",
    ]
    assert _node("a.py:C:notaline") is None
    assert _node("class:Base") is None

    class _NoConn:
        def get_conn(self):
            raise AttributeError("closed")

    lazy = _lazy_hierarchy(_NoConn())
    assert lazy().parents == {} and lazy() is lazy()

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, language TEXT, symbols_json TEXT)"
    )
    conn.execute(
        "CREATE TABLE edges (source_node_id TEXT, target_node_id TEXT, kind TEXT)"
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('a.py', 'python', ?)",
        ('{"symbols": [{"kind": "class", "name": "", "line": 1}]}',),
    )
    from tree_sitter_analyzer.class_mro import load_hierarchy

    assert load_hierarchy(conn) == Hierarchy()


def test_inherited_target_needs_the_symbol_row_and_an_absent_own_method() -> None:
    import sqlite3

    from tree_sitter_analyzer.cache.inherited_self_calls import _certain_target
    from tree_sitter_analyzer.cached_edge_resolution import CachedEdgeResolver
    from tree_sitter_analyzer.call_graph import FunctionRef
    from tree_sitter_analyzer.class_mro import ClassKey, Hierarchy

    base, child = ClassKey("b.py", "Base"), ClassKey("c.py", "Child")
    hierarchy = Hierarchy(
        parents={child: [base], base: []},
        methods={base: {"m": 2}, child: {"own": 5}},
    )
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER, file_path TEXT, name TEXT, "
        "line INTEGER, kind TEXT)"
    )
    # 外围类自己定义了它：交给 Synapse 的 self 规则；找到定义但没有符号行：不写入。
    assert _certain_target(conn, hierarchy, child, "own") is None
    assert _certain_target(conn, hierarchy, child, "m") is None

    own_a = FunctionRef(
        file_path="c.py", name="own", start_line=5, language="python", receiver="Child"
    )
    own_b = FunctionRef(
        file_path="c.py", name="own", start_line=9, language="python", receiver="Child"
    )
    resolver = CachedEdgeResolver(
        functions_by_name={"own": [own_a, own_b]},
        functions_by_file={"c.py": [own_a, own_b]},
        file_import_map={},
        hierarchy=lambda: hierarchy,
    )
    assert resolver._inherited_target("c.py", "Child", "own") is None


def test_second_pass_skips_own_receiver_calls_only() -> None:
    import sqlite3

    from tree_sitter_analyzer.cache.unresolved import _call_refs

    edges = [
        {
            "caller_name": "run",
            "caller_line": 1,
            "callee_name": "m",
            "callee_full": "self.m",
            "callee_line": 2,
        },
        {
            "caller_name": "run",
            "caller_line": 1,
            "callee_name": "m",
            "callee_full": "obj.m",
            "callee_line": 3,
        },
    ]
    refs = _call_refs(sqlite3.connect(":memory:"), "c.py", "python", edges, set())

    assert [ref["line"] for ref in refs] == [3]


def test_index_pass_skips_unknown_owners_and_survives_a_readonly_index(
    tmp_path: Path,
) -> None:
    import json
    import sqlite3

    from tree_sitter_analyzer.cache.inherited_self_calls import (
        resolve_inherited_self_calls,
    )

    db = tmp_path / "index.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, language TEXT, symbols_json TEXT)"
    )
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER, file_path TEXT, name TEXT, "
        "line INTEGER, kind TEXT)"
    )
    conn.execute(
        "CREATE TABLE edges (id INTEGER PRIMARY KEY, kind TEXT, language TEXT, "
        "file_path TEXT, caller_name TEXT, caller_line INTEGER, callee_name TEXT, "
        "callee_full TEXT, callee_resolution TEXT, callee_resolved_file TEXT, "
        "callee_symbol_id INTEGER, source_node_id TEXT, target_node_id TEXT)"
    )
    symbols = {
        "b.py": [
            {"kind": "class", "name": "Base", "line": 1, "parents": []},
            {"kind": "method", "name": "m", "line": 2, "class": "Base"},
        ],
        "c.py": [
            {"kind": "class", "name": "Child", "line": 1, "parents": ["Base"]},
            {"kind": "method", "name": "run", "line": 2, "class": "Child"},
        ],
    }
    for path, items in symbols.items():
        conn.execute(
            "INSERT INTO ast_index VALUES (?, 'python', ?)",
            (path, json.dumps({"symbols": items})),
        )
    conn.execute("INSERT INTO ast_symbol_rows VALUES (7, 'b.py', 'm', 2, 'method')")
    conn.execute(
        "INSERT INTO edges (kind, source_node_id, target_node_id) "
        "VALUES ('extends', 'c.py:Child:1', 'b.py:Base:1')"
    )
    pending = (
        "INSERT INTO edges (kind, language, file_path, caller_name, caller_line, "
        "callee_name, callee_full, callee_resolution, callee_resolved_file) "
        "VALUES ('calls', 'python', 'c.py', ?, ?, 'm', 'self.m', 'unknown', '')"
    )
    conn.execute(pending, ("ghost", 40))
    conn.commit()
    # 调用方不是任何类的方法：跳过，不更新任何边。
    assert resolve_inherited_self_calls(conn) == 0
    conn.execute(pending, ("run", 2))
    conn.commit()
    conn.close()

    readonly = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        assert resolve_inherited_self_calls(readonly) == 0
    finally:
        readonly.close()
    writable = sqlite3.connect(db)
    try:
        assert resolve_inherited_self_calls(writable) == 1
        row = writable.execute(
            "SELECT callee_resolution, callee_resolved_file, callee_symbol_id "
            "FROM edges WHERE caller_name = 'run'"
        ).fetchone()
    finally:
        writable.close()
    assert row == ("project", "b.py", 7)
